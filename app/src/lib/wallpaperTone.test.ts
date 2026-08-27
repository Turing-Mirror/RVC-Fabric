import { describe, expect, it } from "vitest";
import { NEUTRAL_TONE, sampleWallpaper, toneFromPixels } from "./wallpaperTone";

/** 铺一张 w×h 的图，`at(x, y)` 返回该点的 [r,g,b]。 */
function px(w: number, h: number, at: (x: number, y: number) => number[]) {
  const d = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const [r, g, b] = at(x, y);
      const i = (y * w + x) * 4;
      d[i] = r;
      d[i + 1] = g;
      d[i + 2] = b;
      d[i + 3] = 255;
    }
  }
  return d;
}

describe("toneFromPixels", () => {
  it("纯色图的细节量是 0 —— 卡片可以最薄", () => {
    const t = toneFromPixels(px(8, 8, () => [40, 90, 160]), 8, 8);
    expect(t.detail).toBe(0);
    expect(t.tint).toBe("40 90 160");
  });

  it("棋盘格顶满细节量 —— 卡片要最实", () => {
    const t = toneFromPixels(
      px(8, 8, (x, y) => ((x + y) % 2 ? [255, 255, 255] : [0, 0, 0])),
      8,
      8,
    );
    expect(t.detail).toBe(1);
  });

  /**
   * 这条是这套算法存在的理由：一半天空一半地面的图，整图方差很大，可局部是平的，
   * 字压上去毫无问题。用方差判就会把卡片压得死实，白白盖掉背景图。
   */
  it("上下两块纯色的图，细节量接近 0，不按整图方差判", () => {
    // 尺寸用 64 —— 生产里采样网格就是这么大。整张图只有中间一条缝，
    // 8064 对相邻像素里只有 64 对是跨缝的，摊下来接近 0。
    const t = toneFromPixels(
      px(64, 64, (_x, y) => (y < 32 ? [230, 240, 250] : [30, 40, 50])),
      64,
      64,
    );
    expect(t.detail).toBeLessThan(0.1);
  });

  it("平均色是逐通道平均，不是亮度平均", () => {
    const t = toneFromPixels(
      px(2, 1, (x) => (x === 0 ? [0, 0, 0] : [100, 200, 40])),
      2,
      1,
    );
    expect(t.tint).toBe("50 100 20");
  });

  it("亮度用 Rec.709 权重：纯绿比纯蓝亮得多", () => {
    const g = toneFromPixels(px(4, 4, () => [0, 255, 0]), 4, 4);
    const b = toneFromPixels(px(4, 4, () => [0, 0, 255]), 4, 4);
    expect(g.luma).toBeGreaterThan(b.luma);
    expect(b.luma).toBeLessThan(0.1);
  });

  /** 像素数对不上就退回中庸值，绝不算出一个错的色调来。 */
  it("尺寸和数据对不上时退回中庸值", () => {
    expect(toneFromPixels(new Uint8ClampedArray(4), 8, 8)).toEqual(NEUTRAL_TONE);
    expect(toneFromPixels(new Uint8ClampedArray(0), 0, 0)).toEqual(NEUTRAL_TONE);
  });
});

describe("sampleWallpaper", () => {
  it("没有 DOM 的环境里也只是返回中庸值，不抛", async () => {
    // 这条锁的是对外承诺：取不到色调只该让界面少协调一点，不该把调用它的
    // 那次「应用外观」整个带崩。单测环境里连 Image 都没有，正好是最差的那种。
    await expect(sampleWallpaper("whatever.png")).resolves.toEqual(NEUTRAL_TONE);
    await expect(sampleWallpaper("")).resolves.toEqual(NEUTRAL_TONE);
  });

  it("退路自己抛了也照样收敛到中庸值", async () => {
    await expect(
      sampleWallpaper("x.png", () => Promise.reject(new Error("no shell"))),
    ).resolves.toEqual(NEUTRAL_TONE);
  });
});
