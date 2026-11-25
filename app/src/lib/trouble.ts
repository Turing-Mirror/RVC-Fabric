import { diagnosticOf } from "./diagnostics";
export type Trouble = "voice" | "runtime" | "devices" | "vram" | "unknown";

/** Routing from the single Rust diagnosis; never re-interpret exception keywords. */
export function classifyTrouble(value: unknown): Trouble {
  const diagnostic = diagnosticOf(value);
  if (!diagnostic) return "unknown";
  if (diagnostic.actions.some(action => action.id === "open_device_settings")) return "devices";
  if (diagnostic.actions.some(action => action.id === "start_provision")) return "runtime";
  if (diagnostic.code === "diag.oom_gpu") return "vram";
  if (diagnostic.source_code === "vc.need_model") return "voice";
  return "unknown";
}
