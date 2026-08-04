import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn, HelpMark } from "./ui";
import { tip } from "../lib/glossary";
import { ExtrasDialog } from "./ExtrasDialog";
import { ToolBody } from "./ToolWindow";

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
  busy?: boolean;
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

const STAGE_NAMES: Record<string, string> = {
  preprocess: "切片",
  f0: "音高",
  feature: "特征",
  train: "训练",
  index: "索引",
};

const ROW = "flex items-center gap-3 py-2.5";
const LABEL = "w-[76px] shrink-0 text-[13px]";
const PATH =
  "flex-1 min-w-0 truncate text-[12.5px] text-[var(--ink-muted)] font-mono";
const FIELD =
  "rounded-[var(--rs)] border border-[var(--hairline)] bg-transparent px-2 py-1.5 text-[13px]";

/**
 * 训练音色。
 *
 * 只暴露四个决定：素材在哪、叫什么名字、多少轮、采样率。原版那一屏还有
 * batch size、缓存进显存、多卡拆分、是否保存中间权重 —— 那些是给训练农场
 * 调的，我们的用户是一台家用机，多给一个开关就多一种训废的方式。
 */
export function TrainPanel() {
  const [st, setSt] = useState<Status>({});
  const [name, setName] = useState("");
  const [dataset, setDataset] = useState("");
  const [sr, setSr] = useState("48k");
  const [epochs, setEpochs] = useState(200);
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  const [running, setRunning] = useState(false);
  const [extrasOpen, setExtrasOpen] = useState(false);
  const runningRef = useRef(false);

  const load = async () => {
    try {
      setSt(await invoke<Status>("train_status"));
    } catch (e) {
      setMsg(String(e));
    }
  };

  useEffect(() => {
    void load();
    // listen() 是异步的，弹窗在它 resolve 之前关掉就会把注销句柄丢掉，
    // 每开一次泄漏一个监听。和 SeparateDialog 一样的处理。
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<Progress>("train-progress", (ev) => {
      setProg(ev.payload);
      if (ev.payload.phase === "error") setMsg(ev.payload.message || "训练失败");
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
  const needPretrained =
    !!st.runtime_ready &&
    !!st.worker_present &&
    !!st.mute_present &&
    !!st.hubert_present &&
    !!st.nvidia &&
    !srReady;
  const blocked: { text: string; term?: string } = !st.runtime_ready
    ? { text: "运行时未就绪，先到「其他」页补全运行时", term: "运行时" }
    : !st.worker_present || !st.mute_present
      ? { text: "训练组件不全，安装可能不完整" }
      : !st.hubert_present
        ? { text: "缺 Hubert 模型，先补全引擎资源", term: "Hubert 模型" }
        : !st.nvidia
          ? {
              text: "训练仅支持 NVIDIA 显卡。当前系统的 DirectML 环境暂不支持相关训练算子。",
              term: "DirectML",
            }
          : !srReady
            ? {
                text: `缺 ${sr} 的训练底模。只需下载与采样率对应的那一套（与 RVC 原版 pretrained_v2 一致）。`,
                term: "底模",
              }
            : { text: "" };

  const start = async () => {
    if (runningRef.current) return;
    setMsg("");
    setProg(null);
    runningRef.current = true;
    setRunning(true);
    try {
      const r = await invoke<{ weights?: string }>("train_start", {
        req: {
          exp: name.trim(),
          dataset,
          sample_rate: sr,
          total_epoch: epochs,
          // 家用卡的稳妥值。开放出去只会让人调到爆显存，然后来问为什么崩。
          batch_size: 8,
          save_every: 25,
          f0_method: "rmvpe",
          resume,
        },
      });
      setMsg(`训练完成：${r.weights ?? ""}`);
      void load();
    } catch (e) {
      setMsg(String(e));
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  };

  const pct = prog?.total ? Math.round(((prog.done ?? 0) / prog.total) * 100) : 0;
  const stageLabel = prog?.stage ? STAGE_NAMES[prog.stage] || prog.stage : "";
  const stepLine =
    prog?.index && prog?.total_stages
      ? `第 ${prog.index}/${prog.total_stages} 步 · ${stageLabel}`
      : "";

  return (
    <ToolBody>
        <h3 className="m-0 mb-1 text-[17px] font-semibold">训练音色</h3>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)]">
          使用人声干声素材训练专属音色。推荐 10 分钟以上的高质量录音，
          含背景音乐的素材请先使用「人声分离」进行处理。
        </p>

        {blocked.text ? (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <p className="m-0 text-[13px] text-[#b8534f] flex items-center gap-1.5">
              {blocked.text}
              {blocked.term ? <HelpMark title={tip(blocked.term)} /> : null}
            </p>
            {needPretrained ? (
              <Btn onClick={() => setExtrasOpen(true)}>下载训练底模</Btn>
            ) : null}
          </div>
        ) : (
          <div className="mb-3 flex justify-end">
            <Btn onClick={() => setExtrasOpen(true)}>下载底模</Btn>
          </div>
        )}

        <div className="border-t border-[var(--hairline)]">
          <div className={ROW}>
            <span className={LABEL}>素材目录</span>
            <span className={PATH}>{dataset || "未选择"}</span>
            <Btn
              onClick={() => {
                void invoke<string | null>("train_pick_dataset").then(
                  (p) => p && setDataset(p),
                );
              }}
            >
              选择
            </Btn>
          </div>
          <div className={ROW}>
            <span className={LABEL}>音色名</span>
            <input
              className={`flex-1 min-w-0 ${FIELD}`}
              value={name}
              placeholder="训完就是这个名字"
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className={ROW}>
            <span className={`${LABEL} flex items-center gap-1.5`}>
              采样率
              <HelpMark title={tip("底模")} />
            </span>
            <select
              className={FIELD}
              value={sr}
              onChange={(e) => setSr(e.target.value)}
            >
              {(st.pretrained || [{ sample_rate: "48k", ready: false }]).map((p) => (
                <option key={p.sample_rate} value={p.sample_rate}>
                  {p.sample_rate}
                  {p.ready ? "" : "（缺底模）"}
                </option>
              ))}
            </select>
            <span className="text-[12px] text-[var(--meta)]">
              48k 音质最佳，但显存占用更高
            </span>
          </div>
          <div className={ROW}>
            <span className={LABEL}>训练轮数</span>
            <input
              className={`w-[100px] ${FIELD}`}
              type="number"
              min={1}
              max={1000}
              value={epochs}
              onChange={(e) => setEpochs(Number(e.target.value) || 1)}
            />
            <span className="text-[12px] text-[var(--meta)]">
              通常设为 200。轮数越多还原度越高，但过高可能产生电音或杂音。
            </span>
          </div>
        </div>

        {resume ? (
          <p className="m-0 mt-3 text-[12.5px] text-[var(--meta)]">
            「{name.trim()}」已经有 {existing?.slices} 条切片，这次会接着上次跑，
            不用重新切片。
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
            </p>
          </div>
        ) : null}

        {msg ? (
          <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)] break-all">
            {msg}
          </p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2.5">
          {running ? (
            <Btn onClick={() => void invoke("train_cancel")}>中断</Btn>
          ) : null}
          <Btn
            primary
            disabled={running || !!blocked.text || !name.trim() || (!dataset && !resume)}
            onClick={() => void start()}
          >
            {running ? "训练中…" : resume ? "继续训练" : "开始训练"}
          </Btn>
        </div>

        {running ? (
          <p className="m-0 mt-3 text-[12px] text-[var(--meta)]">
            训练过程可能需要数小时。中断后进度将保留（含已处理的切片与已完成的轮次），
            下次使用相同名称即可恢复训练。
          </p>
        ) : null}

        <ExtrasDialog
          open={extrasOpen}
          onClose={() => {
            setExtrasOpen(false);
            void load();
          }}
          filter="train"
          title="下载训练底模"
        />
    </ToolBody>
  );
}
