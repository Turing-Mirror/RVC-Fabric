import { Select } from "./controls";

/** 「自动」在配置里存 -1，不是空字符串 —— 0 是一块真实存在的显卡。 */
export const MAIN_GPU_AUTO = -1;

export const MAIN_GPU_TIP =
  "多块 N 卡时指定用哪一块计算。\n" +
  "引擎默认永远用排在第一的那块：一块 5060 一块 5090，很可能整场都在用 5060。\n" +
  "改完要重新「开启变声」才生效。\n" +
  "选完如果引擎用的还不是你要的那块，换一个序号再试 —— " +
  "显卡在系统里的排序和显卡驱动的排序不保证一致。\n" +
  "A 卡 / 核显（DirectML）路径上这一项不生效。";

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
    { id: String(MAIN_GPU_AUTO), label: "自动（不指定）" },
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
