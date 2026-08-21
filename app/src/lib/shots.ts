/**
 * 把用户粘贴或选中的图片压到能进诊断包的大小。
 *
 * 截图是最省事的一种信息：「界面出错」这四个字加一张图，就知道是哪扇窗、哪个
 * 按钮、报的哪一句 —— 这些日志里全都没有。代价是体积，一张 4K 截图 PNG 能到
 * 十几兆，而这个包要发到群里。
 *
 * 所以先缩到长边 1920（截图上的文字在这个尺寸下仍然读得清），再优先存 PNG；
 * PNG 太大才换 JPEG。反过来一律 JPEG 会把界面上的细字压糊，那就白收了。
 */

/** 长边上限。再大对读图没有帮助，只是把包撑大。 */
const MAX_EDGE = 1920;
/** 超过这个体积就改用 JPEG。 */
const PNG_BUDGET = 2 * 1024 * 1024;
/** 单张硬上限，和 Rust 那边一致。 */
export const MAX_SHOT_BYTES = 8 * 1024 * 1024;
/** 最多几张，和 Rust 那边一致。 */
export const MAX_SHOTS = 6;

export type Shot = {
  /** 列表 key，仅前端用。 */
  id: string;
  /** 缩略图与预览用的 data URL。 */
  url: string;
  /** 传给 Rust：png / jpg。 */
  ext: "png" | "jpg";
  /** 传给 Rust：不带 `data:` 前缀的 base64。 */
  data: string;
  /** 解码后的字节数，界面上显示体积用。 */
  bytes: number;
  name: string;
};

function loadImage(file: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("not an image"));
    };
    img.src = url;
  });
}

/** data URL 里 base64 那一段的解码后字节数（不必真的解一遍）。 */
export function base64Bytes(b64: string): number {
  const pad = b64.endsWith("==") ? 2 : b64.endsWith("=") ? 1 : 0;
  return Math.max(0, Math.floor((b64.length * 3) / 4) - pad);
}

function splitDataUrl(url: string): { ext: "png" | "jpg"; data: string } {
  const comma = url.indexOf(",");
  const head = url.slice(0, comma);
  return {
    ext: head.includes("image/jpeg") ? "jpg" : "png",
    data: url.slice(comma + 1),
  };
}

/**
 * 一个文件 → 一张可以进包的图。读不出来就返回 null（调用方负责说一句）。
 */
export async function prepareShot(file: File | Blob, name: string): Promise<Shot | null> {
  let img: HTMLImageElement;
  try {
    img = await loadImage(file);
  } catch {
    return null;
  }
  const scale = Math.min(1, MAX_EDGE / Math.max(img.width, img.height));
  const w = Math.max(1, Math.round(img.width * scale));
  const h = Math.max(1, Math.round(img.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  // 截图多半有大片纯色背景，JPEG 转档前先铺白，免得透明区域变成黑块。
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);
  ctx.drawImage(img, 0, 0, w, h);

  let url = canvas.toDataURL("image/png");
  let { ext, data } = splitDataUrl(url);
  if (base64Bytes(data) > PNG_BUDGET) {
    url = canvas.toDataURL("image/jpeg", 0.92);
    ({ ext, data } = splitDataUrl(url));
  }
  const bytes = base64Bytes(data);
  if (bytes > MAX_SHOT_BYTES) return null;
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    url,
    ext,
    data,
    bytes,
    name,
  };
}

/** 从一次粘贴 / 拖放里挑出图片文件。 */
export function imageFilesFrom(dt: DataTransfer | null): File[] {
  if (!dt) return [];
  const out: File[] = [];
  if (dt.files && dt.files.length) {
    for (const f of Array.from(dt.files)) {
      if (f.type.startsWith("image/")) out.push(f);
    }
  }
  if (out.length === 0 && dt.items) {
    for (const it of Array.from(dt.items)) {
      if (it.kind === "file" && it.type.startsWith("image/")) {
        const f = it.getAsFile();
        if (f) out.push(f);
      }
    }
  }
  return out;
}
