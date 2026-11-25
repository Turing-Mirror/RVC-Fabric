import { useMemo } from "react";
import { ErrorNote as SharedErrorNote } from "trm-ui";
import { actionsFor, diagnosticOf, legacyDiagnostic, contentFor, type Diagnostic, type Feature } from "../lib/diagnostics";
import { diagnosticActions, type TrainingCopy } from "../lib/diagnosticActions";

export function ErrorNote({
  text, diagnostic, feature = "other", error = true, localOnly = false, extraAction, onEditTrainingCopy,
}: {
  text?: unknown;
  diagnostic?: Diagnostic | null;
  feature?: Feature;
  compact?: boolean;
  localOnly?: boolean;
  error?: boolean;
  code?: string | null;
  extraAction?: { label: string; run: () => void | Promise<unknown> } | null;
  onEditTrainingCopy?: (request: TrainingCopy) => Promise<void>;
}) {
  const value = useMemo(() => diagnostic ?? diagnosticOf(text) ?? legacyDiagnostic(text, feature), [diagnostic, text, feature]);
  if (!text && !diagnostic) return null;
  if (!error) return <p className="m-0 mt-3 text-[12.5px] text-[var(--ink-muted)] break-all leading-relaxed whitespace-pre-wrap">{String(text ?? "")}</p>;
  if (value.code === "diag.cancelled" || value.code === "diag.recovered") return null;
  const actions = actionsFor(value, localOnly ? {} : diagnosticActions(onEditTrainingCopy));
  if (extraAction) actions.unshift({ label: extraAction.label, run: async () => { await extraAction.run(); } });
  return <SharedErrorNote key={value.error_id} content={contentFor(value, feature)} actions={actions} />;
}
