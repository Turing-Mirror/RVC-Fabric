import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { dropListen } from "../lib/tauriListen";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Btn, HelpMark } from "./ui";
import { ErrorNote } from "./ErrorNote";
import { Field, RangeBar } from "./controls";
import { SegmentControl } from "./SegmentControl";
import { ToolActions, ToolBody, ToolTitleActions } from "./ToolWindow";
import { t } from "../i18n/t";
import { pickPath } from "../lib/nativeDialog";
import { openHelpSection } from "../lib/helpNav";
import { listVoices, type VoiceModel } from "../lib/voices";
import { askConfirm, askPrompt } from "../lib/webDialog";
import { openDownloadModels } from "../lib/downloadModels";
import { AudioTrimEditor, canTrimAudio } from "./AudioTrim";
import { MoreMenuPopup, type PopupAnchor } from "./MoreMenu";
import { formatLocalizedList } from "../lib/voiceDisplay";

/** Windows path compare: slash / case must not hide a just-selected voice. */
function samePath(a?: string, b?: string): boolean {
  if (!a || !b) return false;
  const n = (p: string) => p.replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  return n(a) === n(b);
}

const baseName = (p: string) => p.split(/[\\/]/).pop() || p;

/**
 * 重试集合 = 失败 ∪ 未执行，成功的绝不重跑。
 *
 * 依据的是冻结清单的序号顺序：worker 按 manifest 顺序逐条处理，事件里的
 * `done` 是已处理条数（成功+跳过都算）——`idx >= processed` 就是未执行。
 * 失败用 skip 事件的 `path` 全路径精确回配；老 worker 不带 path 时
 * （file==name 纯文件名）退回文件名匹配——那是退而求其次的近似，文档
 * 里写明了。
 */
function deriveRetryable(
  manifest: ManifestEntry[],
  failed: Skipped[],
  processed: number,
): ManifestEntry[] {
  return manifest.filter(
    (e, i) =>
      i >= processed ||
      failed.some(
        (b) =>
          samePath(b.file, e.src) ||
          (b.file === b.name && baseName(e.src) === b.name),
      ),
  );
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
  /** 在跑的是否静默任务（TTS/顾问借用）。只作提示，归属看 owner 凭证。 */
  run_quiet?: boolean;
  /** 在跑单子的归属凭证；无凭证任务给 null。只有它等于本窗凭证才算本窗任务。 */
  run_owner?: string | null;
  /** busy 时后端给的最后一条进度快照，用来给新开的窗口补上进度。 */
  progress?: Progress | null;
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
  /** C-08/09：来源归属与排除状态，由 sts_sources_scan 给出。 */
  source_id?: string;
  source_name?: string;
  source_path?: string;
  excluded?: boolean;
  excluded_by_dir?: boolean;
};

type SrcDef = {
  id: string;
  kind: "file" | "dir";
  path: string;
  recursive: boolean;
  short: string;
};

type SrcScan = {
  sources?: SrcDef[];
  items?: InputFile[];
  missing?: { id: string; path: string; state?: string }[];
  total?: number;
  pending?: number;
  excluded?: number;
  output_in_source?: boolean;
  /** 来源落在输出树内（根相等 / 文件源在输出树下） */
  source_in_output?: boolean;
  /** 带代次扫描被作废时的返回体；前端直接丢弃。 */
  cancelled?: boolean;
};

type ManifestEntry = { src: string; rel: string };

type TtsStatus = {
  runtime_ready?: boolean;
  infer_present?: boolean;
  voices?: string[];
  model_path?: string;
  model_name?: string;
  /**
   * 朗读和变声的输出目录是两个，各自可改。
   *
   * 分开是因为这两种产物不是一类东西：朗读是系统嗓子的原声，变声是它再过一遍
   * RVC 的结果。以前共用一个目录、共用一套 tts_<时间戳>.wav 的名字，攒上十几个
   * 就再也分不出哪个是哪个。
   */
  out_dir_read?: string;
  out_dir_voice?: string;
  out_dir_read_default?: string;
  out_dir_voice_default?: string;
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
  /** skip 事件的源文件全路径（file 只有文件名，同名靠它区分） */
  path?: string;
  /** skip 事件的干净原因（不含「跳过 name：」前缀） */
  reason?: string;
  /** error 事件带的 worker 错误码 —— 配得上动作按钮的码（如「选到训练存档」）靠它 */
  message_code?: string;
  /** 有凭证的任务每条事件回显的归属串；与 runToken 相等才算本窗任务。 */
  owner?: string;
};

