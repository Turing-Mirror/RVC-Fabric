import { useCallback, useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { dropListen } from "../lib/tauriListen";
import { getConfig, notifyConfigPatch, setConfig, type Config } from "../lib/config";
import { applyAppearance } from "../lib/appearance";

/**
 * Settings state. Writes are optimistic so sliders feel live, then reconciled
 * with whatever the backend actually persisted.
 *
 * Cold keys come back in `needs_restart`; the page shows a standing notice
 * instead of silently doing nothing, which is what the old placeholder UI did.
 */

/** 从 src 里把 keys 名单中的键原样摘出来（名单之外的键不碰）。 */
function pickKeys(src: Config, keys: Set<string>): Config {
  const out: Config = {};
  keys.forEach((k) => {
    if (k in src) out[k] = src[k];
  });
  return out;
}

export function useConfig() {
  const [cfg, setCfg] = useState<Config>({});
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [restartKeys, setRestartKeys] = useState<string[]>([]);
  const pending = useRef<Config>({});
  // 已发出还没回来的那一份：任何晚到的快照/响应都必须让它压在表面，
  // 否则加载或别的窗口的 config-changed 会把在途写盘拽回旧值。
  const inflight = useRef<Config>({});
  const timer = useRef<number | null>(null);
  // 写盘串行链：同时只有一条 config_set 在途。旧响应晚到也盖不住新写的结论。
  const tail = useRef<Promise<void>>(Promise.resolve());
  // 链上还没落定（在途或排队中）的 flush 数。>0 期间新写只能挂到链尾，
  // 否则「第一条 finally 先跑、排队任务后跑」的空窗会让新写并发发出。
  const queued = useRef(0);
  // 初始 getConfig 还没回来就被本地改过的键。旧快照比那次写盘老，
  // 回来时这些键以界面现值（已写上的值）为准，不按快照回退。
  const dirty = useRef<Set<string>>(new Set());

  const unconfirmed = useCallback(
    () => ({ ...inflight.current, ...pending.current }),
    [],
  );

  useEffect(() => {
    let alive = true;
    getConfig()
      .then((c) => {
        if (!alive) return;
        // 加载期间（含写盘已经完成的）本地改动盖在旧快照上面 —— inflight/
        // pending 只覆盖「还没落定的」，已写上的键要靠 dirty 名单从现值取。
        setCfg((prev) => ({
          ...c,
          ...pickKeys(prev, dirty.current),
          ...unconfirmed(),
        }));
        setLoaded(true);
      })
      .catch((e) => alive && setError(String(e)));
    let unCfg: (() => void) | undefined;
    void listen<{ config?: Config }>("config-changed", (ev) => {
      if (!alive) return;
      const next = ev.payload?.config;
      if (next && typeof next === "object") {
        setCfg({ ...next, ...unconfirmed() });
      }
    }).then((fn) => {
      if (!alive) dropListen(fn);
      else unCfg = fn;
    });
    return () => {
      alive = false;
      dropListen(unCfg);
    };
  }, [unconfirmed]);

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
    cfg.home_banner_opacity,
  ]);

  const flush = useCallback((): Promise<void> => {
    const run = async () => {
      const patch = pending.current;
      pending.current = {};
      if (!Object.keys(patch).length) return;
      inflight.current = { ...inflight.current, ...patch };
      try {
        const out = await setConfig(patch);
        for (const k of Object.keys(patch)) delete inflight.current[k];
        // 写回结果之上仍盖着未确认的意图 —— 服务端快照不拽回待写字段。
        setCfg({ ...out.config, ...unconfirmed() });
        if (out.needs_restart.length) {
          setRestartKeys((prev) =>
            Array.from(new Set([...prev, ...out.needs_restart])),
          );
        }
        setError("");
      } catch (e) {
        for (const k of Object.keys(patch)) delete inflight.current[k];
        // 没写上的字段放回待写：失败不清空用户意图，下一次 flush 还会带上；
        // 期间用户又改的同名字段以新值为准。
        pending.current = { ...patch, ...pending.current };
        setError(String(e));
        throw e;
      }
    };
    // queued 计数即「链是否排空」：链上还有任何在途/排队任务时，新写
    // 一律挂尾，直到最后一条落定才回到同步派发。
    queued.current += 1;
    const task = (
      queued.current === 1
        ? // 空闲：同步开写。immediate 的调用方紧接着的 invoke（比如改完热键
          // 立刻 hotkeys_apply）仍然排在这条 config_set 后面。
          run()
        : // 有在途写盘：排进串行链，等前一条落定再发 —— 乱序的响应永远
          // 不可能发生，旧成功清不掉新失败。tail 永不拒绝。
          tail.current.then(run)
    ).finally(() => {
      queued.current -= 1;
    });
    tail.current = task.then(
      () => undefined,
      () => undefined,
    );
    return task;
  }, [unconfirmed]);

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
      dirty.current.add(key);
      notifyConfigPatch({ [key]: value });
      if (timer.current) window.clearTimeout(timer.current);
      if (immediate) {
        timer.current = null;
        return flush();
      }
      // 防抖路径没有调用方能接 Promise：失败结论走 error 状态，吞掉即可。
      timer.current = window.setTimeout(() => void flush().catch(() => {}), 220);
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
