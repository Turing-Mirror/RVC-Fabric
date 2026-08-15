import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { openDownloadModels } from "../lib/downloadModels";
import { ToolBody } from "./ToolWindow";
import { t } from "../i18n/t";

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
export function SeparatePanel() {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 开一次窗只挂一次
  }, []);

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
      setMsg(t("s.8efd7ca6b1", { v0: r.files?.length ?? 0 }));
    } catch (e) {
      setMsg(String(e));
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  };

  const needModels = !!st.runtime_ready && !!st.worker_present && !st.models?.length;
  const blocked = !st.runtime_ready
    ? t("s.bc45fc14b1")
    : !st.worker_present
      ? t("s.92ba5de60f")
      : needModels
        ? t("s.f8893054c2")
        : "";

  const pct = prog?.total ? Math.round((prog.done / prog.total) * 100) : 0;

  return (
    <ToolBody>
        <h3 className="m-0 mb-1 text-[17px] font-semibold">{t("s.8fd038283b")}</h3>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)]">{t("s.497e7d9af6")}</p>

        {blocked ? (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <p className="m-0 text-[13px] text-[#b8534f]">{blocked}</p>
            {needModels ? (
              <Btn
                onClick={() => openDownloadModels({ filter: "separate" })}
              >{t("s.7a218555fd")}</Btn>
            ) : null}
          </div>
        ) : (
          <div className="mb-3 flex justify-end">
            <Btn onClick={() => openDownloadModels({ filter: "separate" })}>{t("s.1252c81119")}</Btn>
          </div>
        )}

        <div className="border-t border-[var(--hairline)]">
          <div className={ROW}>
            <span className="w-[64px] shrink-0 text-[13px]">{t("s.e8850440f2")}</span>
            <span className={PATH}>{input || t("s.53e2db7016")}</span>
            <Btn onClick={() => void pick(false)}>{t("s.70b208202c")}</Btn>
          </div>
          <div className={ROW}>
            <span className="w-[64px] shrink-0 text-[13px]">{t("s.a0bc984876")}</span>
            <span className={PATH}>{output || t("s.53e2db7016")}</span>
            <Btn onClick={() => void pick(true)}>{t("s.70b208202c")}</Btn>
          </div>
          <div className={ROW}>
            <span className="w-[64px] shrink-0 text-[13px]">{t("s.98fd0cbd9c")}</span>
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
              {!st.models?.length ? <option value="">{t("s.6238bf9ad5")}</option> : null}
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
            <Btn onClick={() => void invoke("separate_cancel")}>{t("s.4d0b4688c7")}</Btn>
          ) : null}
          <Btn
            primary
            disabled={running || !!blocked || !input || !output}
            onClick={() => void start()}
          >
            {running ? t("s.2282c91c77") : t("s.8c57156c9d")}
          </Btn>
        </div>

    </ToolBody>
  );
}
