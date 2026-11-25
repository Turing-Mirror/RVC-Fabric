import { invoke } from "./invoke";
import { openDownloadModels } from "./downloadModels";
import { openHelpSection } from "./helpNav";
import type { ActionHandlers } from "./diagnostics";

export type TrainingCopy = { job_id: string; stage: string; current: number; suggested: number };
export function diagnosticActions(editTrainingCopy?: (request: TrainingCopy) => Promise<void>): ActionHandlers {
  const handlers: ActionHandlers = {
    open_downloads: async params => openDownloadModels({ filter: params.filter === "train" ? "train" : "all" }),
    open_help: async params => openHelpSection(params.section === "train" ? "train" : ""),
    start_provision: async () => invoke("diagnostic_navigate", { destination: "runtime" }),
    open_device_settings: async () => invoke("diagnostic_navigate", { destination: "devices" }),
    open_community: async () => invoke("diagnostic_navigate", { destination: "community" }),
    open_performance_options: async () => invoke("diagnostic_system_settings", { kind: "performance" }),
    open_storage_cleanup: async () => invoke("diagnostic_system_settings", { kind: "storage" }),
    open_log: async () => invoke("reveal_user_dir", { name: "logs" }),
  };
  if (editTrainingCopy) handlers.edit_training_copy = async params => {
    await editTrainingCopy(params as TrainingCopy);
  };
  return handlers;
}
