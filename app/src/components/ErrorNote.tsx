import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import { t } from "../i18n/t";
import { actionFor } from "../lib/errorActions";

/**
 * 面板里那行报错。
 *
 * 以前是一个裸的 `<p>{msg}</p>`：一整条 traceback 直接铺在面板上，用户截图发
 * 群里，我们再从几十行 `D:\RVC Fabric\Runtime\lib\site-packages\...` 里找那句
 * 真正有用的。
 *
 * 现在正文只留第一行，剩下的收进「详情」。但收起来有个代价 —— 我们在群里问
 * 「报什么错」时，用户的截图会只剩一行。所以「复制完整错误」必须一按就有，
 * 而且完整内容一个字都不能少地进日志和诊断包（那条本来就在，不归这里管）。
 */
export function ErrorNote({
  text,
  error = true,
  code,
  extraAction,
}: {
  text: string;
  /**
   * 这句话是报错还是结果。
   *
   * 面板那一格既报错也报成功（「已提取 xxx.pth」和一条 traceback 走同一个
   * useState）。在「完成 8 个文件」底下摆一个「复制完整错误」，用户会以为
   * 出事了。所以由面板告诉我们是哪一种，不猜。
   */
  error?: boolean;
  /** worker 的 message_code，配得上按钮就多一个按钮。 */
  code?: string | null;
  /** 面板自己才做得到的动作（比如训练窗的「模型提取」）。 */
  extraAction?: { label: string; run: () => void } | null;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  if (!text) return null;
  if (!error) {
    return (
      <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)] break-all leading-relaxed whitespace-pre-wrap">
        {text}
      </p>
    );
  }

  const lines = text.split("\n").filter((l) => l.trim().length > 0);
  const head = lines[0] || text;
  const hasMore = lines.length > 1;
  const action = extraAction ?? actionFor(code);

  const done = () => {
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };
  const copy = () => {
    // 退回 execCommand 是因为「按了没反应」比没有这个按钮还伤 —— 而我们在群里
    // 要用户复制报错的时候，正是他最不该再碰一次钉子的时候。
    const fallback = () => {
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        done();
      } catch {
        /* 真的复制不了就别装作复制成功 */
      }
    };
    try {
      void navigator.clipboard.writeText(text).then(done).catch(fallback);
    } catch {
      fallback();
    }
  };

  return (
    <div className="mt-3">
      <p className="m-0 text-[12.5px] text-[var(--ink-muted)] break-all leading-relaxed">
        {head}
      </p>
      {open && hasMore ? (
        <pre className="mt-1.5 mb-0 max-h-[168px] overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] text-[var(--meta)] leading-relaxed">
          {lines.slice(1).join("\n")}
        </pre>
      ) : null}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {action ? (
          <Btn primary onClick={action.run}>
            {action.label}
          </Btn>
        ) : null}
        {hasMore ? (
          <Btn onClick={() => setOpen((v) => !v)}>
            {open ? t("s.errDetailsHide") : t("s.errDetails")}
          </Btn>
        ) : null}
        <Btn onClick={copy}>{copied ? t("s.errCopied") : t("s.errCopy")}</Btn>
        <Btn
          onClick={() => {
            void invoke("reveal_user_dir", { name: "logs" }).catch(() => {});
          }}
        >
          {t("s.errOpenLog")}
        </Btn>
      </div>
    </div>
  );
}
