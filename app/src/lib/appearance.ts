import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import type { Config } from "./config";
import { NEUTRAL_TONE, sampleWallpaper } from "./wallpaperTone";

/**
 * 外观：配色 + 背景图 + 磨砂 + 不透明度。
 *
 * 全都是往 `<html>` 上写几个 CSS 变量，真正画图的是 index.css 里的
 * `body::before`。所以「生效」这件事本身是零成本的 —— 一次 style 写入，
 * 下一帧就变了。
 *
 * 之所以单独抽出来：这段以前长在 App.tsx 的一个 `useEffect` 里，依赖数组写的是
 * `[page]`。于是它只在**换页**的时候才重新读一次配置 —— 用户在设置页选了背景
 * 图、拖了磨砂和不透明度，界面一动不动，非得切到别的页再切回来才看得见。
 * 三个开关一个都不「实时」，看着就像整块功能是坏的。
 *
 * 现在写配置的地方（useConfig）和启动的地方（App）都调这一个函数，
 * 传的是当时最新的整份配置。
 */
export const APPEARANCE_KEYS = [
  "theme_mode",
  "wallpaper_path",
  "wallpaper_blur",
  "wallpaper_opacity",
  "home_banner_opacity",
] as const;

/** 磨砂滑杆是 0–100，换算成实际的高斯半径。24px 上限是试出来的：
 *  再糊下去就只剩一团颜色，看不出用的是哪张图了。 */
const MAX_BLUR_PX = 24;

export function applyAppearance(cfg: Config): void {
  const el = document.documentElement;

  const mode = String(cfg.theme_mode ?? "system");
  if (mode === "system") el.removeAttribute("data-theme");
  else el.setAttribute("data-theme", mode);

  el.style.setProperty(
    "--wp-blur",
    `${(Number(cfg.wallpaper_blur ?? 40) / 100) * MAX_BLUR_PX}px`,
  );
  el.style.setProperty(
    "--wp-opacity",
    String(Number(cfg.wallpaper_opacity ?? 70) / 100),
  );
  // 首页横幅背景的不透明度。只影响那一格底色（HomePage 里用 color-mix 消费），
  // 文字与 LOGO 不跟着变淡。
  el.style.setProperty(
    "--banner-opacity",
    String(Math.min(100, Math.max(20, Number(cfg.home_banner_opacity ?? 100))) / 100),
  );

  const path = String(cfg.wallpaper_path ?? "");
  if (path) {
    // convertFileSrc 在浏览器预览里没有 Tauri 环境会抛，背景图这一项本来
    // 就只有装好的软件里有意义，抛了就当没设。
    try {
      const src = convertFileSrc(path);
      el.style.setProperty("--wp-image", `url("${src}")`);
      // 设了图就先把开关打上，别等采样。采样要解码一张几兆的图，慢的话是几十
      // 毫秒；这中间卡片如果还是「没有背景图」那一套，用户会看见界面闪一下。
      // `--wp-detail` 有默认值 0.5，先按中庸那档画，采完再落到准确值。
      el.setAttribute("data-wallpaper", "on");
      void applyTone(el, path, src);
    } catch {
      el.style.removeProperty("--wp-image");
      clearTone(el);
    }
  } else {
    el.style.removeProperty("--wp-image");
    clearTone(el);
  }
}

/** 上一次采过的图。同一张图换个磨砂值不必重采。 */
let sampledPath = "";

function clearTone(el: HTMLElement): void {
  sampledPath = "";
  el.removeAttribute("data-wallpaper");
  el.style.removeProperty("--wp-tint");
  el.style.removeProperty("--wp-detail");
  el.style.removeProperty("--wp-luma");
}

async function applyTone(
  el: HTMLElement,
  path: string,
  src: string,
): Promise<void> {
  if (path === sampledPath) return;
  sampledPath = path;
  // 直接采样多半会被 canvas 的同源策略挡下来（asset 地址是另一个源），
  // 挡下来就让 shell 把字节读成 data URL 再采一次。见 wallpaperTone 的说明。
  const tone = await sampleWallpaper(src, () =>
    invoke<string>("wallpaper_data_url", { path }),
  ).catch(() => NEUTRAL_TONE);
  // 采样是异步的，这中间用户可能已经换了图甚至清空了。以最后一次为准。
  if (sampledPath !== path) return;
  el.style.setProperty("--wp-tint", `rgb(${tone.tint})`);
  el.style.setProperty("--wp-detail", String(Math.round(tone.detail * 100) / 100));
  // 亮度交给 CSS 去和当前主题的底色比。放在这里而不是在 JS 里算好，是因为
  // 「当前主题」在跟随系统时会自己变，而这个函数只在配置变化时跑一次。
  el.style.setProperty("--wp-luma", String(Math.round(tone.luma * 100) / 100));
}
