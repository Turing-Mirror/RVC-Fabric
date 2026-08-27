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
  if (n.includes("cable") || n.includes("voicemeeter") || n.includes("vb-audio")) {
    return false;
  }
  return MIC_KEYWORDS.some((k) => n.includes(k));
}

function looksLikeCableInput(name: string): boolean {
  const n = name.toLowerCase();
  // CABLE Input 是虚拟声卡的放音端 —— 变声输出到它，游戏/Discord 再从
  // CABLE Output 当麦克风收走。名字里的 hostapi 后缀不影响判断。
  return n.includes("cable input") || n.includes("vb-audio virtual cable");
}

/** 虚拟线的注入端（放音）：软件输出该选这个。 */
export function looksLikeVirtualInject(name: string): boolean {
  const n = name.toLowerCase();
  if (looksLikeVirtualCapture(n)) return false;
  if (n.includes("cable input")) return true;
  if (n.includes("hi-fi cable input") || n.includes("hifi cable input")) return true;
  if (n.includes("voicemeeter") && n.includes("input")) return true;
  if (n.includes("vaio") && n.includes("input")) return true;
  if (n.includes("vb-audio virtual cable") && !n.includes("output")) return true;
  return false;
}

/** 虚拟线的录音端：游戏/Discord 的麦克风。不能当本软件的输入或输出。 */
export function looksLikeVirtualCapture(name: string): boolean {
  const n = name.toLowerCase();
  if (n.includes("cable output")) return true;
  if (n.includes("voicemeeter") && n.includes("output")) return true;
  if (n.includes("vaio") && n.includes("output")) return true;
  return false;
}

function looksLikePhysicalPlay(name: string): boolean {
  const n = name.toLowerCase();
  if (looksLikeVirtualInject(n) || looksLikeVirtualCapture(n)) return false;
  return [
    "耳机",
    "headphone",
    "headset",
    "扬声器",
    "speaker",
    "realtek",
    "hdmi",
  ].some((k) => n.includes(k));
}

function looksLikeVoiceMeeterInject(name: string): boolean {
  const n = name.toLowerCase();
  return n.includes("voicemeeter") && n.includes("input") && !n.includes("output");
}

