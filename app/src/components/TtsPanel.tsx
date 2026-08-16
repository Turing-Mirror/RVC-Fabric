import { useEffect, useRef, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Btn, HelpMark } from "./ui";
import { Field, RangeBar } from "./controls";
import { SegmentControl } from "./SegmentControl";
import { ToolBody } from "./ToolWindow";
import { t } from "../i18n/t";
import { openHelpSection } from "../lib/helpNav";
import { listVoices, type VoiceModel } from "../lib/voices";
import { askConfirm } from "../lib/webDialog";
import { openDownloadModels } from "../lib/downloadModels";

/** Windows path compare: slash / case must not hide a just-selected voice. */
function samePath(a?: string, b?: string): boolean {
  if (!a || !b) return false;
  const n = (p: string) => p.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  return n(a) === n(b);
}

/** 工具窗两个模式：官方语义的音频推理 + 保留的文字合成。 */
type Mode = "sts" | "tts";

type StsStatus = {
  runtime_ready?: boolean;
  engine_core_ready?: boolean;
  engine_core_missing?: string[];
  worker_present?: boolean;
  model_path?: string;
  model_name?: string;
  index_path?: string;
  pitch?: number;
  f0method?: string;
  index_rate?: number;
  out_dir?: string;
  worker_alive?: boolean;
  busy?: boolean;
  last_input?: string;
  last_output?: string;
  default_input_dir?: string;
  input_device?: string;
  recorder_present?: boolean;
  recording?: boolean;
};

type RecProgress = {
  phase: string;
  db?: number;
  sec?: number;
  message?: string;
};

type InputFile = {
  name: string;
  rel: string;
  path: string;
  size: number;
  mtime: number;
};

type InputList = {
  dir: string;
  exists?: boolean;
  truncated?: boolean;
  files?: InputFile[];
};

type TtsStatus = {
  runtime_ready?: boolean;
  infer_present?: boolean;
  voices?: string[];
  model_path?: string;
  model_name?: string;
  out_dir?: string;
  max_chars?: number;
  busy?: boolean;
};

type Progress = {
  phase: string;
  done: number;
  total: number;
  message: string;
  /** 整次任务 0–100 细粒度进度（模型加载 + 文件内分步）；缺省时回退 done/total */
  pct?: number;
  step?: string;
  /** 当前文件序号（1-based），批量时用 */
  current?: number;
  /** 已成功 / 已跳过 计数，批量实时看板 */
  ok?: number;
  skip?: number;
  file?: string;
  /** skip 事件的干净原因（不含「跳过 name：」前缀） */
  reason?: string;
};

/** 批量转换里没转出来的那几个：哪个文件、为什么。 */
type Skipped = {
  file: string;
  name: string;
  reason: string;
};

const ROW = "flex items-center gap-3 py-2.5";
const LABEL = "w-[86px] shrink-0 text-[13px]";
const LIST_CAP_UI = 300;
const PATH =
  "flex-1 min-w-0 truncate text-[12.5px] text-[var(--ink-muted)] font-mono";
const FIELD =
  "rounded-[var(--rs)] border border-[var(--hairline)] bg-transparent px-2 py-1.5 text-[13px]";
const STS_F0 = ["rmvpe", "harvest", "pm", "crepe"] as const;
const STS_FMTS = ["wav", "flac", "mp3", "m4a"] as const;
const STS_RATES = [0, 16000, 32000, 40000, 44100, 48000] as const;

/**
 * 语音转换工具窗。
 *
 * - **音频变声（STS）**：对应官方 RVC「推理 / 批量推理」——选音频文件或文件夹，
 *   用当前音色离线换成目标声线。这是本意。
 * - **文字合成（TTS）**：系统 SAPI 先念字，再可选 RVC 换音色。额外保留。
 */
export function TtsPanel() {
  const [mode, setMode] = useState<Mode>("sts");

  return (
    <ToolBody>
      <h3 className="m-0 mb-1 text-[17px] font-semibold">{t("s.6f311c47fe")}</h3>
      <p className="m-0 mb-3 text-[12.5px] text-[var(--ink-muted)]">{t("s.859b483004")}</p>
      <div className="mb-4">
        <SegmentControl<Mode>
          value={mode}
          onChange={setMode}
          options={[
            { id: "sts", label: t("s.9035f9b6d1") },
            { id: "tts", label: t("s.90872a6528") },
          ]}
        />
      </div>
      {mode === "sts" ? <StsSection /> : <TtsSection />}
    </ToolBody>
  );
}

// ---------------------------------------------------------------------------
// 音频变声（Speech-to-Speech）
// ---------------------------------------------------------------------------

