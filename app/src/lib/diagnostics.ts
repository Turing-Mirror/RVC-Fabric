import { t, type TVars } from "../i18n/t";
import type { ErrorNoteContent, ErrorNoteAction } from "trm-ui";

export type Feature = "training" | "synthesis" | "annotation" | "separation" | "voicechange" |
  "realtimevoicechange" | "recording" | "tts" | "download" | "update" | "provision" |
  "enginestart" | "importexport" | "store" | "settings" | "other";
export type DiagnosticMessage = { key: string; params: TVars };
export type DiagnosticAction = { id: string; params: Record<string, string | number> };
export type Diagnostic = {
  schema: 1; error_id: string;
  scope: { feature: Feature; stage: string | null; job_id: string | null; attempt: number | null };
  code: string; source_code: string | null; confidence: "confirmed" | "likely" | "unknown";
  title: DiagnosticMessage; cause: DiagnosticMessage | null; steps: DiagnosticMessage[];
  actions: DiagnosticAction[]; detail: { text: string; log_ref: string | null; truncated: boolean };
};

let sequence = 0;
export function diagnosticOf(value: unknown): Diagnostic | undefined {
  if (typeof value === "string") {
    try { return diagnosticOf(JSON.parse(value)); } catch { return undefined; }
  }
  if (!value || typeof value !== "object") return undefined;
  if ("diagnostic" in value) return diagnosticOf(value.diagnostic);
  if ("schema" in value && value.schema === 1 && "scope" in value && "title" in value &&
      "detail" in value && "actions" in value) return value as Diagnostic;
  return undefined;
}

export function rawError(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (value instanceof Error) return value.stack || value.message;
  try { return JSON.stringify(value) ?? String(value); } catch { return String(value); }
}

/** UI-only failures and old shells get an honest per-feature fallback. No keyword diagnosis. */
export function legacyDiagnostic(value: unknown, feature: Feature = "other"): Diagnostic {
  return {
    schema: 1, error_id: `ui-${Date.now()}-${++sequence}`,
    scope: { feature, stage: null, job_id: null, attempt: null },
    code: "diag.unknown", source_code: null, confidence: "unknown",
    title: { key: `diag.title.${feature}`, params: {} }, cause: null,
    steps: [{ key: "diag.step.copyAndCommunity", params: {} }],
    actions: [{ id: "copy_error", params: {} }, { id: "open_community", params: {} }],
    detail: { text: rawError(value), log_ref: null, truncated: false },
  };
}

/** Keeps structured evidence through existing string state without [object Object]. */
export function errorText(value: unknown): string {
  const diagnostic = diagnosticOf(value);
  return diagnostic ? JSON.stringify({ diagnostic }) : rawError(value);
}

/** Keeps diagnostic cause/steps/actions/detail while preserving a specific UI title key. */
export function errorWithTitle(
  value: unknown,
  key: string,
  feature: Feature = "other",
  params: TVars = {},
): string {
  const base = diagnosticOf(value) ?? legacyDiagnostic(value, feature);
  return errorText({
    ...base,
    scope: base.code === "diag.unknown" ? { ...base.scope, feature } : base.scope,
    title: { key, params },
  });
}

export function isCancelledError(value: unknown): boolean {
  const diagnostic = diagnosticOf(value);
  if (diagnostic) {
    return diagnostic.code === "diag.cancelled" || diagnostic.detail.text === t("s.a5ffdc95ee");
  }
  return String(value) === t("s.a5ffdc95ee");
}

export function contentFor(value: unknown, feature: Feature = "other"): ErrorNoteContent {
  const diagnostic = diagnosticOf(value) ?? legacyDiagnostic(value, feature);
  const resolve = (message: DiagnosticMessage) => t(message.key, message.params);
  const title = resolve(diagnostic.title);
  const cause = diagnostic.cause ? resolve(diagnostic.cause) : t("diag.cause.unknown");
  const steps = diagnostic.steps.map(resolve);
  const detail = diagnostic.detail.text +
    (diagnostic.detail.truncated ? `\n\n[truncated=true; log_ref=${diagnostic.detail.log_ref ?? "unavailable"}]` : "");
  const copy = [title, cause, ...steps.map((step, index) => `${index + 1}. ${step}`),
    `error_id: ${diagnostic.error_id}`, detail].filter(Boolean).join("\n");
  return { title, cause, steps, detail, copy };
}

