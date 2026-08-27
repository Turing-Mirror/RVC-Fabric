/**
 * 背景图与界面的协调：从图本身推出卡片该有多实、界面该往哪个色偏。
 *
 * 起因是设了背景图之后界面并不「和它是一套的」。浅色下卡片是 60% 的纯白，
 * 压在一张照片上像贴上去的纸片；深色下 `--group` 只有 7.5% 的浅色，卡片干脆
 * 整个溶进照片里，一屏设置看下来分不清哪些项是一组的。而这两件事的答案取决于
 * 那张图长什么样 —— 一张灰调的雾景和一张高饱和的动漫图，需要的卡片实度差得很远。
 *
 * 所以不给用户加第三个滑杆，而是从图里读两个数：
 *
 * - **平均色**：界面底色和卡片底色各往它偏一点点。整屏于是像一个房间里的东西，
 *   而不是照片上摆了几张白纸。偏得很轻（个位数百分比），再多浅色就发浑了。
 * - **细节量**：相邻像素的平均差。它比整图方差更能说明「字压上去还看不看得清」——
 *   一半天空一半地面的图方差很大，但局部是平的，字压上去毫无问题；一张满是
 *   花纹的图方差可能不高，却哪儿都不能放字。细节越多，卡片越实。
 *
 * **不碰用户自己拖过的东西。** 磨砂和不透明度那两根滑杆是他明确表达过的意思，
 * 这里一个都不改 —— 那是「撕裂自动降 f0」犯过的错：拿一个推断去覆盖用户的显式
 * 设置。如果他把磨砂拖到 0、背景图纤毫毕现，这里的做法是把卡片调实到字能看清，
 * 而不是偷偷把磨砂拧回去。
 */

/** 采样边长。再大对这两个统计量没有帮助，只是多解码一些像素。 */
const GRID = 64;

/** 相邻像素平均差到了这个值就算「满细节」，卡片给到最实的一档。 */
const DETAIL_FULL = 0.1;

export type WallpaperTone = {
  /** 平均色，`r g b` 三个 0–255 整数，直接拼进 `rgb()`。 */
  tint: string;
  /** 细节量 0–1。1 = 到处都是花纹，卡片要最实。 */
  detail: number;
  /** 平均亮度 0–1。留给判断用，目前不参与卡片实度。 */
  luma: number;
};

/** 取不到像素时的中庸值：卡片走中间一档，不做色偏。 */
export const NEUTRAL_TONE: WallpaperTone = {
  tint: "128 128 128",
  detail: 0.5,
  luma: 0.5,
};

const lum = (r: number, g: number, b: number) =>
  (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;

/**
 * 从一张 `w × h` 的 RGBA 像素图推出色调。
 *
 * 单独拆出来是为了能测：`sampleWallpaper` 那半截要 canvas，跑不进单元测试。
 */
export function toneFromPixels(
  data: Uint8ClampedArray | number[],
  w: number,
  h: number,
): WallpaperTone {
  if (w <= 0 || h <= 0 || data.length < w * h * 4) return NEUTRAL_TONE;

  let sr = 0;
  let sg = 0;
  let sb = 0;
  const l: number[] = new Array(w * h);
  for (let i = 0; i < w * h; i++) {
    const r = data[i * 4];
    const g = data[i * 4 + 1];
    const b = data[i * 4 + 2];
    sr += r;
    sg += g;
    sb += b;
    l[i] = lum(r, g, b);
  }
  const n = w * h;

  // 相邻像素差。右邻和下邻各算一次，边界不补。
  let delta = 0;
  let pairs = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (x + 1 < w) {
        delta += Math.abs(l[i] - l[i + 1]);
        pairs++;
      }
      if (y + 1 < h) {
        delta += Math.abs(l[i] - l[i + w]);
        pairs++;
      }
    }
  }
  const mean = pairs > 0 ? delta / pairs : 0;

  return {
    tint: `${Math.round(sr / n)} ${Math.round(sg / n)} ${Math.round(sb / n)}`,
    detail: Math.min(1, Math.max(0, mean / DETAIL_FULL)),
    luma: l.reduce((a, b) => a + b, 0) / n,
  };
}

/**
 * 把一张图缩到 `GRID × GRID` 读像素。
 *
 * **画进 canvas 会被同源策略挡下来。** 界面跑在 `http(s)://<scheme>.localhost`，
 * `convertFileSrc` 出来的 asset 地址属于另一个源，画上去那张 canvas 就成了
 * tainted，`getImageData` 直接抛 SecurityError。`crossOrigin="anonymous"` 只在
 * 宿主真的回了 CORS 头时才管用，不能指望。
 *
 * 所以给一条退路：`readDataUrl` 由调用方提供，从后端把字节读成 data URL —— 那
 * 是同源的，canvas 不会脏。只在直接采样失败时才调，多数机器上一次都不会走到。
 *
 * 两条路都不行就返回中庸值，绝不抛：取不到色调只是界面少协调一点，不该让整个
 * 外观设置连带失效。
 */
export async function sampleWallpaper(
  url: string,
  readDataUrl?: () => Promise<string>,
): Promise<WallpaperTone> {
  if (!url) return NEUTRAL_TONE;
  const direct = await toneOf(url);
  if (direct) return direct;
  if (!readDataUrl) return NEUTRAL_TONE;
  try {
    const data = await readDataUrl();
    return (data ? await toneOf(data) : null) ?? NEUTRAL_TONE;
  } catch {
    return NEUTRAL_TONE;
  }
}

/** 采一张图。失败返回 null（而不是中庸值），好让调用方知道该不该走退路。 */
function toneOf(src: string): Promise<WallpaperTone | null> {
  return new Promise((resolve) => {
    // 整段包起来：没有 DOM 的环境（单测、SSR）里 `new Image()` 本身就会抛，
    // 而这个函数对外的承诺是「失败返回 null」，不是「有时候抛」。
    try {
      drawAndRead(src, resolve);
    } catch {
      resolve(null);
    }
  });
}

/** 把 `src` 缩到 GRID×GRID 画进 canvas 读像素。同源策略挡下来就是 null。 */
function drawAndRead(
  src: string,
  resolve: (v: WallpaperTone | null) => void,
): void {
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    try {
      const c = document.createElement("canvas");
      c.width = GRID;
      c.height = GRID;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      if (!ctx) {
        resolve(null);
        return;
      }
      ctx.drawImage(img, 0, 0, GRID, GRID);
      const d = ctx.getImageData(0, 0, GRID, GRID).data;
      resolve(toneFromPixels(d, GRID, GRID));
    } catch {
      resolve(null);
    }
  };
  img.onerror = () => resolve(null);
  img.src = src;
}
