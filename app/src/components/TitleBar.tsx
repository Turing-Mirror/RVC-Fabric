import type { ReactNode } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { SegmentControl } from "./SegmentControl";
import { navPages, type PageId } from "../lib/nav";
import { useI18n } from "../i18n";
import wordmark from "../assets/logo_wordmark.png";

type Props = {
  page: PageId;
  onPage: (id: PageId) => void;
  plazaUnread?: boolean;
  compactNav?: boolean;
};

export function TitleBar({
  page,
  onPage,
  plazaUnread = true,
  compactNav = false,
}: Props) {
  const { t, locale } = useI18n();
  const win = () => {
    try {
      return getCurrentWindow();
    } catch {
      return null;
    }
  };

  // locale in deps so labels re-resolve when language changes
  const pages = navPages();
  void locale;

  const options = pages.map((p) => ({
    id: p.id as PageId,
    label: (
      <span className="inline-flex items-center">
        {p.label}
        {"badge" in p && p.badge && plazaUnread ? (
          <span
            className="inline-block w-[5px] h-[5px] rounded-full bg-[var(--notify)] ml-1.5 align-middle animate-[pulse_2.4s_var(--ease)_infinite]"
            aria-label={t("nav.newContent")}
          />
        ) : null}
      </span>
    ),
  }));

  // Keep the navigation hit area unchanged and give the title bar a little
  // more vertical breathing room. The old 54px bar left roughly 8px above
  // the 37px segment control, which made the menu feel pressed against the
  // top edge on the light background.
  return (
    <header
      className="flex-none h-[60px] flex items-center pl-[22px] pr-2"
      data-tauri-drag-region
    >
      <img
        src={wordmark}
        alt="RVC Fabric"
        draggable={false}
        data-tauri-drag-region
        className="h-[19px] w-auto select-none flex-none"
        style={{ filter: "var(--logo-filter)" }}
      />

      <div className="ml-auto flex items-center min-w-0" data-tauri-drag-region>
        <div
          className="min-w-0"
          onPointerDown={(e) => e.stopPropagation()}
        >
          <SegmentControl
            role="tablist"
            options={options}
            value={page}
            onChange={onPage}
            compact={compactNav}
          />
        </div>

        <div
          className="flex text-[var(--meta)] ml-3.5"
          onPointerDown={(e) => e.stopPropagation()}
        >
          <WinBtn
            label={t("window.minimize")}
            onClick={() => void win()?.minimize()}
          >
            —
          </WinBtn>
          <WinBtn
            label={t("window.maximize")}
            onClick={() => void win()?.toggleMaximize()}
          >
            □
          </WinBtn>
          <WinBtn
            label={t("window.close")}
            danger
            onClick={() => void win()?.close()}
          >
            ✕
          </WinBtn>
        </div>
      </div>
    </header>
  );
}

function WinBtn({
  children,
  label,
  onClick,
  danger = false,
}: {
  children: ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={[
        "w-10 h-[34px] grid place-items-center text-xs rounded-md border-0 bg-transparent cursor-pointer",
        "text-[var(--meta)] transition-[background,color] duration-150 ease-[var(--ease)]",
        danger
          ? "hover:bg-[#e81123] hover:text-white"
          : "hover:bg-[color-mix(in_srgb,var(--ink)_6%,transparent)] hover:text-[var(--ink)]",
      ].join(" ")}
    >
      {children}
    </button>
  );
}