export type ActionHandlers = Partial<Record<string, (params: DiagnosticAction["params"]) => Promise<unknown>>>;
export function actionsFor(diagnostic: Diagnostic, handlers: ActionHandlers): ErrorNoteAction[] {
  return diagnostic.actions.flatMap(action => {
    const run = handlers[action.id];
    // The shared component already renders the full-copy button.
    if (!run || action.id === "copy_error") return [];
    return [{ label: t(`diag.action.${action.id}`), run: async () => { await run(action.params); } }];
  });
}

export function errorSummary(value: unknown, feature: Feature = "other"): string {
  const content = contentFor(value, feature);
  return [content.title, content.cause].filter(Boolean).join(" ");
}

export class DiagnosticError extends Error {
  readonly diagnostic: Diagnostic;
  readonly code?: unknown;
  readonly details?: unknown;
  constructor(value: unknown, feature: Feature, overrideFeature = false) {
    const found = diagnosticOf(value);
    const diagnostic = found
      ? overrideFeature && found.scope.feature !== feature
        ? {
            ...found,
            scope: { ...found.scope, feature },
            title: found.title.key === `diag.title.${found.scope.feature}`
              ? { key: `diag.title.${feature}`, params: {} }
              : found.title,
          }
        : found
      : legacyDiagnostic(value, feature);
    super(JSON.stringify({ diagnostic }));
    this.name = "DiagnosticError";
    this.diagnostic = diagnostic;
    this.code = value && typeof value === "object" && "code" in value ? value.code : undefined;
    this.details = value && typeof value === "object" && "details" in value ? value.details : undefined;
  }
  override toString() { return this.message; }
}

export function commandFeature(command: string): Feature {
  if (command.startsWith("train_")) return "training";
  if (command.startsWith("tts_") || command === "voice_audition") return "tts";
  if (command.startsWith("separate_")) return "separation";
  if (command.startsWith("sts_record") || command.startsWith("mic_test")) return "recording";
  if (command.startsWith("sts_")) return "voicechange";
  if (command.startsWith("engine_start") || command === "engine_ensure") return "enginestart";
  if (command.startsWith("engine_") || command.startsWith("dsp_")) return "realtimevoicechange";
  if (command.startsWith("provision_") || command.startsWith("runtime_")) return "provision";
  if (command.startsWith("update_")) return "update";
  if (command.startsWith("extra_") || command.startsWith("assets_")) return "download";
  if (command.startsWith("store_") || command.startsWith("community_") || command.startsWith("plaza_")) return "store";
  if (command.startsWith("voices_") || command.startsWith("ckpt_") || command.startsWith("model_version")) return "importexport";
  if (command.startsWith("config_") || command.startsWith("audio_") || command.startsWith("hotkey")) return "settings";
  return "other";
}

/** Carry the sibling diagnostic through older consumers that still store message/error strings. */
export function diagnosticPayload<T>(value: T): T {
  if (!value || typeof value !== "object") return value;
  if (Array.isArray(value)) {
    const result = value.map(diagnosticPayload);
    return (result.every((item, i) => item === value[i]) ? value : result) as T;
  }
  const record = value as Record<string, unknown>;
  const result = { ...record };
  const diagnostic = diagnosticOf(record.diagnostic);
  if (diagnostic && diagnostic.code !== "diag.cancelled" && diagnostic.code !== "diag.recovered") {
    if (typeof record.message === "string") result.message = errorText(diagnostic);
    if (typeof record.error === "string") result.error = errorText(diagnostic);
    if (typeof record.reason === "string") result.reason = errorText(diagnostic);
  }
  for (const key of ["jobs", "progress", "results", "skipped", "items", "packs", "model_apply"]) {
    if (record[key] && typeof record[key] === "object") result[key] = diagnosticPayload(record[key]);
  }
  return (Object.keys(result).every(key => result[key] === record[key]) ? value : result) as T;
}
