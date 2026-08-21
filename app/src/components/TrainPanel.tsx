import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn, HelpMark } from "./ui";
import { tip } from "../lib/glossary";
import { openDownloadModels } from "../lib/downloadModels";
import { openHelpSection } from "../lib/helpNav";
import { CkptAdvanced } from "./CkptAdvanced";
import { ErrorNote } from "./ErrorNote";
import { ToolActions, ToolBody } from "./ToolWindow";
import { t } from "../i18n/t";
import { pickPath } from "../lib/nativeDialog";
import { askConfirm } from "../lib/webDialog";
import { auditionVoice } from "../lib/audition";

type Pretrained = { sample_rate: string; ready: boolean };

type Experiment = {
  name: string;
  slices: number;
  features: number;
  resumable: boolean;
  trained: boolean;
  /** 三个阶段各自的产物数。数目对不上就说明上次是中途停的。 */
  f0?: number;
  complete?: boolean;
  preprocess_ok?: number;
  preprocess_failed?: number;
  /** 上次预处理里读不了的文件（最多 20 条），文件名 + 最后一行异常。 */
  preprocess_failed_files?: { name: string; reason: string }[];
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
  disk_free_bytes?: number | null;
  rmvpe_present?: boolean;
  busy?: boolean;
  /** 上一次训练没跑完就断了（壳被强杀/崩了）。busy 时后端一定给 null。 */
  interrupted?: { exp: string; epoch: number; total: number } | null;
};

type DatasetScan = {
  files: number;
  other_files: number;
  total_bytes: number;
  by_ext: Record<string, number>;
  truncated: boolean;
  supported: string[];
};

type Inspect = {
  available: boolean;
  files?: number;
  sampled?: number;
  median_seconds?: number;
  estimated_total_seconds?: number;
  sample_rates?: { rate: number; files: number }[];
  channels?: { channels: number; files: number }[];
  /** 平均响度（dB）。要解码才量得出，ffmpeg 不在就没这一项 —— 缺省≠0。 */
  mean_volume_db?: number;
  /** 静音占比 0..1。同上，缺省不算 0%。 */
  silence_ratio?: number;
};

