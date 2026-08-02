import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { RangeBar } from "./controls";
import { ToolBody } from "./ToolWindow";

type Status = {
  runtime_ready?: boolean;
  infer_present?: boolean;
  /** 系统里装了的 TTS 嗓子。中文系统一般有 Huihui / Yaoyao / Kangkang。 */
  voices?: string[];
  model_path?: string;
  model_name?: string;
  out_dir?: string;
  max_chars?: number;
  busy?: boolean;
};

type Progress = {
  phase: "sapi" | "rvc" | "done" | "error";
  done: number;
  total: number;
  message: string;
};

const ROW = "flex items-center gap-3 py-2.5";
const LABEL = "w-[86px] shrink-0 text-[13px]";

/**
 * 语音合成：打一段字，用当前选中的音色念出来。
 *
 * 两步走 —— 系统自带的 TTS 先把字念成人声，再由 RVC 把音色换成用户选的那个。
 * 界面上不体现这两步，只在进度里说一句现在在干哪一步：用户要的是「用这个音色
 * 念这段话」，中间怎么实现的不是他该操心的事。
 */
export function TtsPanel() {
  const [st, setSt] = useState<Status>({});
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
        const s = await invoke<Status>("tts_status");
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

  // 拦住合成的原因。没嗓子是最要命的一条，而且用户完全不知道那是系统的事，
  // 所以要把去哪儿装说清楚。
  const blocked = !st.voices?.length
    ? "系统里没有可用的语音。到「Windows 设置 → 时间和语言 → 语音」里添加一个语音包。"
    : useRvc && !st.model_path
      ? "还没有选中的音色。到主窗口首页选一个，或者关掉下面的「换成我的音色」。"
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

  const pct = prog?.total ? Math.round((prog.done / prog.total) * 100) : 0;

  return (
    <ToolBody>
      <h3 className="m-0 mb-1 text-[17px] font-semibold">语音合成</h3>
      <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)]">
        打一段字，用你选中的音色念出来。产出的 wav 存在 User_Data\tts 里。
      </p>

      {blocked ? (
        <p className="m-0 mb-4 text-[13px] text-[#b8534f]">{blocked}</p>
      ) : null}

      <textarea
        className={[
          "w-full min-h-[132px] rounded-[var(--rs)] border px-3 py-2.5 text-[13.5px] leading-relaxed",
          "bg-transparent text-[var(--ink)] resize-y",
          over ? "border-[#b8534f]" : "border-[var(--hairline)]",
        ].join(" ")}
        placeholder="要念的话写在这里。"
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
            className="flex-1 min-w-0 rounded-[var(--rs)] border border-[var(--hairline)] bg-transparent px-2 py-1.5 text-[13px]"
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
              onChange={setPitch}
              ariaLabel="音高"
            />
          </div>
          <span className="w-[52px] text-right text-[13px] tabular-nums">
            {pitch > 0 ? `+${pitch}` : pitch}
          </span>
        </div>
        <div className={ROW}>
          <span className={LABEL}>换成我的音色</span>
          <label className="flex items-center gap-2 text-[13px] cursor-pointer">
            <input
              type="checkbox"
              checked={useRvc}
              onChange={(e) => setUseRvc(e.target.checked)}
            />
            {st.model_name || "未选择模型"}
          </label>
          <span className="text-[12px] text-[var(--meta)]">
            关掉就只留系统嗓音，快很多
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
    </ToolBody>
  );
}
