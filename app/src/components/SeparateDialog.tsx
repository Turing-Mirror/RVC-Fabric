import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";

type Status = {
  runtime_ready?: boolean;
  worker_present?: boolean;
  model_dir?: string;
  models?: string[];
  busy?: boolean;
};

type Progress = {
  phase: "start" | "run" | "done" | "error";
  done: number;
  total: number;
  message: string;
};

const ROW = "flex items-center gap-3 py-2.5";
const PATH =
  "flex-1 min-w-0 truncate text-[12.5px] text-[var(--ink-muted)] font-mono";

/**
 * 人声分离（PyMSS）。
 *
 * 一次一个文件，没有队列 —— 分离很吃显存，排队跑只会让人以为卡死了。要批量
 * 的话再说，先把单个跑通。
 */
export function SeparateDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [st, setSt] = useState<Status>({});
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [model, setModel] = useState("");
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  const [running, setRunning] = useState(false);
  const runningRef = useRef(false);

  const load = async () => {
    try {
      const s = await invoke<Status>("separate_status");
      setSt(s);
      if (!model && s.models?.length) setModel(s.models[0]);
    } catch (e) {
      setMsg(String(e));
    }
  };

  useEffect(() => {
    if (!open) return;
    void load();
    // listen() 是异步的，弹窗在它 resolve 之前关掉就会把注销句柄丢掉，
    // 每开一次泄漏一个监听。和 App.tsx 里一样的处理。
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<Progress>("separate-progress", (ev) => {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const pick = async (dir: boolean) => {
    try {
      const p = await invoke<string | null>("separate_pick", { dir });
      if (!p) return;
      if (dir) setOutput(p);
      else setInput(p);
    } catch (e) {
      setMsg(String(e));
    }
  };

  const start = async () => {
    if (runningRef.current) return;
    setMsg("");
    setProg(null);
    runningRef.current = true;
    setRunning(true);
    try {
      const r = await invoke<{ files?: string[] }>("separate_start", {
        input,
        output,
        model,
      });
      setMsg(`完成，输出 ${r.files?.length ?? 0} 个文件`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  };

  const blocked = !st.runtime_ready
    ? "Runtime 未就绪，先到「其他」页补全运行时"
    : !st.worker_present
      ? "缺分离脚本，安装可能不完整"
      : !st.models?.length
        ? "还没有分离模型，先在「音频工具 → 下载模型」里下载"
        : "";

  const pct = prog?.total ? Math.round((prog.done / prog.total) * 100) : 0;

  return (
    <div
      className="fixed inset-0 z-[80] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[560px] rounded-[var(--r)] bg-[var(--surface)] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="m-0 mb-1 text-[17px] font-semibold">人声分离</h3>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)]">
          把歌曲拆成人声和伴奏。训练音色前用它清掉背景音乐。
        </p>

        {blocked ? (
          <p className="m-0 mb-4 text-[13px] text-[#b8534f]">{blocked}</p>
        ) : null}

        <div className="border-t border-[var(--hairline)]">
          <div className={ROW}>
            <span className="w-[64px] shrink-0 text-[13px]">输入</span>
            <span className={PATH}>{input || "未选择"}</span>
            <Btn onClick={() => void pick(false)}>选择</Btn>
          </div>
          <div className={ROW}>
            <span className="w-[64px] shrink-0 text-[13px]">输出到</span>
            <span className={PATH}>{output || "未选择"}</span>
            <Btn onClick={() => void pick(true)}>选择</Btn>
          </div>
          <div className={ROW}>
            <span className="w-[64px] shrink-0 text-[13px]">模型</span>
            <select
              className="flex-1 min-w-0 rounded-[var(--rs)] border border-[var(--hairline)] bg-transparent px-2 py-1.5 text-[13px]"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {(st.models || []).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
              {!st.models?.length ? <option value="">（无）</option> : null}
            </select>
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
          <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)]">{msg}</p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2.5">
          {running ? (
            <Btn onClick={() => void invoke("separate_cancel")}>取消</Btn>
          ) : (
            <Btn onClick={onClose}>关闭</Btn>
          )}
          <Btn
            primary
            disabled={running || !!blocked || !input || !output}
            onClick={() => void start()}
          >
            {running ? "分离中…" : "开始分离"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
