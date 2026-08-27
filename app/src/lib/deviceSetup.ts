/**
 * 输入 / 输出设备的自动检查与配置。
 *
 * 首次装完软件（或换了机器）的人对「sg_hostapi 该选 MME、输入选麦克风、
 * 输出选 CABLE Input」这套连招一无所知，对着三个空下拉框根本开不了变声。
 * 这里把推荐组合算出来，只在**当前值缺失或已失效**时补位 —— 用户自己选过
 * 的有效配置永远不被碰。
 *
 * 设备列表来自 worker 的枚举（engine_status 的 input_devices /
 * output_devices / hostapis），条目是字符串或 `{name, hostapi}` 对象。
 */

export type DeviceInfo = { name: string; hostapi?: string };

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

export function parseDevices(list: unknown): DeviceInfo[] {
  if (!Array.isArray(list)) return [];
  return list
    .map((d) =>
      typeof d === "string"
        ? { name: d.trim(), hostapi: undefined as string | undefined }
        : {
            name: str((d as { name?: unknown })?.name),
            hostapi: str((d as { hostapi?: unknown })?.hostapi) || undefined,
          },
    )
    .filter((d) => d.name);
}

/** 真麦克风的关键词。覆盖常见系统语言；「CABLE」开头的虚拟设备不算。 */
const MIC_KEYWORDS = [
  "麦克风",
  "microphone",
  "mic ",
  "mic(",
  "mikrofon",
  "マイク",
  "마이크",
  "микрофон",
];

function looksLikeMic(name: string): boolean {
  const n = name.toLowerCase();
  if (n.includes("cable")) return false;
  return MIC_KEYWORDS.some((k) => n.includes(k));
}

function looksLikeCableInput(name: string): boolean {
  const n = name.toLowerCase();
  // CABLE Input 是虚拟声卡的放音端 —— 变声输出到它，游戏/Discord 再从
  // CABLE Output 当麦克风收走。名字里的 hostapi 后缀不影响判断。
  return n.includes("cable input") || n.includes("vb-audio virtual cable");
}

export type DeviceAutoPick = {
  sg_hostapi?: string;
  sg_input_device?: string;
  sg_output_device?: string;
};

/**
 * 按当前配置与设备列表算出需要补位的字段。
 *
 * 返回 null 表示一切有效、什么都不用动。hostapi 只在失效时改成 MME（用户
 * 例子里的默认栈）；输入优先真麦克风、输出优先 CABLE Input，都先在选定的
 * hostapi 里找，找不到再放宽到全部列表。
 */
export function pickAutoDevices(
  cfg: Record<string, unknown>,
  status: Record<string, unknown> | undefined | null,
): DeviceAutoPick | null {
  const inputs = parseDevices(status?.input_devices);
  const outputs = parseDevices(status?.output_devices);
  const hostapis = parseDevices(status?.hostapis).map((d) => d.name);
  if (!inputs.length && !outputs.length) return null;

  const curApi = str(cfg.sg_hostapi);
  const curIn = str(cfg.sg_input_device);
  const curOut = str(cfg.sg_output_device);

  // 空串也算「待补」—— 首次安装的人三个下拉框都是空的，正是这套逻辑要
  // 服务的人。只有**非空且在列表里**的值才被当成用户的有效选择。
  const apiValid =
    !!curApi &&
    (!hostapis.length ||
      hostapis.some((h) => h.toLowerCase() === curApi.toLowerCase()));
  const inValid = !!curIn && inputs.some((d) => d.name === curIn);
  const outValid = !!curOut && outputs.some((d) => d.name === curOut);
  if (apiValid && inValid && outValid) return null;

  // hostapi 失效才换；首选 MME（延迟虽高但兼容性最好，VB-CABLE 的名字也带
  // (MME) 后缀成对出现），没有就保持原样不瞎猜。
  let api = curApi;
  let apiChanged = false;
  if (!apiValid && hostapis.length) {
    const mme = hostapis.find((h) => h.toLowerCase().includes("mme"));
    if (mme && mme !== curApi) {
      api = mme;
      apiChanged = true;
    }
  }
  const apiSuffix = api ? `(${api})` : "";
  const inSameApi = (d: DeviceInfo) =>
    !!api && (d.name.includes(apiSuffix) || d.hostapi?.toLowerCase() === api.toLowerCase());

  let input: string | undefined;
  if (!inValid && inputs.length) {
    const mics = inputs.filter((d) => looksLikeMic(d.name));
    input =
      mics.find(inSameApi)?.name ?? mics[0]?.name ?? inputs[0]?.name;
    if (input === curIn) input = undefined;
  }

  let output: string | undefined;
  if (!outValid && outputs.length) {
    const cable = outputs.filter((d) => looksLikeCableInput(d.name));
    output =
      cable.find(inSameApi)?.name ?? cable[0]?.name ?? outputs[0]?.name;
    if (output === curOut) output = undefined;
  }

  const out: DeviceAutoPick = {};
  // 引擎和设置页读的都是 sg_*。写成 hostapi / input_device 只会进磁盘
  // 里的旧别名：输入输出靠 apply_device_alias 碰巧能回填，sg_hostapi
  // 没有别名，MME 永远配不上。
  if (apiChanged) out.sg_hostapi = api;
  if (input) out.sg_input_device = input;
  if (output) out.sg_output_device = output;
  return Object.keys(out).length ? out : null;
}
