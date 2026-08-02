import type { ReactNode } from "react";
import { HelpMark } from "./Tooltip";

export function PagePad({ children }: { children: ReactNode }) {
  return (
    <div className="px-[30px] pb-[34px] max-[1020px]:px-[22px] max-[1020px]:pb-[30px] max-[720px]:px-4 max-[720px]:pb-[26px]">
      {children}
    </div>
  );
}

export function PageHead({
  title,
  sub,
  actions,
}: {
  title: string;
  sub?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="pt-[26px] pb-1.5 flex items-end justify-between gap-4 flex-wrap">
      <div>
        <h2 className="text-[25px] font-semibold tracking-tight m-0 max-[860px]:text-[22px]">
          {title}
        </h2>
        {sub ? (
          <div className="text-[12.5px] text-[var(--meta)] mt-1.5">{sub}</div>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2 flex-wrap">{actions}</div> : null}
    </div>
  );
}

export function Block({
  title,
  titleTip,
  note,
  action,
  children,
  className = "",
}: {
  title?: string;
  /** 标题后面的小问号。专有名词的解释统一从 lib/glossary 取。 */
  titleTip?: string;
  note?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`mt-[30px] ${className}`}>
      {(title || note || action) && (
        <div className="flex items-baseline gap-[11px] mb-[15px] flex-wrap">
          {title ? (
            <h3 className="text-[15.5px] font-semibold m-0 flex items-center gap-1.5">
              {title}
              {titleTip ? <HelpMark title={titleTip} /> : null}
            </h3>
          ) : null}
          {note ? <span className="text-xs text-[var(--meta)]">{note}</span> : null}
          {action ? <span className="ml-auto">{action}</span> : null}
        </div>
      )}
      {children}
    </section>
  );
}

export function Group({ children }: { children: ReactNode }) {
  return (
    <div className="bg-[var(--group)] rounded-[var(--r)] px-5 py-2">{children}</div>
  );
}

export function Btn({
  children,
  primary = false,
  on = false,
  uw = false,
  disabled = false,
  onClick,
  className = "",
}: {
  children: ReactNode;
  primary?: boolean;
  on?: boolean;
  /** Equal width for 使用 / 使用中 */
  uw?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={[
        "text-[12.5px] border-0 rounded-[var(--rs)] cursor-pointer",
        "transition-[transform,background,color,box-shadow] duration-200 ease-[var(--ease)]",
        "active:scale-[0.955] focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2",
        uw ? "min-w-[74px] text-center px-0 py-1.5" : "px-[13px] py-1.5",
        primary
          ? "bg-[var(--accent)] text-[var(--accent-ink)] font-semibold shadow-none hover:brightness-95"
          : on
            ? "bg-transparent text-[var(--accent)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--accent)_42%,transparent)]"
            : "bg-transparent text-[var(--ink-muted)] shadow-[inset_0_0_0_1px_var(--line)] hover:text-[var(--ink)] hover:bg-[color-mix(in_srgb,var(--ink)_4%,transparent)]",
        disabled ? "cursor-default active:scale-100" : "",
        className,
      ].join(" ")}
    >
      {children}
    </button>
  );
}

export function ListItem({
  title,
  titleTip,
  desc,
  meta,
  right,
  children,
  clickable = false,
  expanded,
  onClick,
}: {
  title?: string;
  /** 标题后面的小问号。专有名词的解释统一从 lib/glossary 取。 */
  titleTip?: string;
  desc?: string;
  meta?: string;
  right?: ReactNode;
  /** Body revealed under the row; only rendered when `expanded`. */
  children?: ReactNode;
  clickable?: boolean;
  expanded?: boolean;
  onClick?: () => void;
}) {
  // `clickable` used to be styling only — rows could look interactive and be
  // completely inert, which is what the four 「展开」 rows on the help page were.
  const act = onClick;
  const isBtn = Boolean(act);
  const body = (
    <div
      role={isBtn ? "button" : undefined}
      tabIndex={isBtn ? 0 : undefined}
      aria-expanded={isBtn && expanded !== undefined ? expanded : undefined}
      onClick={act}
      onKeyDown={
        isBtn
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                act?.();
              }
            }
          : undefined
      }
      className={[
        "flex items-center gap-3.5 py-3.5 rounded-[var(--rs)]",
        clickable || isBtn
          ? "cursor-pointer -mx-3.5 px-3.5 hover:bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] transition-colors"
          : "",
        isBtn
          ? "focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-[-2px]"
          : "",
      ].join(" ")}
    >
      <div className="min-w-0">
        {meta ? (
          <span className="block text-[11.5px] text-[var(--meta)] mb-0.5">{meta}</span>
        ) : null}
        {title ? (
          <span className="flex items-center gap-1.5 text-sm leading-snug">
            {title}
            {titleTip ? <HelpMark title={titleTip} /> : null}
          </span>
        ) : null}
        {desc ? (
          <span className="block text-[12.5px] text-[var(--help)] mt-0.5 leading-relaxed">
            {desc}
          </span>
        ) : null}
      </div>
      {right ? (
        <div className="ml-auto flex-none flex items-center gap-2">{right}</div>
      ) : null}
    </div>
  );
  if (!children) return body;
  return (
    <div>
      {body}
      {/* 正文和标题行之间要留出气口。原来是 -mt-1，正文顶边正好压在标题行
          悬停灰底的底边上 —— 鼠标停在标题上时，灰块下沿和文字挨成一条，
          看着像文字被切了一刀。 */}
      {expanded ? (
        <div className="pt-2 pb-4 text-[12.5px] text-[var(--ink-muted)] leading-relaxed whitespace-pre-line max-w-[74ch]">
          {children}
        </div>
      ) : null}
    </div>
  );
}

/**
 * 小问号。真身在 `Tooltip.tsx` —— 这里只是把名字接着导出，免得十几个
 * 引用处全部改 import。
 *
 * 它以前是个带原生 `title` 的 `<span>`：要悬停一秒多才出提示、样式由操作
 * 系统画、而且在 `<label>` 里会把点击转给它管的开关（点一下说明，功能被
 * 切了）。三件事都在 Tooltip 里治好了。
 */
export { HelpMark };
