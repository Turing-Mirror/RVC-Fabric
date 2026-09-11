import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useRef, useState } from "react";
import { Btn } from "./ui";
import { runtimeVariantLabel } from "../lib/engine";
import { useI18n } from "../i18n";

type MigrationOption = { id: string; label: string };

type MigrationStatus = {
  required?: boolean;
  needs_variant?: boolean;
  variant?: string | null;
  version?: string;
  options?: MigrationOption[];
};

type MigrationProgress = {
  phase?: string;
  percent?: number;
  message?: string;
};

type Props = {
  open: boolean;
  onDone: () => void;
};

const FALLBACK_OPTIONS: MigrationOption[] = [
  { id: "nvidia", label: "NVIDIA" },
  { id: "nvidia50", label: "NVIDIA 50" },
  { id: "amd", label: "AMD / Intel" },
];

export function RuntimeMigrationDialog({ open, onDone }: Props) {
  const { t } = useI18n();
  const [status, setStatus] = useState<MigrationStatus | null>(null);
  const [progress, setProgress] = useState<MigrationProgress | null>(null);
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const started = useRef(false);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    if (!open) {
      started.current = false;
      return;
    }

    let disposed = false;
    let unlisten: (() => void) | undefined;

    const start = async (variant?: string) => {
      if (disposed) return;
      setBusy(true);
      setError("");
      try {
        const result = await invoke<{ ok?: boolean }>("runtime_migration_start", {
          variant: variant || null,
        });
        if (!disposed && result?.ok) doneRef.current();
      } catch (e) {
        if (!disposed) setError(String(e));
      } finally {
        if (!disposed) setBusy(false);
      }
    };

    void listen<MigrationProgress>("runtime-migration-progress", (event) => {
      if (!disposed) setProgress(event.payload);
    }).then((fn) => {
      if (disposed) fn();
      else unlisten = fn;
    });

    void invoke<MigrationStatus>("runtime_migration_status")
      .then((next) => {
        if (disposed) return;
        setStatus(next);
        if (!next.required) {
          doneRef.current();
          return;
        }
        if (!next.needs_variant && !started.current) {
          started.current = true;
          void start();
        }
      })
      .catch((e) => {
        if (!disposed) setError(String(e));
      });

    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [open]);

  if (!open) return null;

  const options = status?.options?.length ? status.options : FALLBACK_OPTIONS;
  const percent = Math.min(100, Math.max(0, Number(progress?.percent || 0)));
  const selectedLabel = runtimeVariantLabel(choice) || choice;
  const waitingForChoice = status?.needs_variant === true && !busy;
  const migrationInProgress =
    !error &&
    (busy || ["prepare", "move", "verify"].includes(progress?.phase || ""));
  const description = waitingForChoice
    ? t("runtimeMigration.waitingDescription")
    : migrationInProgress
      ? t("runtimeMigration.runningDescription")
      : t("runtimeMigration.description");

  return (
    <div className="absolute inset-0 z-[60] flex items-center justify-center bg-[color-mix(in_srgb,var(--ink)_28%,transparent)] p-6">
      <div className="w-full max-w-[520px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-7">
        <h2 className="text-[22px] font-semibold m-0 mb-2">
          {t("runtimeMigration.title")}
        </h2>
        <p className="text-[13px] text-[var(--help)] m-0 mb-5 leading-relaxed">
          {description}
        </p>

        {waitingForChoice ? (
          <>
            <div className="text-[12.5px] text-[var(--meta)] mb-2">
              {t("runtimeMigration.selectVariant")}
            </div>
            <div className="flex flex-col gap-2 mb-5">
              {options.map((option) => {
                const selected = option.id === choice;
                return (
                  <button
                    key={option.id}
                    type="button"
                    disabled={busy}
                    onClick={() => setChoice(option.id)}
                    className={[
                      "text-left border-0 rounded-[var(--rs)] px-3.5 py-2.5 cursor-pointer text-[13.5px] transition-colors",
                      selected
                        ? "bg-[var(--accent-soft)] text-[var(--ink)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--accent)_40%,transparent)]"
                        : "bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] text-[var(--ink-muted)]",
                    ].join(" ")}
                  >
                    {runtimeVariantLabel(option.id) || option.label}
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <div className="mb-5">
            <div className="flex justify-between gap-3 text-[12px] text-[var(--meta)] mb-1.5">
              <span className="truncate">
                {progress?.message || t("runtimeMigration.preparing")}
              </span>
              <span className="shrink-0 tabular-nums">{percent.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-[color-mix(in_srgb,var(--ink)_10%,transparent)] overflow-hidden">
              <div
                className="h-full bg-[var(--accent)] rounded-full transition-[width] duration-200"
                style={{ width: `${Math.max(percent, busy ? 3 : 0)}%` }}
              />
            </div>
          </div>
        )}

        {status?.version ? (
          <p className="text-[11.5px] text-[var(--meta)] m-0 mb-3">
            {t("runtimeMigration.version", { v0: status.version })}
          </p>
        ) : null}
        {error ? (
          <p className="text-[12.5px] text-[#c43] m-0 mb-3 leading-relaxed whitespace-pre-line">
            {error}
          </p>
        ) : null}

        <div className="flex items-center gap-2 justify-end">
          {waitingForChoice ? (
            <Btn
              primary
              disabled={!choice || busy}
              onClick={() => {
                started.current = true;
                void (async () => {
                  setBusy(true);
                  setError("");
                  try {
                    const result = await invoke<{ ok?: boolean }>("runtime_migration_start", {
                      variant: choice,
                    });
                    if (result?.ok) doneRef.current();
                  } catch (e) {
                    setError(String(e));
                  } finally {
                    setBusy(false);
                  }
                })();
              }}
            >
              {busy
                ? t("runtimeMigration.busy")
                : t("runtimeMigration.continue", { v0: selectedLabel })}
            </Btn>
          ) : error ? (
            <Btn
              primary
              disabled={busy}
              onClick={() => {
                started.current = true;
                void invoke<{ ok?: boolean }>("runtime_migration_start", {
                  variant: null,
                })
                  .then((result) => {
                    if (result?.ok) doneRef.current();
                  })
                  .catch((e) => setError(String(e)));
              }}
            >
              {t("runtimeMigration.retry")}
            </Btn>
          ) : (
            <Btn disabled>{t("runtimeMigration.busy")}</Btn>
          )}
        </div>
      </div>
    </div>
  );
}