export type DeviceAutoPick = {
  sg_hostapi?: string;
  sg_input_device?: string;
  sg_output_device?: string;
  monitor_device?: string;
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
    const injects = outputs.filter((d) => looksLikeVirtualInject(d.name));
    output =
      injects.find((d) => looksLikeCableInput(d.name) && inSameApi(d))?.name ??
      injects.find(inSameApi)?.name ??
      injects.find((d) => looksLikeCableInput(d.name))?.name ??
      injects[0]?.name ??
      undefined;
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

export type DeviceAdvice = {
  patch: DeviceAutoPick | null;
  /** 给按钮下面那行看的文案 key，按顺序拼成一句。 */
  reasons: string[];
};

function preferSameApi(
  list: DeviceInfo[],
  api: string,
  pred: (n: string) => boolean,
): string | undefined {
  const apiSuffix = api ? `(${api})` : "";
  const hit = list.filter((d) => pred(d.name));
  if (!hit.length) return undefined;
  return (
    hit.find(
      (d) =>
        !!api &&
        (d.name.includes(apiSuffix) || d.hostapi?.toLowerCase() === api.toLowerCase()),
    )?.name ?? hit[0]?.name
  );
}

/**
 * 设置页「自动配置」用的防呆检查。
 *
 * 不只看「设备名还在列表里」—— 把输出设成扬声器、输入设成 CABLE Output
 * 都是合法设备名，但变声送不到游戏/Discord。这里只拦几类常见接错：
 *
 * - 输入选了虚拟线的录音端（会录到变声自己，或没原声）
 * - 输出没走虚拟线注入端（有 VB-Cable / VoiceMeeter 时）
 * - 输出误选了录音端
 * - 监听选了虚拟线（听不到，还可能回环）
 *
 * VoiceMeeter 的 Input / Aux Input / VAIO3 Input 都算注入端，不强迫改成 Cable。
 * 没有虚拟声卡时不瞎改输出，只提示去装。
 */
export function assessDevices(
  cfg: Record<string, unknown>,
  status: Record<string, unknown> | undefined | null,
): DeviceAdvice {
  const inputs = parseDevices(status?.input_devices);
  const outputs = parseDevices(status?.output_devices);
  const hostapis = parseDevices(status?.hostapis).map((d) => d.name);
  if (!inputs.length && !outputs.length) {
    return { patch: null, reasons: ["s.devAutoNoList"] };
  }

  const curApi = str(cfg.sg_hostapi);
  const curIn = str(cfg.sg_input_device);
  const curOut = str(cfg.sg_output_device);
  const curMon = str(cfg.monitor_device);
  const monitorOn = cfg.monitor_self === true || cfg.monitor_self === "true";

  let api = curApi;
  const patch: DeviceAutoPick = {};
  const parts: string[] = [];

  const apiValid =
    !!curApi &&
    (!hostapis.length ||
      hostapis.some((h) => h.toLowerCase() === curApi.toLowerCase()));
  if (!apiValid && hostapis.length) {
    const mme = hostapis.find((h) => h.toLowerCase().includes("mme"));
    if (mme) {
      api = mme;
      patch.sg_hostapi = mme;
      parts.push("s.devAutoApi");
    }
  }

  const cableOut = preferSameApi(outputs, api, looksLikeCableInput);
  const vmOut = preferSameApi(outputs, api, looksLikeVoiceMeeterInject);
  const anyInject = preferSameApi(outputs, api, looksLikeVirtualInject);
  const inject = cableOut || vmOut || anyInject;
  const realMic = preferSameApi(inputs, api, looksLikeMic);
  const phones =
    preferSameApi(outputs, api, (n) => {
      const x = n.toLowerCase();
      return (
        !looksLikeVirtualInject(n) &&
        !looksLikeVirtualCapture(n) &&
        ["耳机", "headphone", "headset"].some((k) => x.includes(k))
      );
    }) ?? preferSameApi(outputs, api, looksLikePhysicalPlay);

  const inIsCapture = !!curIn && looksLikeVirtualCapture(curIn);
  const inMissing = !curIn || !inputs.some((d) => d.name === curIn);
  if ((inMissing || inIsCapture) && realMic && realMic !== curIn) {
    patch.sg_input_device = realMic;
    parts.push(inIsCapture ? "s.devAutoInWasCable" : "s.devAutoIn");
  }

  const outMissing = !curOut || !outputs.some((d) => d.name === curOut);
  const outIsCapture = !!curOut && looksLikeVirtualCapture(curOut);
  const outIsInject = !!curOut && looksLikeVirtualInject(curOut);
  if (inject) {
    if ((outMissing || outIsCapture || !outIsInject) && inject !== curOut) {
      patch.sg_output_device = inject;
      parts.push(outIsCapture ? "s.devAutoOutWasCapture" : "s.devAutoOutWasSpeaker");
    }
  } else if (outMissing && outputs[0] && outputs[0].name !== curOut) {
    // 没有虚拟线：不把输出改去扬声器装样子，只告诉人去装。
    parts.push("s.devAutoNoVirtual");
  }

  if (monitorOn && curMon && (looksLikeVirtualInject(curMon) || looksLikeVirtualCapture(curMon))) {
    if (phones && phones !== curMon) {
      patch.monitor_device = phones;
      parts.push("s.devAutoMonWasCable");
    }
  }

  const keys = Object.keys(patch);
  if (!keys.length) {
    if (!inject) {
      return { patch: null, reasons: ["s.devAutoNoVirtual"] };
    }
    const kind = looksLikeVoiceMeeterInject(curOut) ? "s.devAutoOkVm" : "s.devAutoOkCable";
    return { patch: null, reasons: [kind] };
  }
  return { patch, reasons: parts };
}