/** 批量转换里没转出来的那几个：哪个文件、为什么。 */
type Skipped = {
  file: string;
  name: string;
  reason: string;
};

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
  // 与训练面板同一模式：开关在底栏、内容在正文末尾。展开时把内容滚进
  // 视野 —— 两个工具窗曾经各摆各的（这里原来把按钮放在正文中间），
  // 用户在一个面板学会的位置到另一个面板就找不着了。
  const advRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (adv) advRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [adv]);
  const [sid, setSid] = useState(0);
  const [f0File, setF0File] = useState("");
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  // msg 这一格既报错也报成功。「复制完整错误 / 打开日志」只在报错时才该出现，
  // 所以两条路分开走，别让 ErrorNote 去猜。
  const [msgErr, setMsgErr] = useState(false);
  // 错误码（worker 的 message_code）。同一条报错通常来两次：进度事件一次（带
  // 码）、invoke 拒绝一次（只剩文本）。后到的没带码时不能把先到的抹掉，否则
  // 错误码上配的动作按钮会闪一下就消失。
  const errRef = useRef({ text: "", code: "" });
  const [msgCode, setMsgCode] = useState("");
  const showErr = useCallback((v: string, code?: string | null) => {
    const c = code ?? (v === errRef.current.text ? errRef.current.code : "");
    errRef.current = { text: v, code: c };
    setMsgErr(true);
    setMsg(v);
    setMsgCode(c);
  }, []);
  const showInfo = useCallback((v: string) => {
    setMsgErr(false);
    setMsg(v);
    setMsgCode("");
  }, []);

  // 批量里转失败被跳过的文件。整批不再因为一个坏文件中止，所以得有地方交代
  // 到底是哪几个没转出来。过程中 skip 事件也会往这里塞，不用等整批结束。
  const [skipped, setSkipped] = useState<Skipped[]>([]);
  // 上次执行的冻结清单 + 可重试的失败者。重试只跑失败条目，不重复处理
  // 已成功的（C-10）。
  const lastManifestRef = useRef<ManifestEntry[]>([]);
  const [retryable, setRetryable] = useState<ManifestEntry[]>([]);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const runningRef = useRef(false);
  // 任务归属：running=true 只说明后端忙；ownsRun 只代表「本窗发起过请求」，
  // ownerProven 才是后端认领回执（status/事件回显 runToken）。取消键只在
  // ownerProven 时出现——snapshot/invoke 在途期间 BUSY 可能是别窗抢走的。
  const [ownsRun, setOwnsRun] = useState(false);
  const ownsRunRef = useRef(false);
  const [ownerProven, setOwnerProven] = useState(false);
  const ownerProvenRef = useRef(false);
  // 本窗这次发起的凭证：每次 start 换新的，后端 sts_start 透传、回显比对。
  // finally 里清空——本单迟到的事件对不上新凭证，不会再进本窗账本。
  const runTokenRef = useRef("");
  // sts_start 调用是否还在途：在途期间本单收尾由 start() 的 finally 负责，
  // 轮询不许越界清 running；invoke 已落定（含拒绝）而后端还在跑时，才轮到
  // 轮询观察态收尾。
  const invokePendingRef = useRef(false);
  // 后端已处理的文件数（progress.done 的最大值）：启动失败/中途崩溃时
  // 用它划出「已执行/未执行」边界，重试集合 = 失败 ∪ 未执行。
  const doneCountRef = useRef(0);
  // 轮询代次：任何更新运行状态的来源（外来事件、本窗 start）先把它加一；
  // 在途轮询响应回来时发现代次变了 → 旧快照作废，不允许旧 idle 盖掉新 busy。
  const pollEpochRef = useRef(0);
  // skip 事件的实时累积放 ref 里：start() 的 catch 读到的是当时最新的
  // 失败集合（state 闭包可能滞后），全失败时据此给出整单重试。
  const skippedRef = useRef<Skipped[]>([]);
  // C-09：多来源清单。scan 是后端清单服务给的完整视图（含排除项）；
  // checked 只是批量操作的临时勾选，不参与/排除状态在服务端。
  const [scan, setScan] = useState<SrcScan | null>(null);
  // 扫描序号：只对最后发起的一次落地；中途被顶掉/取消/任务跑起来的
  // 结果一律丢弃，避免旧响应把运行期界面改回去。
  const scanSeqRef = useRef(0);
  const [scanning, setScanning] = useState(false);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [listFilter, setListFilter] = useState<"active" | "excluded" | "all">("active");
  const [listQuery, setListQuery] = useState("");
  const [inputPage, setInputPage] = useState(0);
  const lastCheckedRef = useRef("");
  const [trimPath, setTrimPath] = useState("");
  const [trimOpen, setTrimOpen] = useState(false);
  const [, setTrimBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [rec, setRec] = useState<RecProgress | null>(null);
  const [playing, setPlaying] = useState("");
  const [fileMenu, setFileMenu] = useState<{ anchor: PopupAnchor; file: InputFile } | null>(null);
  const recordingRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lastHomePath = useRef("");
  /** 上一次真正写出文件的目录。打开输出目录用它，不看默认 sts。 */
  const lastDestRef = useRef("");

  const pickVoice = useCallback((m: VoiceModel | undefined) => {
    if (!m || !m.path) return;
    setModelPath(m.path);
    setIndexPath(typeof m.index === "string" ? m.index : "");
    setModelName(m.name || m.file || "");
  }, []);

  const applyCurrent = useCallback((
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
  }, [pickVoice]);

  const outputRef = useRef(output);
  outputRef.current = output;

  const load = useCallback(async (full = true) => {
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
        // 只回填用户选过的目录。默认 User_Data/sts 不当成已选。
        if (!outputRef.current && s.last_output) setOutput(String(s.last_output));
        if (s.recording) {
          recordingRef.current = true;
          setRecording(true);
        }
      }
      // 后台还在转就把界面接回去。
      //
      // 进度是靠 `sts-progress` 事件推的，事件只发给当时开着的窗口。用户把这扇
      // 窗口关掉再打开，一条都没赶上，界面就显示成「还没开始」，而任务其实还在
      // 跑 —— 用户报的就是这个：以为要从头再来。
      //
      // 后端现在会连着 busy 一起给最后一条进度（sts.rs 的 LAST_PROGRESS），
      // 这里接上就行：进度条接着走。取消只给本窗发起的任务，外来任务只读。
      if (s.busy && !runningRef.current) {
        runningRef.current = true;
        setRunning(true);
        // 打开窗口时后端已在跑 → 这是别处的任务（含静默任务），只读观察，
        // 不给取消——归属只看本面板是否发起。
        ownsRunRef.current = false;
        setOwnsRun(false);
        if (s.progress) setProg(s.progress);
      }
      applyCurrent(s, cat);
    } catch (e) {
      showErr(String(e));
    }
  }, [applyCurrent, showErr]);

  useEffect(() => {
    void load(true);
    let disposed = false;
    const unsubs: Array<() => void> = [];
    void listen<Progress>("sts-progress", (ev) => {
      const p = ev.payload;
      // 事件是更新的运行状态来源：在途轮询的旧快照一律作废（代次闸口）。
      pollEpochRef.current += 1;
      // 归属回执：事件带 owner 且等于本窗凭证 → 本窗任务被后端认领；
      // 带别人的凭证 → 无论先前怎么以为，这都是外来任务，只读观察。
      // 无凭证字段的事件无法证明是本窗的（静默任务本就不发事件）——
      // 一律按外来处理，绝不进本窗账本。
      const mine =
        p.owner !== undefined &&
        p.owner === runTokenRef.current &&
        runTokenRef.current !== "";
      if (p.owner !== undefined) {
        if (mine) {
          ownerProvenRef.current = true;
          setOwnerProven(true);
        } else {
          ownsRunRef.current = false;
          setOwnsRun(false);
          ownerProvenRef.current = false;
          setOwnerProven(false);
        }
      }
      // 别窗启动的非静默任务事件也会广播到本窗：把界面接进只读观察态
      // （静默任务没有事件，由轮询发现；两者都靠 ownerProven=false 排掉取消）。
      if (!runningRef.current) {
        runningRef.current = true;
        setRunning(true);
        if (p.owner !== runTokenRef.current) {
          ownsRunRef.current = false;
          setOwnsRun(false);
        }
      }
      if (p.phase === "error") {
        showErr(p.message, p.message_code);
        // 错误正文只走 ErrorNote。进度行再贴一遍就是 26.8.22/4 截图里
        // 同一段 traceback 上下各一堵。
        setProg(null);
      } else {
        setProg(p);
      }
      // 已处理文件数按事件里的 done 取最大值——worker 失败发生在任何
      // skip 之前时，重试集合要靠「已执行/未执行」边界来算（G-6）。
      // 只记本窗任务的数：外来任务/迟到上一单的 done 不许进本窗账本。
      if (mine && typeof p.done === "number" && Number.isFinite(p.done)) {
        doneCountRef.current = Math.max(doneCountRef.current, p.done);
      }
      // 批量：跳过事件当场入列，方便边跑边看哪个坏了。file 记全路径
      // （path 字段），同名文件靠它区分；老 worker 没 path 时退回文件名。
      // 同样只记本窗任务的——外来任务的 skip 不进本窗的跳过清单/重试账本。
      if (mine && p.phase === "skip" && (p.path || p.file)) {
        const ident = p.path || p.file || "";
        const entry: Skipped = {
          file: ident,
          name: p.file || "?",
          reason: p.reason || p.message,
        };
        // ref 先写、state 后同步：不能在 setState updater 里做副作用——
        // updater 什么时候跑不归 invoke 的 catch 管。
        const prev = skippedRef.current;
        if (
          !prev.some(
            (x) => x.file === ident || (x.name === entry.name && !p.path),
          )
        ) {
          const next = [...prev, entry];
          skippedRef.current = next;
          setSkipped(next);
        }
      }
    }).then((fn) => {
      if (disposed) dropListen(fn);
      else unsubs.push(fn);
    });
    void listen<RecProgress>("sts-record", (ev) => {
      setRec(ev.payload);
      if (ev.payload.phase === "done" || ev.payload.phase === "error") {
        recordingRef.current = false;
        setRecording(false);
        void refreshScanRef.current?.();
      }
    }).then((fn) => {
      if (disposed) dropListen(fn);
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
      if (disposed) dropListen(fn);
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
      if (disposed) dropListen(fn);
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
          if (disposed) dropListen(fn);
          else unFocus = fn;
        });
    } catch {
      /* 浏览器预览没有 Tauri 窗口 */
    }
    return () => {
      disposed = true;
      unsubs.forEach((f) => dropListen(f));
      dropListen(unFocus);
      audioRef.current?.pause();
    };
  }, [load, pickVoice, showErr]);

  // 静默任务（TTS/顾问借用转换管线）不发 sts-progress，只能靠轮询发现；
  // 别窗的非静默任务在事件未到/窗口没开时也一样走这条路。任务收尾由
  // 「!busy」判定——quiet 运行没有终态事件。
  //
  // 串行单飞：上一次没回来就跳过这一拍，不叠加在途请求；响应落地前先查
  // 代次——期间有事件/start 先动过运行状态，这份旧快照直接作废（旧 idle
  // 不许盖掉新 busy）；卸载后到达的响应不落任何 state。卸载清理定时器。
  useEffect(() => {
    let disposed = false;
    let inFlight = false;
    const pollOnce = async () => {
      if (disposed || inFlight) return;
      inFlight = true;
      const epoch = pollEpochRef.current;
      try {
        const s = await invoke<StsStatus>("sts_status");
        if (disposed || epoch !== pollEpochRef.current) return;
        // 归属回执：本窗发过 start 且凭证被回显 → 取消键放行；凭证是别人
        // 的 → 不管先前怎么以为，降级成外来观察态。
        if (s.run_owner != null) {
          const mine = s.run_owner === runTokenRef.current;
          if (mine) {
            if (!ownerProvenRef.current) {
              ownerProvenRef.current = true;
              setOwnerProven(true);
            }
          } else {
            ownsRunRef.current = false;
            setOwnsRun(false);
            ownerProvenRef.current = false;
            setOwnerProven(false);
          }
        }
        if (s.busy) {
          if (!runningRef.current) {
            runningRef.current = true;
            setRunning(true);
          }
          // 静默任务的事件被静音，但 LAST_PROGRESS 仍在更新：
          // 观察态靠它让进度条继续走。
          if (!ownsRunRef.current && s.progress?.phase) {
            setProg(s.progress);
          }
          return;
        }
        // 收尾边界：外来任务（!ownsRun）由这里清；本窗任务在 invoke 在途
        // 时由 start() 的 finally 清——但 invoke 拒绝而后端仍忙（本窗凭证
        // 还在跑/外来已接管）时 finally 不落地运行态，轮到这里收尾。
        if (
          runningRef.current &&
          (!ownsRunRef.current || !invokePendingRef.current)
        ) {
          runningRef.current = false;
          setRunning(false);
          setProg(null);
          ownerProvenRef.current = false;
          setOwnerProven(false);
          void refreshScanRef.current?.();
        }
      } catch {
        // 状态问不到就按上一帧的样子显示，下一拍再试。
      } finally {
        inFlight = false;
      }
    };
    const id = window.setInterval(() => void pollOnce(), 2000);
    return () => {
      disposed = true;
      window.clearInterval(id);
    };
  }, []);

  const refreshScan = useCallback(async () => {
    const seq = ++scanSeqRef.current;
    setScanning(true);
    try {
      const r = await invoke<SrcScan>("sts_sources_scan", { output });
      // 只落地最后发起的一代：被顶掉的、后端作废的、以及任务跑起来后
      // 才回来的结果都丢弃——运行期界面按冻结清单展示，不被半路改写。
      if (seq !== scanSeqRef.current || r.cancelled || runningRef.current) {
        return;
      }
      setScan(r);
      // 重扫后旧勾选可能已失效（文件消失/被排除规则接管），清掉再选。
      setChecked(new Set());
    } catch (e) {
      if (seq === scanSeqRef.current) showErr(String(e));
    } finally {
      if (seq === scanSeqRef.current) setScanning(false);
    }
  }, [output, showErr]);
  const refreshScanRef = useRef<() => Promise<void> | undefined>(() => undefined);
  refreshScanRef.current = refreshScan;

  useEffect(() => {
    void refreshScan();
  }, [refreshScan]);

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
          v0: formatLocalizedList(st.engine_core_missing || []) || "hubert/rmvpe",
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
        showErr(t("s.stsPlayFail"));
      };
      void el.play().then(() => setPlaying(path));
    } catch (e) {
      showErr(String(e));
    }
  };

  const startRec = async () => {
    if (recordingRef.current || runningRef.current) return;
    stopPlay();
    showInfo("");
    setRec({ phase: "start", sec: 0, message: t("s.stsRecordOpening") });
    recordingRef.current = true;
    setRecording(true);
    try {
      // 录音始终落原默认录音目录；录完只登记这次写出的那个文件——录音
      // 目录里可能攒着旧录音，整目录加成来源会把它们一股脑扫进清单。
      const folder = await invoke<string>("sts_default_input");
      const r = await invoke<{
        file?: string;
        dir?: string;
        cancelled?: boolean;
      }>("sts_record_start", { input: folder });
      if (r.file && !r.cancelled) {
        await invoke("sts_sources_add", { path: r.file }).catch(() => undefined);
        showInfo(t("s.stsRecordSaved", { v0: r.file }));
      }
      await refreshScan();
    } catch (e) {
      showErr(String(e));
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
      await invoke("sts_sources_delete", { path: f.path });
      await refreshScan();
    } catch (e) {
      showErr(String(e));
    }
  };

  const renameFile = async (f: InputFile) => {
    const name = await askPrompt(t("s.b8659855b0"), f.name);
    const nextName = name?.trim();
    if (!nextName || nextName === f.name) return;
    if (playing === f.path) stopPlay();
    try {
      await invoke<string>("sts_sources_rename", {
        path: f.path,
        newName: nextName,
      });
      await refreshScan();
    } catch (e) {
      showErr(String(e));
    }
  };

  // 批量勾选只作「排除/恢复」的操作对象；参与/排除状态在服务端，
  // 不拿 checkbox 当真实输入（计划 C8：不拿 DOM 状态决定真正输入）。
  const visibleItems = (scan?.items ?? []).filter((it) => {
    if (listFilter === "active" && it.excluded) return false;
    if (listFilter === "excluded" && !it.excluded) return false;
    const q = listQuery.trim().toLowerCase();
    if (q && !(it.name.toLowerCase().includes(q) || it.rel.toLowerCase().includes(q))) return false;
    return true;
  });
  const inputPageCount = Math.max(1, Math.ceil(visibleItems.length / 20));
  const currentInputPage = Math.min(inputPage, inputPageCount - 1);
  const pagedItems = visibleItems.slice(currentInputPage * 20, (currentInputPage + 1) * 20);

  const toggleItem = (f: InputFile, shift: boolean) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (shift && lastCheckedRef.current) {
        const ids = visibleItems.map((x) => x.path);
        const a = ids.indexOf(lastCheckedRef.current);
        const b = ids.indexOf(f.path);
        if (a >= 0 && b >= 0) {
          const [lo, hi] = a < b ? [a, b] : [b, a];
          const on = !prev.has(f.path);
          for (const id of ids.slice(lo, hi + 1)) {
            if (on) next.add(id); else next.delete(id);
          }
          lastCheckedRef.current = f.path;
          return next;
        }
      }
      if (next.has(f.path)) next.delete(f.path); else next.add(f.path);
      lastCheckedRef.current = f.path;
      return next;
    });
  };

  const excludeSelected = async () => {
    if (!checked.size) return;
    try {
      for (const p of checked) {
        await invoke("sts_sources_exclude", { path: p });
      }
      await refreshScan();
    } catch (e) {
      showErr(String(e));
    }
  };

  const restoreSelected = async () => {
    if (!checked.size) return;
    try {
      for (const p of checked) {
        const r = await invoke<{ blocked_by?: string }>("sts_sources_restore", { path: p });
        if (r?.blocked_by) showInfo(t("s.stsStillExcluded", { v0: r.blocked_by }));
      }
      await refreshScan();
    } catch (e) {
      showErr(String(e));
    }
  };

  const addSource = async (folder: boolean) => {
    const p = await pickPath<string | null>("sts_pick_input", { folder }, t("s.pickBusyFolder"));
    if (!p) return;
    try {
      await invoke("sts_sources_add", { path: p });
      await refreshScan();
    } catch (e) {
      showErr(String(e));
    }
  };

  const removeSource = async (id: string) => {
    try {
      await invoke("sts_sources_remove", { id });
      await refreshScan();
    } catch (e) {
      showErr(String(e));
    }
  };

  const toggleRecursive = async (id: string, v: boolean) => {
    try {
      await invoke("sts_sources_set_recursive", { id, recursive: v });
      await refreshScan();
    } catch (e) {
      showErr(String(e));
    }
  };

  // 点别处或 Escape 关闭行内「⋯」菜单；打开处 stopPropagation 防即开即关。
  useEffect(() => {
    if (!fileMenu) return;
    const close = () => setFileMenu(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFileMenu(null);
    };
    window.addEventListener("click", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [fileMenu]);

  const openFileMenu = (e: MouseEvent<HTMLButtonElement>, f: InputFile) => {
    e.stopPropagation();
    if (fileMenu && fileMenu.file.path === f.path) {
      setFileMenu(null);
      return;
    }
    const r = e.currentTarget.getBoundingClientRect();
    setFileMenu({
      anchor: { left: r.left, right: r.right, top: r.top, bottom: r.bottom },
      file: f,
    });
  };

  const start = async (override?: ManifestEntry[]) => {
    if (runningRef.current || recordingRef.current) return;
    // 实时 worker 还活着就走热路径（复用已加载的模型），不再先杀进程。
    showInfo("");
    setProg({ phase: "start", done: 0, total: 1, pct: 0, message: t("s.090840132b") });
    setSkipped([]);
    skippedRef.current = [];
    setRetryable([]);
    doneCountRef.current = 0;
    runningRef.current = true;
    setRunning(true);
    // 本次发起的凭证：后端认领 BUSY 才记名并回显，取消键等回执再放行。
    // 自封「本窗发起」不算数——snapshot 在途时 BUSY 可能是别窗抢走的。
    const token = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    runTokenRef.current = token;
    ownerProvenRef.current = false;
    setOwnerProven(false);
    ownsRunRef.current = true;
    setOwnsRun(true);
    invokePendingRef.current = true;
    // start 本身是更新运行状态的来源：把在途轮询的旧快照作废。
    pollEpochRef.current += 1;
    // invoke 拒绝≠后端空闲：snapshot/认领竞争下别窗可能拿着 BUSY 在跑
    // 本窗之外的单子。落地前向 sts_status 核实一次，仍在跑就不放控件。
    let backendBusy = false;
    let backendOwner: string | null = null;
    try {
      // C-10 显式清单：先冻结快照，把同一份清单交给 worker 执行。
      // 预览计数、进度、worker 三者看到的是同一批文件；重试失败条目时
      // 直接带上回传入的清单，不再重新扫来源。snapshot 走后端无代次
      // 扫描，UI 侧的扫描取消打不断这次冻结。
      const snap = override
        ? undefined
        : await invoke<{
            manifest?: ManifestEntry[];
            total?: number;
            excluded?: number;
          }>("sts_snapshot", { output });
      const manifest = override ?? snap?.manifest ?? [];
      if (!manifest.length) {
        showInfo(t("s.stsNoItems"));
        runningRef.current = false;
        setRunning(false);
        ownsRunRef.current = false;
        setOwnsRun(false);
        ownerProvenRef.current = false;
        setOwnerProven(false);
        setProg(null);
        return;
      }
      // 冻结清单在 invoke 前就记下来：无论成功失败，重试都对着同一份。
      lastManifestRef.current = manifest;
      const r = await invoke<{
        files?: string[];
        skipped?: Skipped[];
        output?: string;
      }>("sts_start", {
        input: "",
        output,
        manifest,
        owner: token,
        excluded: snap?.excluded,
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
      // 终态权威计数：全部条目都已处理，重试集合只剩失败那部分。
      doneCountRef.current = manifest.length;
      setRetryable(deriveRetryable(manifest, bad, manifest.length));
      if (r.output) lastDestRef.current = String(r.output);
      // 终态清单覆盖过程中累积的，避免 reason 被截断的半截文案。
      setSkipped(bad);
      skippedRef.current = bad;
      // 有跳过的就必须在总结里说出来，不然「完成 8 个文件」会被当成全转完了。
      showInfo(
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
      showErr(String(e));
      setProg(null);
      // 启动就死（一条 skip 都没来）→ doneCount=0，整单算未执行，全部进
      // 重试集合；中途挂 → 已成功的（idx<done 且不在失败里）不重跑，
      // 失败 ∪ 未执行进重试。
      setRetryable(
        deriveRetryable(
          lastManifestRef.current,
          skippedRef.current,
          doneCountRef.current,
        ),
      );
      // 认领竞争下别窗可能拿着 BUSY：向 sts_status 核实一次再决定怎么
      // 收尾。问不到就当空闲处理（下一次轮询会自己纠回来）。
      try {
        const s = await invoke<StsStatus>("sts_status");
        backendBusy = !!s.busy;
        backendOwner = s.run_owner ?? null;
      } catch {
        /* 状态问不到按空闲收尾 */
      }
    } finally {
      invokePendingRef.current = false;
      if (backendBusy && backendOwner === token) {
        // invoke 拒绝但后端仍在执行本单（凭证是它自己回显的）：保留归属
        // 与凭证——取消仍可发、事件仍按本窗记账，终态由轮询收尾
        // （invokePending=false 已放行那条路径）。
      } else {
        // 空闲、或别窗的任务在跑：本窗凭证作废——本单迟到的回显/事件
        // 从此对不上，不进账本不误认归属。
        runTokenRef.current = "";
        if (backendBusy) {
          // 别窗的任务在跑：本窗转外来只读观察——不给取消、不改清单，
          // running 保持 true，控件继续锁定直到轮询看到收尾。
          ownsRunRef.current = false;
          setOwnsRun(false);
          ownerProvenRef.current = false;
          setOwnerProven(false);
        } else {
          runningRef.current = false;
          setRunning(false);
          ownsRunRef.current = false;
          setOwnsRun(false);
          ownerProvenRef.current = false;
          setOwnerProven(false);
          // 运行期丢弃的扫描结果补一轮（清单在任务期间可能被外部动过）。
          void refreshScan();
        }
      }
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
      <ToolTitleActions>
        {st.engine_core_ready === false ? (
          <Btn onClick={() => openDownloadModels()}>{t("s.1252c81119")}</Btn>
        ) : null}
        <Btn onClick={() => openHelpSection("infer")}>{t("s.trainOpenHelp")}</Btn>
      </ToolTitleActions>
      {blocked ? (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <p className="m-0 text-[13px] text-[var(--danger)]">{blocked}</p>
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
          <span className={LABEL}>{t("s.stsSources")}</span>
          <span className={PATH}>
            {t("s.stsPendingCount", {
              v0: scan?.pending ?? 0,
              v1: scan?.excluded ?? 0,
            })}
          </span>
          {scanning ? (
            <Btn
              ariaLabel={t("s.stsScanCancel")}
              onClick={() => void invoke("sts_sources_scan_cancel")}
            >
              {t("s.stsScanCancel")}
            </Btn>
          ) : (
            <Btn
              ariaLabel={t("s.stsRefresh")}
              onClick={() => void refreshScan()}
            >
              {t("s.stsRefresh")}
            </Btn>
          )}
          <Btn
            disabled={running || recording}
            onClick={() => void addSource(false)}
          >{t("s.stsAddFile")}</Btn>
          <Btn
            disabled={running || recording}
            onClick={() => void addSource(true)}
          >{t("s.stsAddDir")}</Btn>
        </div>
        {(scan?.sources?.length ?? 0) > 0 ? (
          <ul className="m-0 list-none p-0 pb-1">
            {scan!.sources!.map((s) => {
              const miss = scan?.missing?.find((m) => m.id === s.id);
              return (
                <li
                  key={s.id}
                  className="flex items-center gap-2 rounded-[var(--rs)] px-2 py-1 text-[12.5px]"
                >
                  <span
                    className={`min-w-0 flex-1 truncate font-mono ${miss ? "text-[var(--danger)]" : "text-[var(--ink-muted)]"}`}
                    title={miss?.path || s.path}
                  >
                    {s.path}
                  </span>
                  {miss ? (
                    <span className="shrink-0 text-[11px] text-[var(--danger)]">
                      {miss.state === "unreadable"
                        ? t("s.stsUnreadableTag")
                        : t("s.stsMissingTag")}
                    </span>
                  ) : null}
                  {s.kind === "dir" ? (
                    <label className="flex shrink-0 items-center gap-1 text-[11.5px] text-[var(--meta)] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={s.recursive}
                        disabled={running || recording}
                        onChange={(e) => void toggleRecursive(s.id, e.target.checked)}
                      />
                      {t("s.stsRecursive")}
                    </label>
                  ) : null}
                  <Btn
                    className="px-2"
                    disabled={running || recording}
                    ariaLabel={t("s.stsRemoveSource")}
                    onClick={() => void removeSource(s.id)}
                  >
                    ✕
                  </Btn>
                </li>
              );
            })}
          </ul>
        ) : null}
        {scan?.output_in_source ? (
          <p className="m-0 pb-1 text-[11.5px] text-[var(--meta)]">
            {t("s.stsOutputInside")}
          </p>
        ) : null}
        {scan?.source_in_output ? (
          <p className="m-0 pb-1 text-[11.5px] text-[var(--meta)]">
            {t("s.stsSourceInsideOut")}
          </p>
        ) : null}
        <div className={ROW}>
          <span className={LABEL}>{t("s.a0bc984876")}</span>
          <span className={PATH}>{output || t("s.53e2db7016")}</span>
          <Btn
            disabled={running || recording}
            onClick={() => {
              void pickPath<string | null>("sts_pick_output", undefined, t("s.pickBusyFolder")).then(
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
            {t("s.stsInputCount", { v0: visibleItems.length })}
          </span>
        </div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <input
            className={`${FIELD} min-w-0 flex-1`}
            placeholder={t("s.stsSearchPh")}
            value={listQuery}
            onChange={(e) => {
              setListQuery(e.target.value);
              setInputPage(0);
              // 搜索只筛显示，不改参与集合；隐藏的勾选先清掉。
              setChecked(new Set());
            }}
          />
          <select
            className={FIELD}
            value={listFilter}
            disabled={running || recording}
            onChange={(e) => {
              setListFilter(e.target.value as typeof listFilter);
              setInputPage(0);
              // 切换过滤后隐藏的已选条目不能被批量操作——直接清勾选。
              setChecked(new Set());
            }}
          >
            <option value="active">{t("s.stsFilterActive")}</option>
            <option value="excluded">{t("s.stsFilterExcluded")}</option>
            <option value="all">{t("s.stsFilterAll")}</option>
          </select>
          <Btn
            disabled={running || recording || !visibleItems.length}
            onClick={() => setChecked(new Set(visibleItems.map((x) => x.path)))}
          >
            {t("s.stsSelectFiltered")}
          </Btn>
          <Btn
            disabled={running || recording || !checked.size}
            onClick={() => void excludeSelected()}
          >
            {t("s.stsExcludeSel")}
          </Btn>
          <Btn
            disabled={running || recording || !checked.size}
            onClick={() => void restoreSelected()}
          >
            {t("s.stsRestoreSel")}
          </Btn>
          <Btn
            disabled={running || recording || !(scan?.sources?.length || scan?.items?.length)}
            onClick={() => {
              void (async () => {
                if (!(await askConfirm(t("s.stsClearConfirm")))) return;
                await invoke("sts_sources_clear").then(() => refreshScan());
              })();
            }}
          >
            {t("s.stsClearList")}
          </Btn>
        </div>
        {checked.size ? (
          <p className="m-0 mb-1 text-[11.5px] text-[var(--meta)]">
            {t("s.stsSelected", { v0: checked.size })}
          </p>
        ) : null}
        {trimOpen && canTrimAudio(trimPath) ? (
          <AudioTrimEditor
            key={trimPath}
            input={trimPath}
            disabled={running || recording}
            onBusyChange={setTrimBusy}
            onApply={() => {
              if (!runningRef.current) void refreshScan();
            }}
          />
        ) : null}
        {!visibleItems.length ? (
          <p className="m-0 text-[12.5px] text-[var(--meta)]">
            {scan?.items?.length ? t("s.stsInputEmpty") : t("s.stsNoItems")}
          </p>
        ) : (
          <>
            <ul className="m-0 max-h-[220px] list-none overflow-y-auto p-0">
              {pagedItems.map((f) => (
                <li
                  key={f.path}
                  className={[
                    "flex items-center gap-2 rounded-[var(--rs)] px-2 py-1.5",
                    checked.has(f.path)
                      ? "bg-[color-mix(in_srgb,var(--accent)_10%,transparent)]"
                      : "hover:bg-[color-mix(in_srgb,var(--ink)_4%,transparent)]",
                  ].join(" ")}
                >
                  <input
                    type="checkbox"
                    className="shrink-0"
                    checked={checked.has(f.path)}
                    disabled={running || recording}
                    // Shift 连选取点击时的 shiftKey；click 里拦下默认切换，
                    // 由 toggleItem 统一处理普通与连选两条路。
                    onClick={(e) => {
                      e.preventDefault();
                      toggleItem(f, e.shiftKey);
                    }}
                    onChange={() => undefined}
                    aria-label={f.name}
                  />
                  <button
                    type="button"
                    className={`min-w-0 flex-1 border-0 bg-transparent p-0 text-left cursor-pointer ${f.excluded ? "opacity-55" : ""}`}
                    disabled={running || recording}
                    onClick={() => toggleItem(f, false)}
                    title={f.path}
                  >
                    <span className="block truncate text-[12.5px] font-mono">
                      {f.rel || f.name}
                      {f.source_name && (scan?.sources?.length ?? 0) > 1
                        ? `  · ${f.source_name}`
                        : ""}
                    </span>
                    <span className="block text-[11px] text-[var(--meta)] tabular-nums">
                      {f.excluded
                        ? f.excluded_by_dir
                          ? t("s.stsExcludedByDir")
                          : t("s.stsFilterExcluded")
                        : `${formatBytes(f.size)}${f.mtime ? ` · ${formatMtime(f.mtime)}` : ""}`}
                    </span>
                  </button>
                  <Btn
                    disabled={recording}
                    onClick={() => playFile(f.path)}
                  >
                    {playing === f.path ? t("s.stsStopPlay") : t("s.stsPlay")}
                  </Btn>
                  <Btn
                    className="px-2.5"
                    disabled={running || recording}
                    ariaLabel={t("models.more")}
                    onClick={(e) => openFileMenu(e, f)}
                  >
                    ⋯
                  </Btn>
                </li>
              ))}
            </ul>
            {fileMenu ? (
              <MoreMenuPopup
                anchor={fileMenu.anchor}
                items={[
                  ...(canTrimAudio(fileMenu.file.path)
                    ? [
                        {
                          label: t("s.stsTrim"),
                          action: () => {
                            setFileMenu(null);
                            setTrimPath(fileMenu.file.path);
                            setTrimOpen(true);
                          },
                        },
                      ]
                    : []),
                  ...(fileMenu.file.excluded
                    ? [
                        {
                          label: t("s.stsRestoreSel"),
                          action: () => {
                            setFileMenu(null);
                            void invoke("sts_sources_restore", {
                              path: fileMenu.file.path,
                            }).then(() => refreshScan());
                          },
                        },
                      ]
                    : [
                        {
                          label: t("s.stsExcludeSel"),
                          action: () => {
                            setFileMenu(null);
                            void invoke("sts_sources_exclude", {
                              path: fileMenu.file.path,
                            }).then(() => refreshScan());
                          },
                        },
                        {
                          label: t("s.1cd80fd7a8"),
                          action: () => {
                            setFileMenu(null);
                            void renameFile(fileMenu.file);
                          },
                        },
                        {
                          label: t("s.stsDelete"),
                          danger: true,
                          action: () => {
                            setFileMenu(null);
                            void removeFile(fileMenu.file);
                          },
                        },
                      ]),
                ]}
              />
            ) : null}
            {inputPageCount > 1 ? (
              <div className="mt-2 flex items-center justify-between gap-2">
                <Btn
                  disabled={running || recording || currentInputPage === 0}
                  onClick={() => setInputPage(Math.max(0, currentInputPage - 1))}
                >{t("s.prevPage")}</Btn>
                <span className="text-[11.5px] text-[var(--meta)] tabular-nums">
                  {t("s.pageOf", { cur: currentInputPage + 1, total: inputPageCount })}
                </span>
                <Btn
                  disabled={running || recording || currentInputPage >= inputPageCount - 1}
                  onClick={() => setInputPage(Math.min(inputPageCount - 1, currentInputPage + 1))}
                >{t("s.67a246a344")}</Btn>
              </div>
            ) : null}
          </>
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

      {/* 进阶设置的开关挪进了底栏（与训练面板同位），展开的内容留在这里。 */}
      {adv ? (
        <div ref={advRef} className="mt-3 flex flex-col gap-3.5">
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
                      void pickPath<string | null>("ckpt_pick", { kind: "f0" }, t("s.pickBusyFile")).then(
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
          {running && !ownsRun ? (
            <p className="m-0 mt-1 text-[11.5px] text-[var(--meta)]">
              {t("s.stsForeignBusy")}
            </p>
          ) : null}
        </div>
      ) : null}

      {msg ? <ErrorNote text={msg} error={msgErr} code={msgCode} /> : null}

      {retryable.length && !running ? (
        <div className="mt-3">
          <Btn className="mb-1" onClick={() => void start(retryable)}>
            {t("s.stsRetryFailed", { v0: retryable.length })}
          </Btn>
        </div>
      ) : null}
      {skipped.length ? (
        <div className={retryable.length && !running ? "pt-1" : "mt-3 pt-2"}>
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

      <ToolActions>
        {/* 进阶设置开关与训练面板同位：底栏左侧，主操作永远在最右。 */}
        <Btn onClick={() => setAdv((v) => !v)}>
          {adv ? t("s.ckptAdvancedHide") : t("s.ckptAdvanced")}
        </Btn>
        <div className="ml-auto flex items-center gap-2.5">
          {running && ownsRun && ownerProven ? (
            <Btn
              onClick={() =>
                void invoke("sts_cancel", { owner: runTokenRef.current })
              }
            >
              {t("s.4d0b4688c7")}
            </Btn>
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
            busy={running}
            disabled={
              running || recording || !!blocked || !(scan?.pending ?? 0)
            }
            onClick={() => void start()}
          >
            {running
              ? t("s.090840132b")
              : t("s.stsWillProcess", { v0: scan?.pending ?? 0 })}
          </Btn>
        </div>
      </ToolActions>
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
  const runningRef = useRef(false);

  /** 改完输出目录要把状态拉一遍，路径是后端算出来的，前端不自己拼。 */
  const refreshStatus = useCallback(async () => {
    try {
      setSt(await invoke<TtsStatus>("tts_status"));
    } catch (e) {
      showErr(String(e));
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const s = await invoke<TtsStatus>("tts_status");
        setSt(s);
        if (s.voices?.length) setVoice((v) => v || s.voices![0]);
      } catch (e) {
        showErr(String(e));
      }
    })();
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<Progress>("tts-progress", (ev) => {
      setProg(ev.payload);
      if (ev.payload.phase === "error") showErr(ev.payload.message);
    }).then((fn) => {
      if (disposed) dropListen(fn);
      else un = fn;
    });
    return () => {
      disposed = true;
      dropListen(un);
    };
  }, []);

  // 当前模式那一路的输出目录，以及它是不是用户自己选过的（选过才给「恢复默认」）。
  const outDir = (useRvc ? st.out_dir_voice : st.out_dir_read) || "";
  const outDefault = (useRvc ? st.out_dir_voice_default : st.out_dir_read_default) || "";
  const outCustom = !!outDir && !!outDefault && !samePath(outDir, outDefault);

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
    showInfo("");
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
      showInfo(t("s.c7cbedc8f6", { v0: r.file ?? "" }));
    } catch (e) {
      showErr(String(e));
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
          <p className="m-0 text-[13px] text-[var(--danger)]">{blocked}</p>
          {useRvc && !st.infer_present ? (
            <Btn onClick={() => openDownloadModels()}>{t("s.1252c81119")}</Btn>
          ) : null}
        </div>
      ) : null}

      <textarea
        className={[
          "w-full min-h-[120px] rounded-[var(--rs)] border px-3 py-2.5 text-[13.5px] leading-relaxed",
          "bg-transparent text-[var(--ink)] resize-y",
          over ? "border-[var(--danger)]" : "border-[var(--hairline)]",
        ].join(" ")}
        placeholder={t("s.f2f07193b8")}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <p
        className={[
          "m-0 mt-1.5 text-[12px] text-right tabular-nums",
          over ? "text-[var(--danger)]" : "text-[var(--meta)]",
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
        {/* 只显示当前模式那一路。两行并排摆出来的话，用户改了不用的那一行却
            以为改的是这一次要用的，比不给还糟。 */}
        <div className={ROW}>
          <span className={LABEL}>{t("s.ttsOutDir")}</span>
          <span className={PATH} title={outDir}>
            {outDir || t("s.53e2db7016")}
          </span>
          {outCustom ? (
            <Btn
              onClick={() => {
                void invoke("tts_reset_output", { useRvc })
                  .then(refreshStatus)
                  .catch((e) => showErr(String(e)));
              }}
            >
              {t("s.ttsOutReset")}
            </Btn>
          ) : null}
          <Btn
            onClick={() => {
              void pickPath<string | null>(
                "tts_pick_output",
                { useRvc },
                t("s.pickBusyFolder"),
              )
                .then((p) => {
                  if (p) void refreshStatus();
                })
                .catch((e) => showErr(String(e)));
            }}
          >
            {t("s.70b208202c")}
          </Btn>
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

      {msg ? <ErrorNote text={msg} error={msgErr} /> : null}

      <ToolActions>
        <div className="ml-auto flex items-center gap-2.5">
          {running ? (
            <Btn onClick={() => void invoke("tts_cancel")}>{t("s.4d0b4688c7")}</Btn>
          ) : (
            <Btn onClick={() => void invoke("tts_reveal", { useRvc })}>
              {t("s.344a481fa0")}
            </Btn>
          )}
          <Btn
            primary
            busy={running}
            disabled={running || !!blocked || !text.trim() || over}
            onClick={() => void start()}
          >
            {running ? t("s.ec35cdf525") : t("s.74a000b7ac")}
          </Btn>
        </div>
      </ToolActions>
    </>
  );
}
