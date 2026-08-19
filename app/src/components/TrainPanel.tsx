import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn, HelpMark } from "./ui";
import { tip } from "../lib/glossary";
import { openDownloadModels } from "../lib/downloadModels";
import { openHelpSection } from "../lib/helpNav";
import { CkptAdvanced } from "./CkptAdvanced";
import { ToolActions, ToolBody } from "./ToolWindow";
import { t } from "../i18n/t";
import { pickPath } from "../lib/nativeDialog";

type Pretrained = { sample_rate: string; ready: boolean };

type Experiment = {
  name: string;
  slices: number;
  features: number;
  resumable: boolean;
  trained: boolean;
};

type Status = {
  runtime_ready?: boolean;
  worker_present?: boolean;
  mute_present?: boolean;
  hubert_present?: boolean;
  nvidia?: boolean;
  pretrained?: Pretrained[];
  experiments?: Experiment[];
  suggested_batch?: number;
  rmvpe_present?: boolean;
  busy?: boolean;
  /** 上一次训练没跑完就断了（壳被强杀/崩了）。busy 时后端一定给 null。 */
  interrupted?: { exp: string; epoch: number; total: number } | null;
};

type Progress = {
  phase: "start" | "stage" | "skip" | "done" | "error";
  stage?: string;
  index?: number;
  total_stages?: number;
  done?: number;
  total?: number;
  message?: string;
};

function stageName(id: string): string {
  const map: Record<string, string> = {
    preprocess: t("s.1a37ffe775"),
    f0: t("s.bda11a3c2d"),
    feature: t("s.672c1db9d8"),
    train: t("s.796e01d5af"),
    index: t("s.79f9110607"),
  };
  return map[id] || id;
}

/** 最多留这么多轮的到达时刻。太少会被偶发的一轮抖动带偏，太多则在
 *  显卡降频之后半天跟不上真实速度。 */
const ETA_WINDOW = 8;

/**
 * 估算剩余时间。
 *
 * 训练轮数默认 200，每轮八到十秒，进度条每九秒才动 0.5% —— 肉眼就是不动。
 * 26.8.18 的用户等了十分钟以为死机，去任务管理器把程序结束了。给个「约剩
 * 25 分钟」，这一整类误判就没了。
 *
 * 取中位数而不是平均：预处理刚结束那几轮、以及显卡被别的程序抢走的那几轮
 * 会明显偏长，平均值会被它们拽着不放。
 */
export function trackEta(marks: { at: number; done: number }[], p: Progress): string {
  if (p.stage !== "train" || !p.total || !p.done) {
    // 不是训练阶段（预处理/提取音高/特征）就不猜 —— 那几步各自的耗时
    // 规律完全不同，硬套只会给出一个错得离谱的数。
    return "";
  }
  const last = marks[marks.length - 1];
  if (last && p.done <= last.done) return "";
  marks.push({ at: Date.now(), done: p.done });
  if (marks.length > ETA_WINDOW) marks.splice(0, marks.length - ETA_WINDOW);
  if (marks.length < 3) return "";
  const per: number[] = [];
  for (let i = 1; i < marks.length; i++) {
    const dt = marks[i].at - marks[i - 1].at;
    const dn = marks[i].done - marks[i - 1].done;
    if (dt > 0 && dn > 0) per.push(dt / dn);
  }
  if (!per.length) return "";
  per.sort((a, b) => a - b);
  const mid = per[Math.floor(per.length / 2)];
  const left = Math.max(0, p.total - p.done);
  return humanLeft(Math.round((mid * left) / 1000));
}

/** 秒数说成人话。不到一分钟就别报数字了，写「快好了」。 */
export function humanLeft(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return "";
  if (sec < 60) return t("s.trainEtaSoon");
  const mins = Math.round(sec / 60);
  if (mins < 60) return t("s.trainEtaMin", { v0: mins });
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? t("s.trainEtaHourMin", { v0: h, v1: m }) : t("s.trainEtaHour", { v0: h });
}

