/**
 * 计算后端的展示与选择（C-05/E-03）：MorePage 的实际后端展示和
 * SettingsPage 的选择器共用同一份标签与说明，不各写一份。
 */

const LABELS: Record<string, string> = {
  cuda: "CUDA",
  directml: "DirectML",
  mps: "Metal",
  xpu: "XPU",
  cpu: "CPU",
};

export function backendLabel(id: string): string {
  return LABELS[id] ?? id;
}

/** 可选的后端列表。nvidia50 包同样走 cuda 通道，不单独列。 */
export const ACCEL_OPTIONS = ["auto", "cuda", "dml", "cpu"] as const;
export type AccelOption = (typeof ACCEL_OPTIONS)[number];

export function normalizeAccel(raw: unknown): AccelOption {
  const v = String(raw || "").toLowerCase();
  return (ACCEL_OPTIONS as readonly string[]).includes(v)
    ? (v as AccelOption)
    : "auto";
}
