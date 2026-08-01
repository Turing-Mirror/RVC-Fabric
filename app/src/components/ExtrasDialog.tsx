import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";

type Item = {
  key: string;
  label: string;
  dest: string;
  size_bytes: number;
  files: string[];
  installed: boolean;
};

type List = { available?: boolean; items?: Item[]; busy?: boolean };

type Progress = {
  key: string;
  phase: "run" | "done" | "error";
  done?: number;
  total?: number;
  message?: string;
};

function mb(n: number) {
  if (!n) return "";
  return n >= 1024 * 1024 * 1024
    ? `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`
    : `${Math.round(n / 1024 / 1024)} MB`;
}

/**
 * 附加资源下载：分离模型、训练底模。
 *
 * 列表来自线上清单而不是写死在客户端里 —— 每加一个模型就发一版客户端，
 * 谁都受不了。清单拉不到就直说「取不到」，不要给一个空列表让人以为没东西下。
 */
export function ExtrasDialog({
  open,
  onClose,
  filter,
  title,
}: {
  open: boolean;
  onClose: () => void;
  /** 只显示 key 以此开头的条目；不给就全显示。 */
  filter?: string;
  title?: string;
}) {
  const [list, setList] = useState<List | null>(null);
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  const [busyKey, setBusyKey] = useState("");
  const busyRef = useRef(false);

  const load = async () => {
    setMsg("");
    try {
      setList(await invoke<List>("extra_list"));
    } catch (e) {
      setList({ available: false, items: [] });
      setMsg(String(e));
    }
  };

  useEffect(() => {
    if (!open) return;
    setList(null);
    void load();
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<Progress>("extra-progress", (ev) => {
      setProg(ev.payload);
      if (ev.payload.phase === "error") setMsg(ev.payload.message || "下载失败");
    }).then((fn) => {
      if (disposed) fn();
      else un = fn;
    });
    return () => {
      disposed = true;
      un?.();
    };
     
  }, [open]);

  if (!open) return null;

  const start = async (key: string) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusyKey(key);
    setMsg("");
    setProg(null);
    try {
      await invoke("extra_download", { key });
      setMsg("下载完成");
      void load();
    } catch (e) {
      setMsg(String(e));
    } finally {
      busyRef.current = false;
      setBusyKey("");
    }
  };

  const items = (list?.items || []).filter(
    (i) => !filter || i.key.startsWith(filter),
  );
  const pct =
    prog?.total ? Math.round(((prog.done ?? 0) / prog.total) * 100) : 0;

  return (
    <div
      className="fixed inset-0 z-[80] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={busyKey ? undefined : onClose}
    >
      <div
        className="w-full max-w-[560px] rounded-[var(--r)] bg-[var(--surface)] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="m-0 mb-1 text-[17px] font-semibold">{title || "下载模型"}</h3>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)]">
          都是大文件，走我们自己的发布仓下载，下完会校验完整性。
        </p>

        {list === null ? (
          <p className="m-0 py-4 text-[13px] text-[var(--meta)]">正在读取清单…</p>
        ) : items.length === 0 ? (
          <p className="m-0 py-4 text-[13px] text-[var(--ink-muted)]">
            {list.available === false
              ? "暂时无法获取下载清单，检查网络后再试。"
              : "清单里目前没有可下载的项目。"}
          </p>
        ) : (
          <div className="border-t border-[var(--hairline)]">
            {items.map((it) => (
              <div
                key={it.key}
                className="flex items-center gap-3 border-b border-[var(--hairline)] py-3"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px]">{it.label}</span>
                  <span className="block truncate text-[12px] text-[var(--meta)] font-mono">
                    {it.dest} · {mb(it.size_bytes)}
                  </span>
                </span>
                {it.installed ? (
                  <span className="text-[12.5px] text-[var(--ink-muted)]">已安装</span>
                ) : (
                  <Btn
                    disabled={!!busyKey}
                    onClick={() => void start(it.key)}
                  >
                    {busyKey === it.key ? "下载中…" : "下载"}
                  </Btn>
                )}
              </div>
            ))}
          </div>
        )}

        {busyKey && prog ? (
          <div className="mt-4">
            <div className="h-1 w-full overflow-hidden rounded bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
              <div
                className="h-full bg-[var(--accent)] transition-[width] duration-200"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="m-0 mt-2 text-[12px] text-[var(--meta)]">
              {prog.message} {pct}%
            </p>
          </div>
        ) : null}

        {msg ? (
          <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)] break-all">
            {msg}
          </p>
        ) : null}

        <div className="mt-5 flex justify-end gap-2.5">
          {busyKey ? (
            <Btn onClick={() => void invoke("extra_cancel")}>取消下载</Btn>
          ) : (
            <Btn onClick={onClose}>关闭</Btn>
          )}
        </div>
      </div>
    </div>
  );
}