const ROW = "flex items-center gap-3 py-2.5";
/**
 * 表单左边那一列。
 *
 * 宽度原来是照着中文标签配的，四个汉字五十来像素刚好塞得下。八种语言里
 * 这就不成立了：法语的「Enregistrer les modèles dans」有两百多像素，会在
 * 词中间断成三行；连中文的「导出格式」加上后面那个问号图标也已经超了。
 * 放宽到能装下绝大多数语言，剩下几个特别长的折成两行，配 leading-tight
 * 看起来是有意为之，而不是挤坏了。
 */
const LABEL = "w-[112px] shrink-0 text-[13px] leading-tight";
const PATH =
  "flex-1 min-w-0 truncate text-[12.5px] text-[var(--ink-muted)] font-mono";
const FIELD =
  "rounded-[var(--rs)] border border-[var(--hairline)] bg-transparent px-2 py-1.5 text-[13px]";

const F0_OPTS = ["rmvpe", "harvest", "pm"] as const;

/**
 * 训练音色。
 *
 * 原版一键训练那条链都在：素材、名字、采样率、轮数、批次、音高算法、
 * 保存间隔、中途出小模型。多卡拆分和缓存进显存仍不开放——家用机开了
 * 只会炸显存。
 */
export function TrainPanel() {
  const [st, setSt] = useState<Status>({});
  const [name, setName] = useState("");
  const [dataset, setDataset] = useState("");
  /** 训好的音色放哪。空 = User_Data/models。上次的选择记在配置里。 */
  const [outDir, setOutDir] = useState("");
  const [sr, setSr] = useState("48k");
  const [epochs, setEpochs] = useState(200);
  const [batch, setBatch] = useState(4);
  const [batchTouched, setBatchTouched] = useState(false);
  const [f0, setF0] = useState<(typeof F0_OPTS)[number]>("rmvpe");
  const [saveEvery, setSaveEvery] = useState(5);
  const [saveWeights, setSaveWeights] = useState(false);
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  const [running, setRunning] = useState(false);
  const [adv, setAdv] = useState(false);
  // 进阶设置的开关在底栏、内容在正文末尾。展开时把内容滚进视野，不然用户点完
  // 按钮，画面上什么都不会变 —— 新长出来的那块在滚动区外面。
  const advRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (adv) advRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [adv]);
  const runningRef = useRef(false);
  /** 每轮到达的时刻，用来估剩余时间。只留最近若干个。 */
  const epochMarks = useRef<{ at: number; done: number }[]>([]);
  const [eta, setEta] = useState("");

  const load = async () => {
    try {
      const s = await invoke<Status>("train_status");
      setSt(s);
      if (!batchTouched && s.suggested_batch && s.suggested_batch > 0) {
        setBatch(s.suggested_batch);
      }
    } catch (e) {
      setMsg(String(e));
    }
  };

  useEffect(() => {
    void load();
    // 上次选的存放目录记在配置里 —— 重开面板要回到用户上次的选择，
    // 而不是每次都退回默认，害他每训一个音色重选一遍。
    void invoke<string>("train_output_dir")
      .then((d) => setOutDir(d || ""))
      .catch(() => {});
    // listen() 是异步的，弹窗在它 resolve 之前关掉就会把注销句柄丢掉，
    // 每开一次泄漏一个监听。和 SeparateDialog 一样的处理。
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<Progress>("train-progress", (ev) => {
      setProg(ev.payload);
      setEta(trackEta(epochMarks.current, ev.payload));
      if (ev.payload.phase === "error") setMsg(ev.payload.message || t("s.60a21a8105"));
    }).then((fn) => {
      if (disposed) fn();
      else un = fn;
    });
    return () => {
      disposed = true;
      un?.();
    };
  }, []);

  const existing = st.experiments?.find((e) => e.name === name.trim());
  // 有切片就能续跑，预处理是最慢的一步（几十分钟），能跳过就跳过。
  const resume = !!existing?.resumable;
  const srReady = st.pretrained?.find((p) => p.sample_rate === sr)?.ready ?? false;

  // 拦住训练的原因，外加这句话里那个专有名词的解释（渲染成一个小问号）。
  const needRmvpe = f0 === "rmvpe" && !st.rmvpe_present;
  const needPretrained =
    !!st.runtime_ready &&
    !!st.worker_present &&
    !!st.mute_present &&
    !!st.hubert_present &&
    !!st.nvidia &&
    !srReady;
  const blocked: { text: string; term?: string } = !st.runtime_ready
    ? { text: t("s.bc45fc14b1"), term: t("s.cef8154370") }
    : !st.worker_present || !st.mute_present
      ? { text: t("s.946a92f5a2") }
      : !st.hubert_present
        ? { text: t("s.e700c7ba47"), term: t("s.b269c54674") }
        : needRmvpe
          ? { text: t("s.trainRmvpeMissing") }
          : !st.nvidia
            ? {
                text: t("s.8f5fdb1c8a"),
                term: "DirectML",
              }
            : !srReady
              ? {
                  text: t("s.b453debe2c", { v0: sr }),
                  term: t("s.4bdd408f42"),
                }
              : { text: "" };

  const start = async () => {
    if (runningRef.current) return;
    setMsg("");
    setProg(null);
    setEta("");
    epochMarks.current = [];
    runningRef.current = true;
    setRunning(true);
    try {
      const r = await invoke<{ weights?: string }>("train_start", {
        req: {
          exp: name.trim(),
          dataset,
          sample_rate: sr,
          total_epoch: epochs,
          batch_size: batch,
          save_every: saveEvery,
          f0_method: f0,
          resume,
          save_every_weights: saveWeights,
          output_dir: outDir,
        },
      });
      setMsg(t("s.2b30598b60", { v0: r.weights ?? "" }));
    } catch (e) {
      setMsg(String(e));
    } finally {
      runningRef.current = false;
      setRunning(false);
      // 成败都回读一次：训好的音色要出现在列表里，失败/取消的那次也要
      // 让「上次中断了」这条提示跟着盘上的实际情况走。
      void load();
    }
  };

  const pct = prog?.total ? Math.round(((prog.done ?? 0) / prog.total) * 100) : 0;
  const stageLabel = prog?.stage ? stageName(prog.stage) : "";
  const stepLine =
    prog?.index && prog?.total_stages
      ? t("s.588a754143", { v0: prog.index, v1: prog.total_stages, v2: stageLabel })
      : "";

  return (
    <ToolBody>
        <div className="mb-1 flex items-center justify-between gap-2">
          <h3 className="m-0 text-[17px] font-semibold">{t("s.ba65bd5595")}</h3>
          <Btn onClick={() => openHelpSection("train")}>{t("s.trainOpenHelp")}</Btn>
        </div>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)]">{t("s.42667034ec")}</p>

        {blocked.text ? (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <p className="m-0 text-[13px] text-[#b8534f] flex items-center gap-1.5">
              {blocked.text}
              {blocked.term ? <HelpMark title={tip(blocked.term)} /> : null}
            </p>
            {needPretrained || !st.hubert_present || needRmvpe ? (
              <Btn onClick={() => openDownloadModels({ filter: "train" })}>{t("s.0c593a479c")}</Btn>
            ) : null}
          </div>
        ) : (
          <div className="mb-3 flex justify-end">
            <Btn onClick={() => openDownloadModels({ filter: "train" })}>{t("s.aac4f88e84")}</Btn>
          </div>
        )}

        <div className="border-t border-[var(--hairline)]">
          <div className={ROW}>
            <span className={LABEL}>{t("s.10c5cf2954")}</span>
            <span className={PATH}>{dataset || t("s.53e2db7016")}</span>
            <Btn
              onClick={() => {
                void pickPath<string | null>("train_pick_dataset", undefined, t("s.pickBusyFolder")).then(
                  (p) => p && setDataset(p),
                );
              }}
            >{t("s.70b208202c")}</Btn>
          </div>
          <div className={ROW}>
            <span className={LABEL}>{t("s.trainOutDir")}</span>
            <span className={PATH} title={outDir || t("s.trainOutDefault")}>
              {outDir || t("s.trainOutDefault")}
            </span>
            {outDir ? (
              <Btn onClick={() => setOutDir("")}>{t("s.trainOutReset")}</Btn>
            ) : null}
            <Btn
              onClick={() => {
                void pickPath<string | null>("train_pick_output_dir", undefined, t("s.pickBusyFolder")).then(
                  (p) => p && setOutDir(p),
                );
              }}
            >{t("s.70b208202c")}</Btn>
          </div>
          <p className="m-0 mb-2 text-[12px] text-[var(--meta)] leading-snug">
            {t("s.trainOutHint")}
          </p>
          <div className={ROW}>
            <span className={LABEL}>{t("s.4eea655d6f")}</span>
            <input
              className={`flex-1 min-w-0 ${FIELD}`}
              value={name}
              placeholder={t("s.b27dd877b1")}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className={ROW}>
            <span className={`${LABEL} flex items-center gap-1.5`}>{t("s.ab4dae189d")}<HelpMark title={tip(t("s.4bdd408f42"))} />
            </span>
            <select
              className={FIELD}
              value={sr}
              onChange={(e) => setSr(e.target.value)}
            >
              {(st.pretrained || [{ sample_rate: "48k", ready: false }]).map((p) => (
                <option key={p.sample_rate} value={p.sample_rate}>
                  {p.sample_rate}
                  {p.ready ? "" : t("s.3d19649847")}
                </option>
              ))}
            </select>
            <span className="text-[12px] text-[var(--meta)]">{t("s.f9786f5b73")}</span>
          </div>
          <div className={ROW}>
            <span className={LABEL}>{t("s.61fdf63b84")}</span>
            <input
              className={`w-[100px] ${FIELD}`}
              type="number"
              min={1}
              max={1000}
              value={epochs}
              onChange={(e) => setEpochs(Number(e.target.value) || 1)}
            />
            <span className="text-[12px] text-[var(--meta)]">{t("s.c7acce2c4c")}</span>
          </div>
          <div className={ROW}>
            <span className={`${LABEL} flex items-center gap-1.5`}>
              {t("s.trainBatch")}
              <HelpMark title={t("s.trainBatchHint")} />
            </span>
            <input
              className={`w-[100px] ${FIELD}`}
              type="number"
              min={1}
              max={40}
              value={batch}
              onChange={(e) => {
                setBatchTouched(true);
                setBatch(Math.max(1, Number(e.target.value) || 1));
              }}
            />
            {st.suggested_batch ? (
              <span className="text-[12px] text-[var(--meta)]">
                {t("s.trainSuggested", { v0: st.suggested_batch })}
              </span>
            ) : null}
          </div>
          <div className={ROW}>
            <span className={`${LABEL} flex items-center gap-1.5`}>
              {t("s.trainF0")}
              <HelpMark title={t("s.trainF0Hint")} />
            </span>
            <select
              className={FIELD}
              value={f0}
              onChange={(e) => setF0(e.target.value as (typeof F0_OPTS)[number])}
            >
              {F0_OPTS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div className={ROW}>
            <span className={`${LABEL} flex items-center gap-1.5`}>
              {t("s.trainSaveEvery")}
              <HelpMark title={t("s.trainSaveEveryHint")} />
            </span>
            <input
              className={`w-[100px] ${FIELD}`}
              type="number"
              min={1}
              max={50}
              value={saveEvery}
              onChange={(e) => setSaveEvery(Math.max(1, Number(e.target.value) || 5))}
            />
          </div>
          <div className={ROW}>
            <label className="flex items-center gap-2 text-[13px] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={saveWeights}
                onChange={(e) => setSaveWeights(e.target.checked)}
                className="accent-[var(--accent)]"
              />
              {t("s.trainSaveWeights")}
              <HelpMark title={t("s.trainSaveWeightsHint")} />
            </label>
          </div>
        </div>

        {st.experiments && st.experiments.length > 0 ? (
          <div className="mt-3">
            <div className="text-[12px] text-[var(--meta)] mb-1.5">{t("s.trainExps")}</div>
            <div className="flex flex-wrap gap-1.5">
              {st.experiments.map((e) => (
                <button
                  key={e.name}
                  type="button"
                  className={[
                    "text-[12px] px-2 py-1 rounded-[var(--rs)] border-0 cursor-pointer",
                    e.name === name.trim()
                      ? "bg-[var(--accent-soft)] text-[var(--ink)]"
                      : "bg-[color-mix(in_srgb,var(--ink)_6%,transparent)] text-[var(--ink-muted)]",
                  ].join(" ")}
                  onClick={() => setName(e.name)}
                >
                  {e.name}
                  {e.trained ? " · pth" : e.resumable ? ` · ${e.slices}` : ""}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {resume ? (
          <p className="m-0 mt-3 text-[12.5px] text-[var(--meta)]">
            {t("s.0340e37d88", {
              v0: name.trim(),
              v1: existing?.slices ?? 0,
            })}
          </p>
        ) : null}

        {!prog && st.interrupted ? (
          <p className="m-0 mt-3 text-[12.5px] text-[var(--meta)]">
            {t("s.trainInterrupted", {
              v0: st.interrupted.exp,
              v1: st.interrupted.epoch,
              v2: st.interrupted.total,
            })}
          </p>
        ) : null}

        {prog ? (
          <div className="mt-4">
            <div className="h-1 w-full overflow-hidden rounded bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
              <div
                className="h-full bg-[var(--accent)] transition-[width] duration-200"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="m-0 mt-2 text-[12px] text-[var(--meta)]">
              {stepLine ? `${stepLine} · ` : ""}
              {prog.message}
              {prog.phase === "stage" ? ` ${pct}%` : ""}
              {eta ? ` · ${eta}` : ""}
            </p>
          </div>
        ) : null}

        {msg ? (
          <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)] break-all">
            {msg}
          </p>
        ) : null}

        {running ? (
          <p className="m-0 mt-3 text-[12px] text-[var(--meta)]">{t("s.8a5ef195d6")}</p>
        ) : null}

        {/* 进阶设置的按钮进了底栏，展开的内容留在这里 —— 那是一整块表单，塞进
            操作栏没地方放。展开时把它滚进视野，否则按钮在窗口底部、内容在正文
            末尾，用户点完会以为什么都没发生。 */}
        {adv ? (
          <div ref={advRef} className="mt-4">
            <CkptAdvanced />
          </div>
        ) : null}

      <ToolActions>
        <Btn onClick={() => setAdv((v) => !v)}>
          {adv ? t("s.ckptAdvancedHide") : t("s.ckptAdvanced")}
        </Btn>
        <div className="ml-auto flex items-center gap-2.5">
          {running ? (
            <Btn onClick={() => void invoke("train_cancel")}>{t("s.44e681a374")}</Btn>
          ) : null}
          <Btn
            primary
            disabled={running || !!blocked.text || !name.trim() || (!dataset && !resume)}
            onClick={() => void start()}
          >
            {running ? t("s.3e6b1657c7") : resume ? t("s.3166554c46") : t("s.be24590d21")}
          </Btn>
        </div>
      </ToolActions>
    </ToolBody>
  );
}
