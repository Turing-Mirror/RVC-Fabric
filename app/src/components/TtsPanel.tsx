import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { RangeBar } from "./controls";
import { SegmentControl } from "./SegmentControl";
import { ToolBody } from "./ToolWindow";

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
      <h3 className="m-0 mb-1 text-[17px] font-semibold">语音转换</h3>
      <p className="m-0 mb-3 text-[12.5px] text-[var(--ink-muted)]">
        音频变声把已有录音换成目标音色；文字合成用系统语音念字后再换音色。
        二者都使用首页当前选中的 RVC 模型。
      </p>
      <div className="mb-4">
        <SegmentControl<Mode>
          value={mode}
          onChange={setMode}
          options={[
            { id: "sts", label: "音频变声" },
            { id: "tts", label: "文字合成" },
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
    ? "运行时未就绪，先到「其他」页补全运行时"
    : st.engine_core_ready === false
      ? `引擎资源未补全（缺 ${(st.engine_core_missing || []).join("、") || "hubert/rmvpe"}）。请先在主界面完成引擎资源下载。`
      : !st.worker_present
        ? "缺少转换脚本，安装可能不完整"
        : !st.model_path
          ? "未选择目标音色。请到首页或「模型」页先选一个音色。"
          : "";

  const start = async () => {
    if (runningRef.current) return;
    setMsg("");
    setProg(null);
    runningRef.current = true;
    setRunning(true);
    try {
      const r = await invoke<{ files?: string[]; output?: string }>("sts_start", {
        input,
        output,
        pitch,
        f0method,
        indexRate,
      });
      setMsg(
        `完成 ${r.files?.length ?? 0} 个文件${r.output ? ` → ${r.output}` : ""}`,
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
          当前音色：{st.model_name || "—"}
          {st.index_path ? " · 已绑定检索库" : ""}
        </p>
      )}

      <div className="border-t border-[var(--hairline)]">
        <div className={ROW}>
          <span className={LABEL}>输入</span>
          <span className={PATH}>{input || "未选择（文件或文件夹）"}</span>
          <Btn
            onClick={() => {
              void invoke<string | null>("sts_pick_input", { folder: false }).then(
                (p) => p && setInput(p),
              );
            }}
          >
            文件
          </Btn>
          <Btn
            onClick={() => {
              void invoke<string | null>("sts_pick_input", { folder: true }).then(
                (p) => p && setInput(p),
              );
            }}
          >
            文件夹
          </Btn>
        </div>
        <div className={ROW}>
          <span className={LABEL}>输出到</span>
          <span className={PATH}>{output || "未选择"}</span>
          <Btn
            onClick={() => {
              void invoke<string | null>("sts_pick_output").then(
                (p) => p && setOutput(p),
              );
            }}
          >
            选择
          </Btn>
        </div>
        <div className={ROW}>
          <span className={LABEL}>音高</span>
          <div className="flex-1">
            <RangeBar
              value={pitch}
              min={-24}
              max={24}
              step={1}
              defaultValue={0}
              onChange={setPitch}
              ariaLabel="音高"
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {pitch > 0 ? `+${pitch}` : pitch}
          </span>
        </div>
        <div className={ROW}>
          <span className={LABEL}>音高算法</span>
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
          <span className={LABEL}>检索强度</span>
          <div className="flex-1">
            <RangeBar
              value={indexRate}
              min={0}
              max={1}
              step={0.01}
              defaultValue={0.75}
              onChange={setIndexRate}
              ariaLabel="检索强度"
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

      <div className="mt-5 flex justify-end gap-2.5">
        {running ? (
          <Btn onClick={() => void invoke("sts_cancel")}>取消</Btn>
        ) : (
          <Btn onClick={() => void invoke("sts_reveal")}>打开输出目录</Btn>
        )}
        <Btn
          primary
          disabled={running || !!blocked || !input}
          onClick={() => void start()}
        >
          {running ? "转换中…" : "开始转换"}
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
    ? "系统里没有可用的语音。到「Windows 设置 → 时间和语言 → 语音」里添加一个语音包。"
    : useRvc && !st.model_path
      ? "未选择目标音色。请到首页选择一个音色，或关闭下方的「使用变声」。"
      : useRvc && !st.runtime_ready
        ? "运行时未就绪，先到「其他」页补全运行时"
        : useRvc && !st.infer_present
          ? "缺少推理脚本，安装可能不完整"
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
      setMsg(`合成完成：${r.file ?? ""}`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  };

  return (
    <>
      <p className="m-0 mb-3 text-[12.5px] text-[var(--meta)]">
        系统语音负责吐字，可选再经 RVC 换成目标音色。结果在 User_Data\tts。
      </p>

      {blocked ? (
        <p className="m-0 mb-4 text-[13px] text-[#b8534f]">{blocked}</p>
      ) : null}

      <textarea
        className={[
          "w-full min-h-[120px] rounded-[var(--rs)] border px-3 py-2.5 text-[13.5px] leading-relaxed",
          "bg-transparent text-[var(--ink)] resize-y",
          over ? "border-[#b8534f]" : "border-[var(--hairline)]",
        ].join(" ")}
        placeholder="请输入需要合成的文本…"
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
          <span className={LABEL}>朗读嗓音</span>
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
            {!st.voices?.length ? <option value="">（无）</option> : null}
          </select>
        </div>
        <div className={ROW}>
          <span className={LABEL}>语速</span>
          <div className="flex-1">
            <RangeBar
              value={rate}
              min={-6}
              max={6}
              step={1}
              onChange={setRate}
              ariaLabel="语速"
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {rate > 0 ? `+${rate}` : rate}
          </span>
        </div>
        <div className={ROW}>
          <span className={LABEL}>音高</span>
          <div className="flex-1">
            <RangeBar
              value={pitch}
              min={-12}
              max={12}
              step={1}
              defaultValue={0}
              onChange={setPitch}
              ariaLabel="音高"
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {pitch > 0 ? `+${pitch}` : pitch}
          </span>
        </div>
        <div className={ROW}>
          <span className={LABEL}>使用变声</span>
          <label className="flex items-center gap-2 text-[13px] cursor-pointer">
            <input
              type="checkbox"
              checked={useRvc}
              onChange={(e) => setUseRvc(e.target.checked)}
            />
            {st.model_name || "未选择音色"}
          </label>
          <span className="text-[12px] text-[var(--meta)]">
            关闭后仅输出系统原声
          </span>
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
          <Btn onClick={() => void invoke("tts_cancel")}>取消</Btn>
        ) : (
          <Btn onClick={() => void invoke("tts_reveal")}>打开输出目录</Btn>
        )}
        <Btn
          primary
          disabled={running || !!blocked || !text.trim() || over}
          onClick={() => void start()}
        >
          {running ? "合成中…" : "开始合成"}
        </Btn>
      </div>
    </>
  );
}
