import { Select } from "./controls";
import { t } from "../i18n/t";

/** 「自动」在配置里存 -1，不是空字符串 —— 0 是一块真实存在的显卡。 */
export const MAIN_GPU_AUTO = -1;

/** Call at use time — module-level t() freezes default locale. */
export function mainGpuTip(): string {
  return (
    t("s.c4c4673f74") +
    t("s.c21f67d167") +
    t("s.750e6a370f") +
    t("s.7cb4f28eb2") +
    t("s.12579f2917") +
    t("s.310f4d242c")
  );
}

/**
 * 主显卡选择。
 *
 * 只列 N 卡：这个序号最后是给 `CUDA_VISIBLE_DEVICES` 用的，而 CUDA 根本看不见
 * 核显和 A 卡，把它们混进列表只会让序号错位。
 */
export function MainGpuPicker({
  gpus,
  value,
  onChange,
  disabled = false,
  full = false,
}: {
  /** 系统枚举到的 N 卡，顺序即序号。 */
  gpus: string[];
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
  full?: boolean;
}) {
  const options = [
    { id: String(MAIN_GPU_AUTO), label: t("s.74982a8e00") },
    ...gpus.map((name, i) => ({ id: String(i), label: `${i} · ${name}` })),
  ];
  return (
    <Select
      full={full}
      disabled={disabled}
      value={String(Number.isFinite(value) ? value : MAIN_GPU_AUTO)}
      options={options}
      onChange={(v) => onChange(Number(v))}
    />
  );
}
