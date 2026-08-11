import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { RangeBar } from "./controls";
import { SegmentControl } from "./SegmentControl";
import { ToolBody } from "./ToolWindow";
import { t } from "../i18n/t";

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
};

/** 批量转换里没转出来的那几个：哪个文件、为什么。 */
type Skipped = {
  file: string;
  name: string;
  reason: string;
};

const ROW = "flex items-center gap-3 py-2.5";
const LABEL = "w-[86px] shrink-0 text-[13px]";
const PATH =
  "flex-1 min-w-0 truncate text-[12.5px] text-[var(--ink-muted)] font-mono";
const FIELD =
  "rounded-[var(--rs)] border border-[var(--hairline)] bg-transparent px-2 py-1.5 text-[13px]";

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

function StsSection() {
  const [st, setSt] = useState<StsStatus>({});
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [pitch, setPitch] = useState(0);
  const [f0method, setF0method] = useState("rmvpe");
  const [indexRate, setIndexRate] = useState(0.75);
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  // 批量里转失败被跳过的文件。整批不再因为一个坏文件中止，所以得有地方交代
  // 到底是哪几个没转出来。
  const [skipped, setSkipped] = useState<Skipped[]>([]);
  const [running, setRunning] = useState(false);
  const runningRef = useRef(false);

  const load = async () => {
    try {
      const s = await invoke<StsStatus>("sts_status");
      setSt(s);
      if (s.pitch != null) setPitch(Number(s.pitch));
      if (s.f0method) setF0method(String(s.f0method));
      if (s.index_rate != null) setIndexRate(Number(s.index_rate));
      if (!output && s.out_dir) setOutput(String(s.out_dir));
    } catch (e) {
      setMsg(String(e));
    }
  };

  useEffect(() => {
    void load();
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<Progress>("sts-progress", (ev) => {
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

  const blocked = !st.runtime_ready
    ? t("s.bc45fc14b1")
    : st.engine_core_ready === false
      ? t("s.156ff9271b", {
          v0: (st.engine_core_missing || []).join("、") || "hubert/rmvpe",
        })
      : !st.worker_present
        ? t("s.84b7d7b6b0")
        : !st.model_path
          ? t("s.03877888b6")
          : "";

  const start = async () => {
    if (runningRef.current) return;
    // 离线转换要独占显存，后端会先杀掉实时变声。那是用户正在用的东西，不能
    // 不打招呼就停——现问一次状态，别拿进面板时的旧值判断。
    try {
      const now = await invoke<StsStatus>("sts_status");
      if (now.worker_alive && !window.confirm(t("s.stsStopWorkerConfirm"))) return;
    } catch {
      // 状态问不到就照原样往下走，后端还会再判一次。
    }
    setMsg("");
    setProg(null);
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
      });
      const ok = r.files?.length ?? 0;
      const bad = r.skipped ?? [];
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

  const pct = prog?.total ? Math.round((prog.done / prog.total) * 100) : 0;

  return (
    <>
      {blocked ? (
        <p className="m-0 mb-4 text-[13px] text-[#b8534f]">{blocked}</p>
      ) : (
        <p className="m-0 mb-3 text-[12.5px] text-[var(--meta)]">
          {t("s.6c415e91bb", { v0: st.model_name || "—" })}
          {st.index_path ? t("s.0ca99fa9f1") : ""}
        </p>
      )}

      <div className="border-t border-[var(--hairline)]">
        <div className={ROW}>
          <span className={LABEL}>{t("s.e8850440f2")}</span>
          <span className={PATH}>{input || t("s.245826185c")}</span>
          <Btn
            onClick={() => {
              void invoke<string | null>("sts_pick_input", { folder: false }).then(
                (p) => p && setInput(p),
              );
            }}
          >{t("s.49deaf7da2")}</Btn>
          <Btn
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
          <span className={LABEL}>{t("s.3579ac474b")}</span>
          <select
            className={`flex-1 min-w-0 ${FIELD}`}
            value={f0method}
            onChange={(e) => setF0method(e.target.value)}
          >
            {["rmvpe", "fcpe", "harvest", "pm", "crepe"].map((m) => (
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
      </div>

      {prog ? (
        <div className="mt-4">
          <div className="h-1 w-full overflow-hidden rounded bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
            <div
              className="h-full bg-[var(--accent)] transition-[width] duration-200"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="m-0 mt-2 text-[12px] text-[var(--meta)]">
            {prog.message} {prog.phase === "run" ? `${pct}%` : ""}
          </p>
        </div>
      ) : null}

      {msg ? (
        <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)] break-all">
          {msg}
        </p>
      ) : null}

      {skipped.length ? (
        <div className="mt-3 border-t border-[var(--hairline)] pt-2">
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
          <Btn onClick={() => void invoke("sts_reveal")}>{t("s.344a481fa0")}</Btn>
        )}
        <Btn
          primary
          disabled={running || !!blocked || !input}
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
        <p className="m-0 mb-4 text-[13px] text-[#b8534f]">{blocked}</p>
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

      <div className="mt-3 border-t border-[var(--hairline)]">
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