type Progress = {
  phase: "start" | "stage" | "skip" | "done" | "error";
  stage?: string;
  index?: number;
  total_stages?: number;
  done?: number;
  total?: number;
  message?: string;
  /** worker 写的稳定错误码。壳子是把 worker 那行 JSON 原样 emit 出来的，
      这个字段一直都在，只是以前没人声明、也就没人用。 */
  message_code?: string;
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
  // 选完就数一遍。26.8.20 那位的另一个实验 2038 个文件只切出 3 条，训练照跑，
  // 500 epoch 跑完才发现音色不像 —— 那是预处理的事，但选目录的当下就该知道
  // 这里到底有几个音频。
  const [scan, setScan] = useState<DatasetScan | null>(null);
  const [scanning, setScanning] = useState(false);
  // 体检要解码元数据，比数文件慢，所以是手动触发、可跳过的一步：素材本身不
  // 合适（整首歌、时长太短）跑完 500 轮才发现，同样是几十分钟白费。
  const [inspect, setInspect] = useState<Inspect | null>(null);
  const [inspecting, setInspecting] = useState(false);
  // 预处理失败清单的展开状态。换了实验名不自动收起 —— 名字列表跟着 existing
  // 走，看另一个实验的失败清单同样是「展开」语义。
  const [showFailed, setShowFailed] = useState(false);
  const runInspect = async () => {
    if (!dataset || inspecting) return;
    setInspecting(true);
    try {
      setInspect(await invoke<Inspect>("train_inspect_dataset", { path: dataset }));
    } catch {
      setInspect(null);
    } finally {
      setInspecting(false);
    }
  };
  useEffect(() => {
    if (!dataset) {
      setScan(null);
      setInspect(null);
      return;
    }
    // 换了目录，上一份体检结果就不作数了。
    setInspect(null);
    let alive = true;
    setScanning(true);
    invoke<DatasetScan>("train_scan_dataset", { path: dataset })
      .then((v) => {
        if (alive) setScan(v);
      })
      .catch(() => {
        if (alive) setScan(null);
      })
      .finally(() => {
        if (alive) setScanning(false);
      });
    return () => {
      alive = false;
    };
  }, [dataset]);
  /** 训好的音色放哪。空 = User_Data/models。上次的选择记在配置里。 */
  const [outDir, setOutDir] = useState("");
  const [sr, setSr] = useState("48k");
  const [epochs, setEpochs] = useState(200);
  const [batch, setBatch] = useState(4);
  const batchRef = useRef<HTMLInputElement | null>(null);
  const nameRef = useRef<HTMLInputElement | null>(null);
  // Btn 不转发 ref（它到处都在用，不为这一处改签名），所以套一层 span。
  const startRef = useRef<HTMLSpanElement | null>(null);
  const [resetting, setResetting] = useState(false);
  // 训完之后立刻能听一下像不像。「训完才发现白训」是这个产品里最贵的一种失望，
  // 而「像不像」只有用户自己判断得了 —— 我们能做的是把这一步从「导出、找文件、
  // 拖进播放器」缩成一个按钮。
  const [trained, setTrained] = useState("");
  const [auditing, setAuditing] = useState(false);
  const audition = async () => {
    if (!trained || auditing) return;
    setAuditing(true);
    try {
      const err = await auditionVoice(trained);
      if (err) showErr(t("s.auditionFailed", { v0: err }));
    } finally {
      setAuditing(false);
    }
  };
  // 「补齐并继续」不另起一条代码路径：它就是开始按钮，两条路会分叉。这里只是
  // 把它滚进视野，省得用户在长表单里自己找。
  const focusStart = () => {
    startRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    startRef.current?.querySelector("button")?.focus();
  };
  const resetStages = async () => {
    const exp = name.trim();
    if (!exp || resetting) return;
    if (!(await askConfirm(t("s.trainResetConfirm", { v0: exp })))) return;
    setResetting(true);
    try {
      const r = await invoke<{ freed_mb?: string }>("train_reset_stages", { exp });
      showInfo(t("s.trainResetDone", { a0: exp, a1: `${r?.freed_mb ?? "0"} MB` }));
      await load();
    } catch (e) {
      showErr(String(e));
    } finally {
      setResetting(false);
    }
  };
  // 显存不足时那个按钮要落到实处：滚进视野 + 选中输入框里的数字，用户下一键
  // 就能改。只滚不选的话，他还得自己找、自己划掉旧值。
  const focusBatch = useCallback(() => {
    const el = batchRef.current;
    if (!el) return;
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    el.focus();
    el.select();
  }, []);
  const [batchTouched, setBatchTouched] = useState(false);
  const [f0, setF0] = useState<(typeof F0_OPTS)[number]>("rmvpe");
  const [saveEvery, setSaveEvery] = useState(5);
  const [saveWeights, setSaveWeights] = useState(false);
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  // 配一个能按的按钮要靠错误码，光有文案认不出来是哪一类错。
  const [msgCode, setMsgCode] = useState("");
  // msg 这一格既报错也报成功。「复制完整错误 / 打开日志」只在报错时才该出现，
  // 所以两条路分开走，别让 ErrorNote 去猜。
  const [msgErr, setMsgErr] = useState(false);
  const showErr = (v: string) => {
    setMsgErr(true);
    setMsg(v);
  };
  const showInfo = (v: string) => {
    setMsgErr(false);
    setMsg(v);
  };

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
      showErr(String(e));
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
      const line = ev.payload.message || "";
      if (ev.payload.phase === "error") {
        showErr(line || t("s.60a21a8105"));
        setMsgCode(ev.payload.message_code || "");
      } else if (ev.payload.phase === "skip" && line) {
        // skip 下一拍就是 stage，prog.message 会被盖掉。半份产物那种警告
        // 必须写到 msg 上，否则界面上看着像正常续跑。
        setMsg((prev) => (prev && prev !== line ? `${prev}\n${line}` : line));
      }
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
  // 只有最吃显存的那档就绪：显存不够的用户没有退路，得先告诉他退路在哪。
  const readySrs = (st.pretrained || []).filter((p) => p.ready).map((p) => p.sample_rate);
  const onlyHighSrReady = readySrs.length === 1 && readySrs[0] === "48k";

  // 拦住训练的原因，外加这句话里那个专有名词的解释（渲染成一个小问号）。
  const needRmvpe = f0 === "rmvpe" && !st.rmvpe_present;
  /**
   * 开始之前的检查清单。
   *
   * 以前这里是一条 if-else 链，只报第一个拦路的：用户改掉它，点一下，又冒出
   * 第二个。而且全都一个级别 —— 「没装运行时」和「素材可能偏少」长得一样，
   * 用户不知道哪个必须先解决。
   *
   * 现在分两级：must 会禁用开始按钮，should 不会。每条尽量自带一个能按的东西
   * —— 只把失败从「训练跑到一半」提前到「点按钮之前」是不够的，那只是换了个
   * 地方失败。
   */
  const goDownloads = () => openDownloadModels({ filter: "train" });
  const repick = () => {
    void pickPath<string | null>(
      "train_pick_dataset",
      undefined,
      t("s.pickBusyFolder"),
    ).then((p) => p && setDataset(p));
  };
  const focusName = () => {
    nameRef.current?.focus();
    nameRef.current?.select();
  };

  type Check = {
    level: "must" | "should";
    text: string;
    term?: string;
    action?: { label: string; run: () => void };
  };
  const checks: Check[] = [];
  const dl = { label: t("s.0c593a479c"), run: goDownloads };
  if (!st.runtime_ready) {
    checks.push({ level: "must", text: t("s.bc45fc14b1"), term: t("s.cef8154370"), action: dl });
  } else if (!st.worker_present || !st.mute_present) {
    checks.push({ level: "must", text: t("s.946a92f5a2"), action: dl });
  } else {
    if (!st.hubert_present) {
      checks.push({ level: "must", text: t("s.e700c7ba47"), term: t("s.b269c54674"), action: dl });
    }
    if (needRmvpe) {
      checks.push({ level: "must", text: t("s.trainRmvpeMissing"), action: dl });
    }
    if (!st.nvidia) {
      // 这条没有动作按钮：换显卡不是软件能代劳的事，给一个点了没用的按钮更伤。
      checks.push({ level: "must", text: t("s.8f5fdb1c8a"), term: "DirectML" });
    }
    if (!srReady) {
      checks.push({
        level: "must",
        text: t("s.b453debe2c", { v0: sr }),
        term: t("s.4bdd408f42"),
        action: dl,
      });
    }
  }
  // 数据集这两条只在真选了目录之后才谈得上；续跑不需要数据集。
  if (dataset && scan && !scanning) {
    if (scan.files === 0 && !resume) {
      checks.push({
        level: "must",
        text: t("s.trainCheckNoAudio"),
        action: { label: t("s.trainCheckRepick"), run: repick },
      });
    } else if (scan.files > 0 && scan.files < 10) {
      checks.push({ level: "should", text: t("s.trainCheckFewFiles", { v0: scan.files }) });
    }
    // 中间产物（切片 + 音高 + 特征）大致是源素材的三倍上下。给的是量级，
    // 不是承诺 —— 所以文案写「预计需要 … 以上」，不写具体数字对账。
    const need = scan.total_bytes * 3;
    const free = st.disk_free_bytes;
    if (typeof free === "number" && free > 0 && need > 0 && free < need) {
      checks.push({
        level: "must",
        text: t("s.trainCheckDisk", { a0: humanBytes(free), a1: humanBytes(need) }),
      });
    }
  }
  if (st.suggested_batch && batch > st.suggested_batch) {
    checks.push({
      level: "should",
      text: t("s.trainCheckBatch", { a0: String(batch), a1: String(st.suggested_batch) }),
      action: { label: t("s.errActBatch"), run: focusBatch },
    });
  }
  if (existing && !resume) {
    checks.push({
      level: "should",
      text: t("s.trainCheckNameTaken", { v0: name.trim() }),
      action: { label: t("s.trainCheckRename"), run: focusName },
    });
  }
  const mustFix = checks.some((c) => c.level === "must");

  const start = async () => {
    if (runningRef.current) return;
    showInfo("");
    setMsgCode("");
    setTrained("");
    setProg(null);
    setEta("");
    epochMarks.current = [];
    runningRef.current = true;
    setRunning(true);
    try {
      const r = await invoke<{ weights?: string; leftover_bytes?: number }>("train_start", {
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
      setTrained(String(r?.weights ?? ""));
      const leftover = r?.leftover_bytes ?? 0;
      showInfo(
        t("s.2b30598b60", { v0: r.weights ?? "" }) +
          // 训练刚跑完是用户唯一会读这句话的时刻。只报数，不自动删 —— 中间产物
          // 还留着才能续训。
          (leftover > 0 ? `\n${t("s.trainLeftover", { v0: humanBytes(leftover) })}` : ""),
      );
    } catch (e) {
      showErr(String(e));
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

        {checks.length ? (
          <ul className="m-0 mb-4 list-none p-0">
            {checks.map((c, i) => (
              <li key={i} className="relative py-2 first:pt-0">
                {i > 0 ? (
                  <div
                    aria-hidden
                    className="absolute top-0 left-0 right-0 h-px bg-[var(--hairline)]"
                  />
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  {/* 等宽的级别标签，不靠颜色分级 —— 一片红黄看不出该先做哪个。 */}
                  <span className="font-mono text-[11px] text-[var(--meta)] shrink-0">
                    {c.level === "must" ? t("s.trainCheckMust") : t("s.trainCheckShould")}
                  </span>
                  <p
                    className={
                      "m-0 flex items-center gap-1.5 text-[13px] " +
                      (c.level === "must" ? "text-[#b8534f]" : "text-[var(--ink-muted)]")
                    }
                  >
                    {c.text}
                    {c.term ? <HelpMark title={tip(c.term)} /> : null}
                  </p>
                  {c.action ? (
                    <Btn onClick={c.action.run}>{c.action.label}</Btn>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="mb-3 flex justify-end">
            <Btn onClick={goDownloads}>{t("s.aac4f88e84")}</Btn>
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
          {dataset && scan && scan.files > 0 ? (
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Btn onClick={() => void runInspect()} busy={inspecting} disabled={inspecting}>
                {inspecting ? t("s.trainInspecting") : t("s.trainInspect")}
              </Btn>
              {inspect && inspect.available && (inspect.sampled ?? 0) > 0 ? (
                <span className="text-[12px] text-[var(--meta)]">
                  {t("s.trainInspectResult", {
                    a0: String(inspect.sampled),
                    a1: humanSeconds(inspect.estimated_total_seconds ?? 0),
                    a2: humanSeconds(inspect.median_seconds ?? 0),
                  })}
                </span>
              ) : null}
            </div>
          ) : null}
          {inspect && inspect.available && (inspect.sampled ?? 0) > 0 ? (
            <div className="mb-2 flex flex-col gap-1">
              {(inspect.estimated_total_seconds ?? 0) < 600 ? (
                <p className="m-0 text-[12px] text-[var(--ink-muted)] leading-snug">
                  {t("s.trainInspectShort")}
                </p>
              ) : null}
              {(inspect.median_seconds ?? 0) > 60 ? (
                <p className="m-0 text-[12px] text-[var(--ink-muted)] leading-snug">
                  {t("s.trainInspectLong", {
                    v0: humanSeconds(inspect.median_seconds ?? 0),
                  })}
                </p>
              ) : null}
              {(inspect.sample_rates?.length ?? 0) > 1 ? (
                <p className="m-0 text-[12px] text-[var(--meta)] leading-snug">
                  {t("s.trainInspectMixedRate", {
                    v0: (inspect.sample_rates ?? [])
                      .map((r) => `${Math.round(r.rate / 1000)}k×${r.files}`)
                      .join(" / "),
                  })}
                </p>
              ) : null}
              {/* 阈值只给相对判断用的「值得看一眼」线，不是承诺：偏轻到什么程度
                  该重录，取决于用户能接受什么质量。 */}
              {inspect.mean_volume_db != null && inspect.mean_volume_db < -35 ? (
                <p className="m-0 text-[12px] text-[var(--ink-muted)] leading-snug">
                  {t("s.trainInspectQuiet", {
                    v0: inspect.mean_volume_db.toFixed(1),
                  })}
                </p>
              ) : null}
              {(inspect.silence_ratio ?? 0) > 0.6 ? (
                <p className="m-0 text-[12px] text-[var(--ink-muted)] leading-snug">
                  {t("s.trainInspectSilent", {
                    v0: Math.round((inspect.silence_ratio ?? 0) * 100),
                  })}
                </p>
              ) : null}
              {(inspect.channels?.length ?? 0) > 1 ? (
                <p className="m-0 text-[12px] text-[var(--meta)] leading-snug">
                  {t("s.trainInspectMixedCh", {
                    v0: (inspect.channels ?? [])
                      .map((c) => `${c.channels}ch×${c.files}`)
                      .join(" / "),
                  })}
                </p>
              ) : null}
            </div>
          ) : null}
          {dataset ? (
            <p
              className={
                "m-0 mb-2 text-[12px] leading-snug " +
                (scan && scan.files === 0
                  ? "text-[var(--ink-muted)] font-semibold"
                  : "text-[var(--meta)]")
              }
            >
              {scanning || !scan
                ? t("s.trainDatasetScanning")
                : scan.files === 0
                  ? t("s.trainDatasetEmpty", { v0: scan.supported.join(" / ") })
                  : t("s.trainDatasetFound", {
                      a0: String(scan.files),
                      a1: humanBytes(scan.total_bytes),
                    })}
            </p>
          ) : null}
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
              ref={nameRef}
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
          {/* 只给相对判断，不给「48k 需要 8 GB」这种绝对承诺 —— 那取决于批大小、
              数据集长度和显卡，说死了就会有人拿着它来对账。 */}
          <p className="m-0 mb-2 text-[12px] text-[var(--meta)] leading-snug">
            {t("s.trainSrCost")}
            {onlyHighSrReady ? ` ${t("s.trainSrOnly48")}` : ""}
          </p>
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
              ref={batchRef}
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
          <div className="mt-3">
            <p className="m-0 text-[12.5px] text-[var(--meta)]">
              {t("s.0340e37d88", {
                v0: name.trim(),
                v1: existing?.slices ?? 0,
              })}
            </p>
            {/* 三个阶段的数目摊开写。以前只有一个「可续跑」的布尔值，用户看不出
                上次到底做完没有 —— 而没做完时「继续」会比他预期的慢几分钟，
                他会以为是更新之后变慢了。 */}
            <p className="m-0 mt-1 font-mono text-[11.5px] text-[var(--meta)]">
              {t("s.trainStages", {
                a0: String(existing?.slices ?? 0),
                a1: String(existing?.f0 ?? 0),
                a2: String(existing?.features ?? 0),
              })}
            </p>
            {existing && existing.complete === false ? (
              <p className="m-0 mt-1 text-[12px] text-[var(--ink-muted)] leading-snug">
                {t("s.trainStagesIncomplete")}
              </p>
            ) : null}
            {existing && (existing.preprocess_failed ?? 0) > 0 ? (
              <p className="m-0 mt-1 text-[12px] text-[var(--ink-muted)] leading-snug">
                {t("s.trainPreprocessFailed", {
                  a0: String(existing.preprocess_failed),
                  a1: String(existing.preprocess_ok ?? 0),
                })}
              </p>
            ) : null}
            {/* 哪些文件坏了、为什么坏 —— 只报条数的话，用户清完坏文件还得再跑
                一遍预处理才知道清没清干净。清单来自 preprocess.log，上限 20 条。 */}
            {existing && (existing.preprocess_failed_files?.length ?? 0) > 0 ? (
              <div className="mt-1">
                <Btn
                  onClick={() => setShowFailed((v) => !v)}
                  className="!py-1 !px-2 text-[12px]"
                >
                  {showFailed
                    ? t("s.trainFailedHide")
                    : t("s.trainFailedList", {
                        v0: String(existing.preprocess_failed_files?.length ?? 0),
                      })}
                </Btn>
                {showFailed ? (
                  <ul className="m-0 mt-1.5 max-h-[120px] list-none overflow-auto p-0">
                    {(existing.preprocess_failed_files ?? []).map((f) => (
                      <li
                        key={f.name}
                        className="py-0.5 text-[11.5px] text-[var(--meta)] break-all leading-snug"
                      >
                        <span className="font-medium text-[var(--ink-muted)]">{f.name}</span>
                        {" — "}
                        {f.reason}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-2">
              {/* 「补齐并继续」就是现在的开始按钮，这里只是把话说清楚，不另开一条
                  代码路径 —— 两条路会分叉。 */}
              <Btn onClick={focusStart}>{t("s.trainResumeFill")}</Btn>
              <Btn
                onClick={() => void resetStages()}
                busy={resetting}
                disabled={running || resetting}
              >
                {t("s.trainResumeReset")}
              </Btn>
            </div>
          </div>
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

        {trained && !running ? (
          <div className="mt-3">
            <Btn onClick={() => void audition()} busy={auditing} disabled={auditing}>
              {auditing ? t("s.auditionBusy") : t("s.auditionBtn")}
            </Btn>
          </div>
        ) : null}

        {msg ? (
          <ErrorNote
            text={msg}
            error={msgErr}
            code={msgCode}
            extraAction={
              // 显存不足只有一条路能走：把批大小调小。那个输入框就在这一页上，
              // 所以这条不进 CODE_ACTIONS 表 —— 表里只放跨窗口也成立的动作。
              msgCode === "train.oom"
                ? { label: t("s.errActBatch"), run: focusBatch }
                : null
            }
          />
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
          <span ref={startRef}>
          <Btn
            primary
            busy={running}
            disabled={running || mustFix || !name.trim() || (!dataset && !resume)}
            onClick={() => void start()}
          >
            {running ? t("s.3e6b1657c7") : resume ? t("s.3166554c46") : t("s.be24590d21")}
          </Btn>
          </span>
        </div>
      </ToolActions>
    </ToolBody>
  );
}

/** 数据集体积。用户看的是量级，不是精确字节数。 */
function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/** 秒数写成人话。用户看的是量级，不是精确到秒。单位跟着语言走。 */
function humanSeconds(n: number): string {
  if (n < 60) return t("s.unitSeconds", { v0: Math.round(n) });
  if (n < 3600) return t("s.unitMinutes", { v0: Math.round(n / 60) });
  return t("s.unitHours", { v0: (n / 3600).toFixed(1) });
}