function formatElapsed(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** 根据已用时间和整体 pct 估剩余时间；pct 太低时不报，避免乱跳。 */
function formatEta(elapsedSec: number, pct: number): string {
  if (elapsedSec < 3 || pct < 5 || pct >= 100) return "";
  const remain = Math.round((elapsedSec * (100 - pct)) / pct);
  if (remain < 1) return "";
  return t("s.stsEta", { v0: formatElapsed(remain) });
}

function formatBytes(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} MB`;
  if (n >= 1_000) return `${Math.round(n / 1_000)} KB`;
  return `${n} B`;
}

function formatMtime(sec: number): string {
  if (!sec) return "";
  const d = new Date(sec * 1000);
  if (Number.isNaN(d.getTime())) return "";
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function formatRecSec(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function StsSection() {
  const [st, setSt] = useState<StsStatus>({});
  const [voices, setVoices] = useState<VoiceModel[]>([]);
  // 本窗选的目标音色；默认跟首页「当前变声音色」，改这里不改全局选中。
  const [modelPath, setModelPath] = useState("");
  const [indexPath, setIndexPath] = useState("");
  const [modelName, setModelName] = useState("");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [pitch, setPitch] = useState(0);
  const [f0method, setF0method] = useState<(typeof STS_F0)[number]>("rmvpe");
  const [indexRate, setIndexRate] = useState(0.75);
  const [protect, setProtect] = useState(0.33);
  const [rms, setRms] = useState(0.25);
  const [filterRadius, setFilterRadius] = useState(3);
  const [resample, setResample] = useState(0);
  const [fmt, setFmt] = useState<(typeof STS_FMTS)[number]>("wav");
  const [adv, setAdv] = useState(false);
  const [sid, setSid] = useState(0);
  const [f0File, setF0File] = useState("");
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  // 批量里转失败被跳过的文件。整批不再因为一个坏文件中止，所以得有地方交代
  // 到底是哪几个没转出来。过程中 skip 事件也会往这里塞，不用等整批结束。
  const [skipped, setSkipped] = useState<Skipped[]>([]);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const runningRef = useRef(false);
  const [lib, setLib] = useState<InputList | null>(null);
  const [recording, setRecording] = useState(false);
  const [rec, setRec] = useState<RecProgress | null>(null);
  const [playing, setPlaying] = useState("");
  const recordingRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const inputRef = useRef(input);
  inputRef.current = input;
  const lastHomePath = useRef("");
  /** 上一次真正写出文件的目录。打开输出目录用它，不看默认 sts。 */
  const lastDestRef = useRef("");

  const pickVoice = (m: VoiceModel | undefined) => {
    if (!m || !m.path) return;
    setModelPath(m.path);
    setIndexPath(typeof m.index === "string" ? m.index : "");
    setModelName(m.name || m.file || "");
  };

  const applyCurrent = (
    s: StsStatus,
    cat: { models?: VoiceModel[]; selected_idx?: number },
  ) => {
    const usable = (cat.models || []).filter(
      (m) => m.path && !m.missing && String(m.path).length > 0,
    );
    setVoices(usable);
    const byPath =
      s.model_path && usable.find((m) => samePath(m.path, s.model_path));
    const byIdx =
      cat.selected_idx != null && cat.selected_idx >= 0
        ? cat.models?.[cat.selected_idx]
        : undefined;
    const byIdxUsable =
      byIdx && usable.some((m) => samePath(m.path, byIdx.path)) ? byIdx : undefined;
    // 首页当前音色优先：上次转换用过的路径不能盖住刚换的最近模型。
    const chosen = byIdxUsable || byPath || usable[0];
    if (chosen) {
      if (byIdxUsable) lastHomePath.current = byIdxUsable.path;
      pickVoice(chosen);
    } else if (s.model_path) {
      setModelPath(s.model_path);
      setIndexPath(s.index_path || "");
      setModelName(s.model_name || "");
    }
  };

  const load = async (full = true) => {
    try {
      const [s, cat] = await Promise.all([
        invoke<StsStatus>("sts_status"),
        listVoices(),
      ]);
      setSt(s);
      if (full) {
        if (s.pitch != null) setPitch(Number(s.pitch));
        if (s.f0method) {
          const m = String(s.f0method);
          setF0method(
            (STS_F0 as readonly string[]).includes(m)
              ? (m as (typeof STS_F0)[number])
              : "rmvpe",
          );
        }
        if (s.index_rate != null) setIndexRate(Number(s.index_rate));
        if (!input && s.last_input) setInput(String(s.last_input));
        // 只回填用户选过的目录。默认 User_Data/sts 不当成已选。
        if (!output && s.last_output) setOutput(String(s.last_output));
        if (s.recording) {
          recordingRef.current = true;
          setRecording(true);
        }
      }
      applyCurrent(s, cat);
    } catch (e) {
      setMsg(String(e));
    }
  };

  useEffect(() => {
    void load(true);
    let disposed = false;
    const unsubs: Array<() => void> = [];
    void listen<Progress>("sts-progress", (ev) => {
      const p = ev.payload;
      setProg(p);
      if (p.phase === "error") setMsg(p.message);
      // 批量：跳过事件当场入列，方便边跑边看哪个坏了。
      if (p.phase === "skip" && p.file) {
        setSkipped((prev) => {
          if (prev.some((x) => x.name === p.file || x.file === p.file)) return prev;
          return [
            ...prev,
            {
              file: p.file || p.message,
              name: p.file || "?",
              reason: p.reason || p.message,
            },
          ];
        });
      }
    }).then((fn) => {
      if (disposed) fn();
      else unsubs.push(fn);
    });
    void listen<RecProgress>("sts-record", (ev) => {
      setRec(ev.payload);
      if (ev.payload.phase === "done" || ev.payload.phase === "error") {
        recordingRef.current = false;
        setRecording(false);
        void invoke<InputList>("sts_list_input", {
          input: inputRef.current,
        }).then(setLib)
          .catch(() => undefined);
      }
    }).then((fn) => {
      if (disposed) fn();
      else unsubs.push(fn);
    });
    // 首页换音色（含最近三卡）时本窗要跟过去。工具窗是独立 webview，
    // 不听事件就一直停在打开时的那一个。
    const followHome = (m?: VoiceModel | null) => {
      if (m?.path && !m.missing) {
        lastHomePath.current = m.path;
        pickVoice(m);
        return true;
      }
      return false;
    };
    void listen<{ model?: VoiceModel }>("voices-changed", (ev) => {
      if (followHome(ev.payload?.model)) {
        void listVoices()
          .then((cat) => {
            setVoices(
              (cat.models || []).filter(
                (x) => x.path && !x.missing && String(x.path).length > 0,
              ),
            );
          })
          .catch(() => undefined);
        return;
      }
      void load(false);
    }).then((fn) => {
      if (disposed) fn();
      else unsubs.push(fn);
    });
    void listen<{ config?: { last_model_path?: string } }>(
      "config-changed",
      (ev) => {
        const p = ev.payload?.config?.last_model_path || "";
        if (!p || samePath(p, lastHomePath.current)) return;
        lastHomePath.current = p;
        void listVoices()
          .then((cat) => {
            const usable = (cat.models || []).filter(
              (x) => x.path && !x.missing && String(x.path).length > 0,
            );
            setVoices(usable);
            const hit = usable.find((x) => samePath(x.path, p));
            if (hit) pickVoice(hit);
          })
          .catch(() => undefined);
      },
    ).then((fn) => {
      if (disposed) fn();
      else unsubs.push(fn);
    });
    let unFocus: (() => void) | undefined;
    try {
      const win = getCurrentWindow();
      void win
        .onFocusChanged((ev) => {
          // 只把新装进库的音色补进下拉框；不要盖掉本窗刚选的目标。
          if (!ev.payload) return;
          void listVoices()
            .then((cat) => {
              setVoices(
                (cat.models || []).filter(
                  (x) => x.path && !x.missing && String(x.path).length > 0,
                ),
              );
            })
            .catch(() => undefined);
        })
        .then((fn) => {
          if (disposed) fn();
          else unFocus = fn;
        });
    } catch {
      /* 浏览器预览没有 Tauri 窗口 */
    }
    return () => {
      disposed = true;
      unsubs.forEach((f) => f());
      unFocus?.();
      audioRef.current?.pause();
    };
  }, []);

  const refreshList = async (path: string) => {
    try {
      const r = await invoke<InputList>("sts_list_input", { input: path });
      setLib(r);
    } catch (e) {
      setMsg(String(e));
    }
  };

  useEffect(() => {
    // 只跟输入路径走
    void refreshList(input);
  }, [input]);

  // 单文件音高提取可能静默几十秒；有已用时间用户才知道还在跑。
  useEffect(() => {
    if (!running) {
      setElapsed(0);
      return;
    }
    const t0 = Date.now();
    const id = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - t0) / 1000));
    }, 500);
    return () => window.clearInterval(id);
  }, [running]);

  const recBlocked = !st.runtime_ready
    ? t("s.bc45fc14b1")
    : st.recorder_present === false
      ? t("s.stsRecordNeedWorker")
      : "";
  const blocked = !st.runtime_ready
    ? t("s.bc45fc14b1")
    : st.engine_core_ready === false
      ? t("s.156ff9271b", {
          v0: (st.engine_core_missing || []).join("、") || "hubert/rmvpe",
        })
      : !st.worker_present
        ? t("s.84b7d7b6b0")
        : !modelPath
          ? t("s.03877888b6")
          : "";

  const stopPlay = () => {
    audioRef.current?.pause();
    setPlaying("");
  };

  const playFile = (path: string) => {
    if (playing === path) {
      stopPlay();
      return;
    }
    stopPlay();
    try {
      const el = audioRef.current ?? new Audio();
      audioRef.current = el;
      el.src = convertFileSrc(path);
      el.onended = () => setPlaying("");
      el.onerror = () => {
        setPlaying("");
        setMsg(t("s.stsPlayFail"));
      };
      void el.play().then(() => setPlaying(path));
    } catch (e) {
      setMsg(String(e));
    }
  };

  const startRec = async () => {
    if (recordingRef.current || runningRef.current) return;
    stopPlay();
    setMsg("");
    setRec({ phase: "start", sec: 0, message: t("s.stsRecordOpening") });
    recordingRef.current = true;
    setRecording(true);
    const prior = input;
    try {
      let folder = prior;
      if (!folder) {
        folder = await invoke<string>("sts_default_input");
        setInput(folder);
      }
      const r = await invoke<{
        file?: string;
        dir?: string;
        cancelled?: boolean;
      }>("sts_record_start", { input: folder });
      if (r.dir) {
        const wasSingle = !!(prior && lib?.dir && prior !== lib.dir);
        if (wasSingle && r.file && !r.cancelled) setInput(r.file);
        else if (!prior) setInput(r.dir);
      }
      if (r.file && !r.cancelled) {
        setMsg(t("s.stsRecordSaved", { v0: r.file }));
      }
      await refreshList(r.dir || folder);
    } catch (e) {
      setMsg(String(e));
    } finally {
      recordingRef.current = false;
      setRecording(false);
      setRec(null);
    }
  };

  const removeFile = async (f: InputFile) => {
    if (!(await askConfirm(t("s.stsDeleteConfirm", { v0: f.name })))) return;
    if (playing === f.path) stopPlay();
    try {
      await invoke("sts_delete_input", { input, path: f.path });
      if (input === f.path) setInput(lib?.dir || "");
      await refreshList(input === f.path ? lib?.dir || "" : input);
    } catch (e) {
      setMsg(String(e));
    }
  };

  const start = async () => {
    if (runningRef.current || recordingRef.current) return;
    // 实时 worker 还活着就走热路径（复用已加载的模型），不再先杀进程。
    setMsg("");
    setProg({ phase: "start", done: 0, total: 1, pct: 0, message: t("s.090840132b") });
    setSkipped([]);
    runningRef.current = true;
    setRunning(true);
    try {
      const r = await invoke<{
        files?: string[];
        skipped?: Skipped[];
        output?: string;
      }>("sts_start", {
        input,
        output,
        pitch,
        f0method,
        indexRate,
        modelPath,
        indexPath,
        filterRadius,
        resampleSr: resample,
        rmsMixRate: rms,
        protect,
        format: fmt,
        sid,
        f0File,
      });
      const ok = r.files?.length ?? 0;
      const bad = r.skipped ?? [];
      if (r.output) lastDestRef.current = String(r.output);
      // 终态清单覆盖过程中累积的，避免 reason 被截断的半截文案。
      setSkipped(bad);
      // 有跳过的就必须在总结里说出来，不然「完成 8 个文件」会被当成全转完了。
      setMsg(
        bad.length
          ? t("s.stsDoneSkipped", {
              v0: ok,
              v1: bad.length,
              v2: r.output || "",
            })
          : r.output
            ? t("s.6a17eda1b7", { v0: ok, v1: r.output })
            : t("s.4d8ef8514f", { v0: ok }),
      );
    } catch (e) {
      setMsg(String(e));
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  };

  // 优先用 worker 细粒度 pct；旧 worker 没有 pct 时回退文件计数。
  const pct =
    prog?.pct != null && Number.isFinite(prog.pct)
      ? Math.max(0, Math.min(100, Math.round(Number(prog.pct))))
      : prog?.total
        ? Math.round((prog.done / prog.total) * 100)
        : 0;
  const multi = !!(prog && prog.total > 1);
  const current =
    prog?.current && prog.current > 0
      ? prog.current
      : prog
        ? Math.min(prog.done + (prog.phase === "run" ? 1 : 0), prog.total)
        : 0;
  const fileHint = multi ? `${current}/${prog!.total}` : "";
  const okN = prog?.ok ?? 0;
  const skipN = prog?.skip ?? skipped.length;
  const eta = running ? formatEta(elapsed, pct) : "";

  return (
    <>
      <div className="mb-3 flex justify-end">
        <Btn onClick={() => openHelpSection("infer")}>{t("s.trainOpenHelp")}</Btn>
      </div>
      {blocked ? (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <p className="m-0 text-[13px] text-[#b8534f]">{blocked}</p>
          {st.engine_core_ready === false ? (
            <Btn onClick={() => openDownloadModels()}>{t("s.1252c81119")}</Btn>
          ) : null}
        </div>
      ) : null}

      <div>
        <div className={ROW}>
          <span className={LABEL}>{t("s.stsTargetVoice")}</span>
          <select
            className={`flex-1 min-w-0 ${FIELD}`}
            value={voices.find((v) => samePath(v.path, modelPath))?.path || modelPath}
            disabled={running || !voices.length}
            onChange={(e) => {
              const m = voices.find((v) => samePath(v.path, e.target.value));
              pickVoice(m);
            }}
          >
            {voices.map((m) => (
              <option key={m.path} value={m.path}>
                {m.name || m.file || m.path}
              </option>
            ))}
            {!voices.length ? (
              <option value="">{t("s.03877888b6")}</option>
            ) : null}
          </select>
        </div>
        {!blocked && modelName ? (
          <p className="m-0 px-0 pb-1 text-[12px] text-[var(--meta)]">
            {t("s.6c415e91bb", { v0: modelName })}
            {indexPath ? t("s.0ca99fa9f1") : ""}
          </p>
        ) : null}
        <div className={ROW}>
          <span className={LABEL}>{t("s.e8850440f2")}</span>
          <span className={PATH}>{input || t("s.245826185c")}</span>
          <Btn
            disabled={running || recording}
            onClick={() => {
              void invoke<string | null>("sts_pick_input", { folder: false }).then(
                (p) => p && setInput(p),
              );
            }}
          >{t("s.49deaf7da2")}</Btn>
          <Btn
            disabled={running || recording}
            onClick={() => {
              void invoke<string | null>("sts_pick_input", { folder: true }).then(
                (p) => p && setInput(p),
              );
            }}
          >{t("s.46ecac2910")}</Btn>
        </div>
        <div className={ROW}>
          <span className={LABEL}>{t("s.a0bc984876")}</span>
          <span className={PATH}>{output || t("s.53e2db7016")}</span>
          <Btn
            onClick={() => {
              void invoke<string | null>("sts_pick_output").then(
                (p) => p && setOutput(p),
              );
            }}
          >{t("s.70b208202c")}</Btn>
        </div>
        <div className={ROW}>
          <span className={LABEL}>{t("s.stsRecord")}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5">
              <div
                className="relative h-1.5 w-[120px] shrink-0 overflow-hidden rounded-sm bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]"
                title={t("s.stsRecord")}
              >
                <div
                  className="absolute inset-y-0 left-0 rounded-sm bg-[var(--accent)] transition-[width] duration-75"
                  style={{
                    width: `${
                      recording
                        ? Math.round(
                            ((Math.max(-60, Math.min(0, rec?.db ?? -60)) + 60) /
                              60) *
                              100,
                          )
                        : 0
                    }%`,
                  }}
                />
              </div>
              <span className="w-[44px] shrink-0 tabular-nums text-[12.5px] text-[var(--meta)]">
                {formatRecSec(rec?.sec ?? 0)}
              </span>
              {recording ? (
                <Btn onClick={() => void invoke("sts_record_stop")}>
                  {t("s.stsRecordStop")}
                </Btn>
              ) : (
                <Btn
                  disabled={running || !!recBlocked}
                  onClick={() => void startRec()}
                >
                  {t("s.stsRecordStart")}
                </Btn>
              )}
            </div>
            <p className="m-0 mt-1 text-[11.5px] text-[var(--meta)] truncate">
              {recording
                ? rec?.message || t("s.stsRecording")
                : t("s.stsRecordDevice", {
                    v0: st.input_device || t("s.stsRecordDeviceDefault"),
                  })}
            </p>
          </div>
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <span className="text-[13px] font-medium">{t("s.stsInputLibrary")}</span>
          <span className="text-[11.5px] text-[var(--meta)]">
            {lib?.truncated
              ? t("s.stsInputTruncated", { v0: LIST_CAP_UI })
              : t("s.stsInputCount", { v0: lib?.files?.length ?? 0 })}
          </span>
        </div>
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          {!input ? (
            <Btn
              disabled={running || recording}
              onClick={() => {
                void invoke<string>("sts_default_input").then((p) => {
                  if (p) setInput(p);
                });
              }}
            >
              {t("s.stsDefaultFolder")}
            </Btn>
          ) : null}
          {input && lib?.dir && input !== lib.dir ? (
            <Btn
              disabled={running || recording}
              onClick={() => setInput(lib.dir)}
            >
              {t("s.stsUseFolder")}
            </Btn>
          ) : null}
          <Btn
            disabled={!lib?.dir}
            onClick={() => {
              if (lib?.dir) void invoke("sts_reveal_input", { path: lib.dir });
            }}
          >
            {t("s.stsOpenInput")}
          </Btn>
        </div>
        {(lib?.files?.length ?? 0) === 0 ? (
          <p className="m-0 text-[12.5px] text-[var(--meta)]">
            {t("s.stsInputEmpty")}
          </p>
        ) : (
          <ul className="m-0 max-h-[220px] list-none overflow-y-auto p-0">
            {(lib?.files ?? []).map((f) => {
              const on = input === f.path;
              return (
                <li
                  key={f.path}
                  className={[
                    "flex items-center gap-2 rounded-[var(--rs)] px-2 py-1.5",
                    on
                      ? "bg-[color-mix(in_srgb,var(--accent)_10%,transparent)]"
                      : "hover:bg-[color-mix(in_srgb,var(--ink)_4%,transparent)]",
                  ].join(" ")}
                >
                  <button
                    type="button"
                    className="min-w-0 flex-1 border-0 bg-transparent p-0 text-left cursor-pointer"
                    disabled={running || recording}
                    onClick={() => setInput(f.path)}
                    title={f.path}
                  >
                    <span className="block truncate text-[12.5px] font-mono">
                      {f.rel || f.name}
                    </span>
                    <span className="block text-[11px] text-[var(--meta)] tabular-nums">
                      {`${formatBytes(f.size)}${f.mtime ? ` · ${formatMtime(f.mtime)}` : ""}`}
                    </span>
                  </button>
                  <Btn
                    disabled={recording}
                    onClick={() => playFile(f.path)}
                  >
                    {playing === f.path ? t("s.stsStopPlay") : t("s.stsPlay")}
                  </Btn>
                  <Btn
                    disabled={running || recording}
                    onClick={() => void removeFile(f)}
                  >
                    {t("s.stsDelete")}
                  </Btn>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="mt-1">
        <div className={ROW}>
          <span className={LABEL}>{t("s.bda11a3c2d")}</span>
          <div className="flex-1">
            <RangeBar
              value={pitch}
              min={-24}
              max={24}
              step={1}
              defaultValue={0}
              onChange={setPitch}
              ariaLabel={t("s.bda11a3c2d")}
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {pitch > 0 ? `+${pitch}` : pitch}
          </span>
        </div>
        <div className={ROW}>
          <span className={`${LABEL} flex items-center gap-1.5`}>
            {t("s.3579ac474b")}
            <HelpMark title={t("s.stsF0Hint")} />
          </span>
          <select
            className={`flex-1 min-w-0 ${FIELD}`}
            value={f0method}
            onChange={(e) => setF0method(e.target.value as (typeof STS_F0)[number])}
          >
            {STS_F0.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div className={ROW}>
          <span className={LABEL}>{t("s.389bc211b2")}</span>
          <div className="flex-1">
            <RangeBar
              value={indexRate}
              min={0}
              max={1}
              step={0.01}
              defaultValue={0.75}
              onChange={setIndexRate}
              ariaLabel={t("s.389bc211b2")}
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {indexRate.toFixed(2)}
          </span>
        </div>
        <div className={ROW}>
          <span className={`${LABEL} flex items-center gap-1.5`}>
            {t("s.stsProtect")}
            <HelpMark title={t("s.stsProtectHint")} />
          </span>
          <div className="flex-1">
            <RangeBar
              value={protect}
              min={0}
              max={0.5}
              step={0.01}
              defaultValue={0.33}
              onChange={setProtect}
              ariaLabel={t("s.stsProtect")}
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {protect.toFixed(2)}
          </span>
        </div>
        <div className={ROW}>
          <span className={`${LABEL} flex items-center gap-1.5`}>
            {t("s.stsRms")}
            <HelpMark title={t("s.stsRmsHint")} />
          </span>
          <div className="flex-1">
            <RangeBar
              value={rms}
              min={0}
              max={1}
              step={0.01}
              defaultValue={0.25}
              onChange={setRms}
              ariaLabel={t("s.stsRms")}
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {rms.toFixed(2)}
          </span>
        </div>
        <div className={ROW}>
          <span className={`${LABEL} flex items-center gap-1.5`}>
            {t("s.stsFilter")}
            <HelpMark title={t("s.stsFilterHint")} />
          </span>
          <div className="flex-1">
            <RangeBar
              value={filterRadius}
              min={0}
              max={7}
              step={1}
              defaultValue={3}
              onChange={setFilterRadius}
              ariaLabel={t("s.stsFilter")}
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {filterRadius}
          </span>
        </div>
        <div className={ROW}>
          <span className={`${LABEL} flex items-center gap-1.5`}>
            {t("s.stsResample")}
            <HelpMark title={t("s.stsResampleHint")} />
          </span>
          <select
            className={`flex-1 min-w-0 ${FIELD}`}
            value={resample}
            onChange={(e) => setResample(Number(e.target.value) || 0)}
          >
            {STS_RATES.map((n) => (
              <option key={n} value={n}>
                {n === 0 ? t("s.stsResampleOff") : `${n}`}
              </option>
            ))}
          </select>
        </div>
        <div className={ROW}>
          <span className={`${LABEL} flex items-center gap-1.5`}>
            {t("s.stsFormat")}
            <HelpMark title={t("s.stsFormatHint")} />
          </span>
          <select
            className={`flex-1 min-w-0 ${FIELD}`}
            value={fmt}
            onChange={(e) => setFmt(e.target.value as (typeof STS_FMTS)[number])}
          >
            {STS_FMTS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-3">
        <Btn onClick={() => setAdv((v) => !v)}>
          {adv ? t("s.ckptAdvancedHide") : t("s.ckptAdvanced")}
        </Btn>
        {adv ? (
          <div className="mt-3 flex flex-col gap-3.5">
            <Field
              label={t("s.stsSid")}
              tip={t("s.stsSidHint")}
              control={
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <RangeBar
                      value={sid}
                      min={0}
                      max={16}
                      step={1}
                      defaultValue={0}
                      onChange={setSid}
                      ariaLabel={t("s.stsSid")}
                    />
                  </div>
                  <input
                    className={`w-[64px] ${FIELD}`}
                    type="number"
                    min={0}
                    max={2333}
                    value={sid}
                    onChange={(e) =>
                      setSid(Math.max(0, Math.min(2333, Number(e.target.value) || 0)))
                    }
                  />
                </div>
              }
            />
            <Field
              label={t("s.stsF0File")}
              tip={t("s.stsF0FileHint")}
              control={
                <div className="flex items-center gap-2">
                  <span className={PATH}>{f0File || t("s.53e2db7016")}</span>
                  <Btn
                    disabled={running}
                    onClick={() => {
                      void invoke<string | null>("ckpt_pick", { kind: "f0" }).then(
                        (p) => p && setF0File(p),
                      );
                    }}
                  >
                    {t("s.70b208202c")}
                  </Btn>
                  {f0File ? (
                    <Btn disabled={running} onClick={() => setF0File("")}>
                      {t("s.stsF0FileClear")}
                    </Btn>
                  ) : null}
                </div>
              }
            />
          </div>
        ) : null}
      </div>

      {prog || running ? (
        <div className="mt-4">
          <div className="h-1.5 w-full overflow-hidden rounded bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
            <div
              className="h-full bg-[var(--accent)] transition-[width] duration-200"
              style={{ width: `${running && pct < 2 ? 2 : pct}%` }}
            />
          </div>
          <div className="mt-2 flex items-baseline justify-between gap-3 text-[12px] text-[var(--meta)]">
            <p className="m-0 min-w-0 flex-1 break-all">
              {prog?.message || t("s.090840132b")}
            </p>
            <p className="m-0 shrink-0 tabular-nums text-right">
              {fileHint ? `${fileHint} · ` : ""}
              {`${pct}%`}
              {running ? ` · ${formatElapsed(elapsed)}` : ""}
              {eta ? ` · ${eta}` : ""}
            </p>
          </div>
          {multi && running ? (
            <p className="m-0 mt-1 text-[11.5px] text-[var(--meta)] tabular-nums">
              {t("s.stsBatchStats", {
                v0: okN,
                v1: skipN,
                v2: Math.max(0, (prog?.total ?? 0) - okN - skipN),
              })}
            </p>
          ) : null}
        </div>
      ) : null}

      {msg ? (
        <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)] break-all">
          {msg}
        </p>
      ) : null}

      {skipped.length ? (
        <div className="mt-3 pt-2">
          <p className="m-0 mb-1 text-[12px] text-[var(--meta)]">
            {t("s.stsSkippedTitle", { v0: skipped.length })}
          </p>
          <ul className="m-0 list-none p-0">
            {skipped.map((s) => (
              <li
                key={s.file}
                className="py-0.5 text-[12px] text-[var(--meta)] break-all"
              >
                <span className="font-mono">{s.name}</span>
                {` — ${s.reason}`}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-5 flex justify-end gap-2.5">
        {running ? (
          <Btn onClick={() => void invoke("sts_cancel")}>{t("s.4d0b4688c7")}</Btn>
        ) : (
          <Btn
            onClick={() =>
              void invoke("sts_reveal", {
                path: lastDestRef.current || output,
              })
            }
          >
            {t("s.344a481fa0")}
          </Btn>
        )}
        <Btn
          primary
          disabled={running || recording || !!blocked || !input}
          onClick={() => void start()}
        >
          {running ? t("s.090840132b") : t("s.31e9cad169")}
        </Btn>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// 文字合成（TTS → 可选 RVC）— 保留
// ---------------------------------------------------------------------------

function TtsSection() {
  const [st, setSt] = useState<TtsStatus>({});
  const [text, setText] = useState("");
  const [voice, setVoice] = useState("");
  const [rate, setRate] = useState(0);
  const [pitch, setPitch] = useState(0);
  const [useRvc, setUseRvc] = useState(true);
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  const [running, setRunning] = useState(false);
  const runningRef = useRef(false);

  useEffect(() => {
    void (async () => {
      try {
        const s = await invoke<TtsStatus>("tts_status");
        setSt(s);
        if (s.voices?.length) setVoice((v) => v || s.voices![0]);
      } catch (e) {
        setMsg(String(e));
      }
    })();
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<Progress>("tts-progress", (ev) => {
      setProg(ev.payload);
      if (ev.payload.phase === "error") setMsg(ev.payload.message);
    }).then((fn) => {
      if (disposed) fn();
      else un = fn;
    });
    return () => {
      disposed = true;
      un?.();
    };
  }, []);

  const max = st.max_chars ?? 2000;
  const over = text.length > max;

  const blocked = !st.voices?.length
    ? t("s.42d0633ac9")
    : useRvc && !st.model_path
      ? t("s.bb1d8d1da8")
      : useRvc && !st.runtime_ready
        ? t("s.bc45fc14b1")
        : useRvc && !st.infer_present
          ? t("s.68cf604e87")
          : "";

  const start = async () => {
    if (runningRef.current) return;
    setMsg("");
    setProg(null);
    runningRef.current = true;
    setRunning(true);
    try {
      const r = await invoke<{ file?: string; converted?: boolean }>("tts_speak", {
        text,
        voice,
        rate,
        pitch,
        useRvc,
      });
      setMsg(t("s.c7cbedc8f6", { v0: r.file ?? "" }));
    } catch (e) {
      setMsg(String(e));
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  };

  return (
    <>
      <p className="m-0 mb-3 text-[12.5px] text-[var(--meta)]">{t("s.b052ea8cb8")}</p>

      {blocked ? (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <p className="m-0 text-[13px] text-[#b8534f]">{blocked}</p>
          {useRvc && !st.infer_present ? (
            <Btn onClick={() => openDownloadModels()}>{t("s.1252c81119")}</Btn>
          ) : null}
        </div>
      ) : null}

      <textarea
        className={[
          "w-full min-h-[120px] rounded-[var(--rs)] border px-3 py-2.5 text-[13.5px] leading-relaxed",
          "bg-transparent text-[var(--ink)] resize-y",
          over ? "border-[#b8534f]" : "border-[var(--hairline)]",
        ].join(" ")}
        placeholder={t("s.f2f07193b8")}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <p
        className={[
          "m-0 mt-1.5 text-[12px] text-right tabular-nums",
          over ? "text-[#b8534f]" : "text-[var(--meta)]",
        ].join(" ")}
      >
        {text.length} / {max}
      </p>

      <div className="mt-3">
        <div className={ROW}>
          <span className={LABEL}>{t("s.09febb1c95")}</span>
          <select
            className={`flex-1 min-w-0 ${FIELD}`}
            value={voice}
            onChange={(e) => setVoice(e.target.value)}
          >
            {(st.voices || []).map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
            {!st.voices?.length ? <option value="">{t("s.6238bf9ad5")}</option> : null}
          </select>
        </div>
        <div className={ROW}>
          <span className={LABEL}>{t("s.747374775d")}</span>
          <div className="flex-1">
            <RangeBar
              value={rate}
              min={-6}
              max={6}
              step={1}
              onChange={setRate}
              ariaLabel={t("s.747374775d")}
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {rate > 0 ? `+${rate}` : rate}
          </span>
        </div>
        <div className={ROW}>
          <span className={LABEL}>{t("s.bda11a3c2d")}</span>
          <div className="flex-1">
            <RangeBar
              value={pitch}
              min={-12}
              max={12}
              step={1}
              defaultValue={0}
              onChange={setPitch}
              ariaLabel={t("s.bda11a3c2d")}
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {pitch > 0 ? `+${pitch}` : pitch}
          </span>
        </div>
        <div className={ROW}>
          <span className={LABEL}>{t("s.a46919fc8e")}</span>
          <label className="flex items-center gap-2 text-[13px] cursor-pointer">
            <input
              type="checkbox"
              checked={useRvc}
              onChange={(e) => setUseRvc(e.target.checked)}
            />
            {st.model_name || t("s.9bbf6a5dce")}
          </label>
          <span className="text-[12px] text-[var(--meta)]">{t("s.b3009f6985")}</span>
        </div>
      </div>

      {prog ? (
        <div className="mt-4">
          <div className="h-1 w-full overflow-hidden rounded bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
            <div
              className="h-full bg-[var(--accent)] transition-[width] duration-200"
              style={{ width: `${prog.total ? Math.round((prog.done / prog.total) * 100) : 0}%` }}
            />
          </div>
          <p className="m-0 mt-2 text-[12px] text-[var(--meta)]">{prog.message}</p>
        </div>
      ) : null}

      {msg ? (
        <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)] break-all">
          {msg}
        </p>
      ) : null}

      <div className="mt-5 flex justify-end gap-2.5">
        {running ? (
          <Btn onClick={() => void invoke("tts_cancel")}>{t("s.4d0b4688c7")}</Btn>
        ) : (
          <Btn onClick={() => void invoke("tts_reveal")}>{t("s.344a481fa0")}</Btn>
        )}
        <Btn
          primary
          disabled={running || !!blocked || !text.trim() || over}
          onClick={() => void start()}
        >
          {running ? t("s.ec35cdf525") : t("s.74a000b7ac")}
        </Btn>
      </div>
    </>
  );
}
