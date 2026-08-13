import { useCallback, useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { getConfig, notifyConfigPatch, setConfig, type Config } from "../lib/config";
import { applyAppearance } from "../lib/appearance";

/**
 * Settings state. Writes are optimistic so sliders feel live, then reconciled
 * with whatever the backend actually persisted.
 *
 * Cold keys come back in `needs_restart`; the page shows a standing notice
 * instead of silently doing nothing, which is what the old placeholder UI did.
 */
export function useConfig() {
  const [cfg, setCfg] = useState<Config>({});
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [restartKeys, setRestartKeys] = useState<string[]>([]);
  const pending = useRef<Config>({});
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;
    getConfig()
      .then((c) => {
        if (alive) {
          setCfg(c);
          setLoaded(true);
        }
      })
      .catch((e) => alive && setError(String(e)));
    let unCfg: (() => void) | undefined;
    let unVoice: (() => void) | undefined;
    void listen<{ config?: Config }>("config-changed", (ev) => {
      if (!alive) return;
      const next = ev.payload?.config;
      if (next && typeof next === "object") setCfg(next);
    }).then((fn) => {
      if (!alive) fn();
      else unCfg = fn;
    });
    // 切音色会把该音色档案里的音高/共鸣写进配置，设置页要跟着换。
    void listen("voices-changed", () => {
      if (!alive) return;
      void getConfig()
        .then((c) => {
          if (alive) setCfg(c);
        })
        .catch(() => undefined);
    }).then((fn) => {
      if (!alive) fn();
      else unVoice = fn;
    });
    return () => {
      alive = false;
      unCfg?.();
      unVoice?.();
    };
  }, []);

  /**
   * 外观改一下就套一下，不等写盘、不等换页。
   *
   * `set` 是乐观更新，cfg 里立刻就是新值，所以磨砂和不透明度是**拖着就在变**
   * 的 —— 这两项本来就该当场看效果，否则用户根本没法调。写盘那边照旧 220ms
   * 合并一次，跟这里没关系。
   *
   * 依赖只列这四个键：别的设置（音频参数之类）每次改都重建 cfg 对象，写整个
   * cfg 会让这段跟着白跑。
   */
  useEffect(() => {
    if (!loaded) return;
    applyAppearance(cfg);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只认外观那几个键
  }, [
    loaded,
    cfg.theme_mode,
    cfg.wallpaper_path,
    cfg.wallpaper_blur,
    cfg.wallpaper_opacity,
  ]);

  const flush = useCallback(async () => {
    const patch = pending.current;
    pending.current = {};
    if (!Object.keys(patch).length) return;
    try {
      const out = await setConfig(patch);
      setCfg(out.config);
      if (out.needs_restart.length) {
        setRestartKeys((prev) =>
          Array.from(new Set([...prev, ...out.needs_restart])),
        );
      }
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, []);

  /**
   * Coalesce rapid changes (slider drags) into one write.
   *
   * `immediate` 时**同步**开始写盘并把那个 promise 交出来。以前它也是走
   * `setTimeout(…, 0)` 的，于是调用方紧接着做的事（比如快捷键那边 `set` 完
   * 立刻 `hotkeys_apply`）永远排在写盘前面 —— Rust 是从配置文件里读组合键的，
   * 读到的还是上一个值，注册的就永远慢一步：界面显示 F2，实际生效的还是 F1。
   * 需要「存完再做下一步」的地方 await 这个返回值。
   */
  const set = useCallback(
    (key: string, value: unknown, immediate = false): Promise<void> => {
      setCfg((c) => ({ ...c, [key]: value }));
      pending.current[key] = value;
      notifyConfigPatch({ [key]: value });
      if (timer.current) window.clearTimeout(timer.current);
      if (immediate) {
        timer.current = null;
        return flush();
      }
      timer.current = window.setTimeout(() => void flush(), 220);
      return Promise.resolve();
    },
    [flush],
  );

  const clearRestartNotice = useCallback(() => setRestartKeys([]), []);

  const num = useCallback(
    (k: string, fallback = 0) => {
      const v = cfg[k];
      return typeof v === "number" ? v : Number(v ?? fallback) || fallback;
    },
    [cfg],
  );
  const str = useCallback(
    (k: string, fallback = "") => {
      const v = cfg[k];
      return typeof v === "string" ? v : fallback;
    },
    [cfg],
  );
  const bool = useCallback((k: string) => cfg[k] === true, [cfg]);

  return { cfg, loaded, error, set, num, str, bool, restartKeys, clearRestartNotice };
}
