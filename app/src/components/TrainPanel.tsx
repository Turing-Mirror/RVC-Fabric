import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn, HelpMark } from "./ui";
import { tip } from "../lib/glossary";
import { ExtrasDialog } from "./ExtrasDialog";
import { ToolBody } from "./ToolWindow";
import { t } from "../i18n/t";

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
  const stageLabel = prog?.stage ? stageName(prog.stage) : "";
  const stepLine =
    prog?.index && prog?.total_stages
      ? t("s.588a754143", { v0: prog.index, v1: prog.total_stages, v2: stageLabel })
      : "";

  return (
    <ToolBody>
        <h3 className="m-0 mb-1 text-[17px] font-semibold">{t("s.ba65bd5595")}</h3>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)]">{t("s.42667034ec")}</p>

        {blocked.text ? (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <p className="m-0 text-[13px] text-[#b8534f] flex items-center gap-1.5">
              {blocked.text}
              {blocked.term ? <HelpMark title={tip(blocked.term)} /> : null}
            </p>
            {needPretrained ? (
              <Btn onClick={() => setExtrasOpen(true)}>{t("s.0c593a479c")}</Btn>
            ) : null}
          </div>
        ) : (
          <div className="mb-3 flex justify-end">
            <Btn onClick={() => setExtrasOpen(true)}>{t("s.aac4f88e84")}</Btn>
          </div>
        )}

        <div className="border-t border-[var(--hairline)]">
          <div className={ROW}>
            <span className={LABEL}>{t("s.10c5cf2954")}</span>
            <span className={PATH}>{dataset || t("s.53e2db7016")}</span>
            <Btn
              onClick={() => {
                void invoke<string | null>("train_pick_dataset").then(
                  (p) => p && setDataset(p),
                );
              }}
            >{t("s.70b208202c")}</Btn>
          </div>
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

        {running ? (
          <p className="m-0 mt-3 text-[12px] text-[var(--meta)]">{t("s.8a5ef195d6")}</p>
        ) : null}

        <ExtrasDialog
          open={extrasOpen}
          onClose={() => {
            setExtrasOpen(false);
            void load();
          }}
          filter="train"
          title={t("s.0c593a479c")}
        />
    </ToolBody>
  );
}
