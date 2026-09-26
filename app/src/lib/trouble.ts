/**
 * 变声启动失败时，把报错归到用户能动手处理的几类，每类配一个下一步。
 *
 * dock 上那一行报错是写给会看日志的人的；新手看到「PortAudio -9996」不知道该做什么，
 * 只能去群里问。这里只认出最常见的几类，认不出的一律交给链路自检，不硬猜。
 */
export type Trouble = "voice" | "runtime" | "devices" | "vram" | "unknown";

const RULES: [Trouble, RegExp][] = [
  ["voice", /need_model|no model|未选择音色|未選擇音色|select a voice|模型文件不存在|\.pth.*not found/i],
  ["runtime", /runtime|python\.exe|运行时|執行時|not_ready|missing_python/i],
  ["vram", /out of memory|cuda.*memory|显存不足|顯存不足|vram/i],
  ["devices", /portaudio|invalid device|device unavailable|-999\d|input device|output device|设备|裝置|設備|sample rate|采样率|wasapi|mme/i],
];

export function classifyTrouble(error: string): Trouble {
  if (!error) return "unknown";
  for (const [kind, re] of RULES) if (re.test(error)) return kind;
  return "unknown";
}
