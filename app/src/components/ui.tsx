import type { ReactNode } from "react";

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
  note,
  action,
  children,
  className = "",
}: {
  title?: string;
  note?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`mt-[30px] ${className}`}>
      {(title || note || action) && (
        <div className="flex items-baseline gap-[11px] mb-[15px] flex-wrap">
          {title ? <h3 className="text-[15.5px] font-semibold m-0">{title}</h3> : null}
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
  desc,
  meta,
  right,
  clickable = false,
}: {
  title?: string;
  desc?: string;
  meta?: string;
  right?: ReactNode;
  clickable?: boolean;
}) {
  return (
    <div
      className={[
        "flex items-center gap-3.5 py-3.5 rounded-[var(--rs)]",
        clickable
          ? "cursor-pointer -mx-3.5 px-3.5 hover:bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] transition-colors"
          : "",
      ].join(" ")}
    >
      <div className="min-w-0">
        {meta ? (
          <span className="block text-[11.5px] text-[var(--meta)] mb-0.5">{meta}</span>
        ) : null}
        {title ? <span className="block text-sm leading-snug">{title}</span> : null}
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
}

export function HelpMark({ title }: { title: string }) {
  return (
    <span
      title={title}
      className="w-[17px] h-[17px] rounded-full text-[var(--meta)] text-[11px] inline-grid place-items-center cursor-help shadow-[inset_0_0_0_1px_var(--line)] transition-[color,box-shadow,transform] duration-200 ease-[var(--spring)] hover:text-[var(--accent)] hover:shadow-[inset_0_0_0_1px_var(--accent)] hover:scale-110"
    >
      ?
    </span>
  );
}
