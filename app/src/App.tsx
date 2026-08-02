import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Dock, type OutputMode } from "./components/Dock";
import { Nudge } from "./components/Nudge";
import { Btn } from "./components/ui";
import { FOLLOW_LINKS } from "./lib/links";
import { openExternal } from "./lib/plaza";
import { PageHost } from "./components/PageHost";
import { ProvisionGate } from "./components/ProvisionGate";
import { TitleBar } from "./components/TitleBar";
import { useEngine } from "./hooks/useEngine";
import { usePlaza } from "./hooks/usePlaza";
import { ensureEngine, forceKillEngine, getProvisionStatus, setHot } from "./lib/engine";
import type { PageId } from "./lib/nav";
import { currentVoice } from "./lib/voices";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { HelpPage } from "./pages/HelpPage";
import { HomePage } from "./pages/HomePage";
import { ModelsPage } from "./pages/ModelsPage";
import { MorePage } from "./pages/MorePage";
import { PlazaPage } from "./pages/PlazaPage";
import { SettingsPage } from "./pages/SettingsPage";

/**
 * 变声多少次之后问一句「要不要关注」。
 *
 * 十次的意思是：这人已经把软件用起来了，不是打开看两眼就走的。太早问等于
 * 拦路要东西，太晚问他早就忘了这软件是谁做的。
 */
const FOLLOW_AFTER_RUNS = 10;

/** `update_check` 的返回。字段名和 `update::decide` 里那个 json! 一一对应。 */
type UpdateInfo = {
  local: string;
  remote: string;
  available: boolean;
  blocked_by_min_version: boolean;
  min_app_version: string;
  package_type: string;
  /** `external` = 换 exe，走签名更新器；否则是界面补丁。 */
  action: string;
  url: string;
  sha256: string;
  notes: string;
};

/** `14:07`。状态行里带个时间，才看得出这句话是刚查的还是上次留下的。 */
function clockNow(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes(),
  ).padStart(2, "0")}`;
}

export default function App() {
  const [page, setPage] = useState<PageId>("home");
  const [compactNav, setCompactNav] = useState(false);
  // Self-update: check reports the catalog's latest; applying swaps the
  // external frontend/ dir and takes effect on restart.
  const [updateLine, setUpdateLine] = useState("");
  // 检查更新唯一的反馈原来只有一行灰色小字，用户点完看不出点没点上，
  // 会以为按钮坏了。按钮自己也要进入「检查中…」并禁用。
  const [updateBusy, setUpdateBusy] = useState(false);

  // Wallpaper + theme come from app_config and are applied to the shell root.
  // Blur/opacity are plain CSS here — the Tk shell needed a chroma-key hack
  // (#010203) to fake transparency; a webview does not.
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const cfg = await invoke<Record<string, unknown>>("config_get");
        if (!alive) return;
        const mode = String(cfg.theme_mode ?? "system");
        const el = document.documentElement;
        if (mode === "system") el.removeAttribute("data-theme");
        else el.setAttribute("data-theme", mode);
        const path = String(cfg.wallpaper_path ?? "");
        el.style.setProperty("--wp-blur", `${Number(cfg.wallpaper_blur ?? 40) / 100 * 24}px`);
        el.style.setProperty("--wp-opacity", String(Number(cfg.wallpaper_opacity ?? 70) / 100));
        if (path) {
          el.style.setProperty("--wp-image", `url("${convertFileSrc(path)}")`);
        } else {
          el.style.removeProperty("--wp-image");
        }
      } catch {
        /* config unavailable outside Tauri */
      }
    })();
    return () => {
      alive = false;
    };
  }, [page]);
  // 启动时自动查到的新版本。非空 = 弹一条「要不要现在装」。
  const [updateOffer, setUpdateOffer] = useState<UpdateInfo | null>(null);

  /** 只查，不装。返回后端那份原样的结果，顺手把状态行写好。 */
  const probeUpdate = async (): Promise<UpdateInfo | null> => {
    const r = (await invoke<Record<string, unknown>>(
      "update_check",
    )) as UpdateInfo;
    if (r.blocked_by_min_version) {
      setUpdateLine(
        `当前版本 ${String(r.local)}，需要先更新到 ${String(
          r.min_app_version,
        )} 才能继续`,
      );
      return null;
    }
    if (!r.available) {
      // 「已是最新」必须带上版本号和时间。只说一句「已是最新」，用户分不清
      // 是真查过了还是根本没查动。
      setUpdateLine(`已是最新版本 ${String(r.local)}（${clockNow()} 查过）`);
      return null;
    }
    setUpdateLine(
      `发现新版本 ${String(r.remote)}，当前 ${String(r.local)}`,
    );
    return r;
  };

  /** 真正下载并安装。整包走签名更新器，界面补丁走 update_apply。 */
  const installUpdate = async (r: UpdateInfo) => {
    if (r.action === "external") {
      // Rust side changed → replace the exe through the signed updater.
      setUpdateLine(`正在下载程序更新 ${String(r.remote)}…`);
      const b = await invoke<Record<string, unknown>>("update_app");
      setUpdateLine(
        b.installed
          ? `已更新到 ${String(b.version ?? r.remote)}，重启程序后生效`
          : "暂时取不到程序更新包，可先到发布页手动下载",
      );
      return;
    }
    setUpdateLine(`正在下载界面更新 ${String(r.remote)}…`);
    await invoke("update_apply", {
      url: String(r.url),
      sha256: String(r.sha256 || ""),
    });
    setUpdateLine(`已更新到 ${String(r.remote)}，重启程序后生效`);
  };

  /** 设置页那个「立即检查」：查到了就直接装，这是用户主动点的。 */
  const checkUpdate = async () => {
    if (updateBusy) return;
    setUpdateBusy(true);
    setUpdateLine("正在检查…");
    try {
      const r = await probeUpdate();
      if (r) await installUpdate(r);
    } catch (e) {
      setUpdateLine(`检查更新失败：${String(e)}`);
    } finally {
      setUpdateBusy(false);
    }
  };

  // 开机自动查一次。
  //
  // 查到了**不直接装** —— 用户刚点开软件多半是要马上用，后台自作主张占着网
  // 下几 MB 到几十 MB，是别人的软件才干的事。弹一条问一句，他说装才装。
  //
  // 没查到也要把「已是最新（版本号 + 时间）」写进状态行：这样进设置页时那行
  // 字已经在了，不用先点一下才知道自己是不是最新的。
  //
  // 延后 4 秒：启动那几秒 CPU 和磁盘都在忙着起引擎、扫音色，这一发网络请求
  // 挤进去只会让开屏更卡，而更新这件事晚四秒没有任何损失。
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          const r = await probeUpdate();
          if (!cancelled && r) setUpdateOffer(r);
        } catch {
          // 开机没网是常态，不要为此弹窗打扰。状态行留空，用户进设置页
          // 手点「立即检查」时才会看到具体的失败原因。
        }
      })();
    }, 4000);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  // 答应更新之后，那条提示**留在原地**变成进度，不跳页也不换地方看。
  // 把人扔到设置页去找进度条，等于让他自己去确认「我刚才点的那下算数了吗」。
  const [updateWorking, setUpdateWorking] = useState(false);
  const acceptUpdate = async () => {
    const r = updateOffer;
    if (!r) return;
    setUpdateWorking(true);
    setUpdateBusy(true);
    try {
      await installUpdate(r);
    } catch (e) {
      setUpdateLine(`更新失败：${String(e)}`);
    } finally {
      setUpdateBusy(false);
    }
  };
  const [pitch, setPitch] = useState(0);
  const [formant, setFormant] = useState(0);
  const [mode, setMode] = useState<OutputMode>("vc");
  const [voiceName, setVoiceName] = useState("未选择模型");
  const [voiceId, setVoiceId] = useState("");
  const [profileSummary, setProfileSummary] = useState("无");
  const [voiceTag, setVoiceTag] = useState("");
  const [voicePos, setVoicePos] = useState("");
  const [showProvision, setShowProvision] = useState(false);
  const [provisionDismissed, setProvisionDismissed] = useState(false);

  const engine = useEngine();
  const plaza = usePlaza();
  const { syncParams } = engine;

  // Telemetry consent: ask only after the user has actually got value out of
  // the product — 60 s of clean conversion — not at first launch.
  const [askTelemetry, setAskTelemetry] = useState(false);

  // The daily ping belongs to app start, not to every start/stop of the
  // stream. The Rust side dedupes by day, but firing it on each toggle still
  // meant a network attempt and a config write every time.
  useEffect(() => {
    void (async () => {
      const cfg = await invoke<Record<string, unknown>>("config_get").catch(() => null);
      if (cfg?.telemetry_opt_in === true) {
        void invoke("telemetry_tick").catch(() => {});
      }
    })();
  }, []);

  // Ask only after the user has actually got value out of the product —
  // 60 s of clean conversion — not at first launch.
  useEffect(() => {
    if (!engine.running) return;
    let timer: number | null = null;
    let cancelled = false;
    void (async () => {
      const cfg = await invoke<Record<string, unknown>>("config_get").catch(() => null);
      if (!cfg || cancelled) return;
      // null/undefined = never answered. false = declined, do not ask again.
      if (cfg.telemetry_opt_in !== null && cfg.telemetry_opt_in !== undefined) return;
      timer = window.setTimeout(() => !cancelled && setAskTelemetry(true), 60_000);
    })();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [engine.running]);

  const answerTelemetry = async (yes: boolean) => {
    setAskTelemetry(false);
    await invoke("config_set", { patch: { telemetry_opt_in: yes } }).catch(() => {});
    if (yes) void invoke("telemetry_tick").catch(() => {});
  };

  // 「喜欢的话关注一下」——攒够 FOLLOW_AFTER_RUNS 次变声之后问一次。
  //
  // 数的是**完成**的次数（开启→停止算一次），不是点了几次开启：起了又立刻
  // 报错停掉的不该算数，那种时候用户正在烦躁，问他要不要关注是最糟的时机。
  const [askFollow, setAskFollow] = useState(false);
  const wasRunning = useRef(false);
  useEffect(() => {
    const was = wasRunning.current;
    wasRunning.current = engine.running;
    if (!was || engine.running) return; // 只在 running: true → false 那一下计数
    void (async () => {
      try {
        const cfg = await invoke<Record<string, unknown>>("config_get");
        if (cfg.follow_prompt_done === true) return;
        const n = Number(cfg.vc_run_count ?? 0) + 1;
        await invoke("config_set", { patch: { vc_run_count: n } });
        if (n >= FOLLOW_AFTER_RUNS) setAskFollow(true);
      } catch {
        /* 配置读不到就算了，这不是要紧事 */
      }
    })();
  }, [engine.running]);

  // 不管点的是哪个社媒还是「以后再说」，都不再问第二次。反复问一件用户
  // 已经表过态的事，比不问更让人反感。
  const closeFollow = () => {
    setAskFollow(false);
    void invoke("config_set", { patch: { follow_prompt_done: true } }).catch(
      () => {},
    );
  };

  // Close prompt (close_action = "ask"). Same two choices as the Tk shell,
  // plus 「记住我的选择」 which writes close_action so we stop asking.
  const [closeAsk, setCloseAsk] = useState(false);
  const [closeRemember, setCloseRemember] = useState(false);
  const answerClose = async (toTray: boolean) => {
    setCloseAsk(false);
    if (closeRemember) {
      await invoke("config_set", {
        patch: { close_action: toTray ? "tray" : "exit" },
      }).catch(() => {});
    }
    await invoke("close_finish", { toTray }).catch(() => {});
  };



  useEffect(() => {
    if (engine.provision.need_provision && !provisionDismissed) {
      setShowProvision(true);
    }
  }, [engine.provision.need_provision, provisionDismissed]);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 520px)");
    const fn = () => setCompactNav(mq.matches);
    fn();
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);

  useEffect(() => {
    void currentVoice()
      .then((c) => {
        if (c.model) {
          setVoiceName(String(c.model.name || "未选择模型"));
          setVoiceId(String(c.model.path || c.model.dir || c.model.name || ""));
          setVoiceTag(String(c.model.tag || ""));
        }
        setVoicePos(c.index && c.total ? `${c.index}/${c.total}` : "");
        if (c.pitch != null) setPitch(Number(c.pitch));
        if (c.formant != null) setFormant(Number(c.formant));
        if (c.profile_summary) setProfileSummary(c.profile_summary);
        syncParams({
          pitch: c.pitch != null ? Number(c.pitch) : undefined,
          formant: c.formant != null ? Number(c.formant) : undefined,
        });
      })
      .catch(() => {
        /* browser preview */
      });
    // Runs once on mount; syncParams is stable (useCallback with no deps).
  }, [syncParams]);

  // The settings page reads only the device lists out of engine status, but the
  // whole status object changes every poll tick (mic level, latency), so
  // passing it straight through re-rendered that page 2.5x a second while
  // converting. Narrow it to the parts that actually change rarely.
  const st = engine.status as unknown as Record<string, unknown> | undefined;
  const deviceKey = JSON.stringify([
    st?.input_devices,
    st?.output_devices,
    st?.hostapis,
  ]);
  const deviceStatus = useMemo(
    () => ({
      input_devices: st?.input_devices,
      output_devices: st?.output_devices,
      hostapis: st?.hostapis,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on content, not identity
    [deviceKey],
  );

  const { onPitch, onFormant, onMode } = engine;
  const handlePitch = useCallback(
    (v: number) => {
      setPitch(v);
      onPitch(v);
    },
    [onPitch],
  );
  const handleFormant = useCallback(
    (v: number) => {
      setFormant(v);
      onFormant(v);
    },
    [onFormant],
  );
  const handleMode = useCallback(
    (m: OutputMode) => {
      setMode(m);
      onMode(m);
    },
    [onMode],
  );

  // One place where "the user picked a different voice" is applied, so the
  // home page and the models page can never drift apart on what the dock shows.
  const openModels = useCallback(() => setPage("models"), []);
  const openHelp = useCallback(() => setPage("help"), []);
  // 进广场同时把小红点消掉 —— 和顶栏点「广场」是同一件事，不能只有一条路
  // 清红点，否则从模型页进来的用户那个点永远亮着。
  const openPlaza = useCallback(() => {
    plaza.markSeen();
    setPage("plaza");
  }, [plaza]);
  const { reload: plazaReload } = plaza;
  const reloadPlaza = useCallback(() => void plazaReload(), [plazaReload]);

  const applyVoiceChange = useCallback(({
    model,
    pitch: p,
    formant: f,
    profileSummary: ps,
  }: {
    model: { name?: string; path?: string; dir?: string };
    pitch?: number;
    formant?: number;
    profileSummary?: string;
  }) => {
    setVoiceName(model.name || "未选择模型");
    setVoiceId(model.path || model.dir || model.name || "");
    if (p != null) setPitch(Number(p));
    if (f != null) setFormant(Number(f));
    if (ps) setProfileSummary(ps);
    setVoiceTag(String((model as { tag?: string }).tag || ""));
    // Keep what a later start will send in step with what the dock shows.
    syncParams({
      pitch: p != null ? Number(p) : undefined,
      formant: f != null ? Number(f) : undefined,
    });
    // The library position moves with the selection; only the shell knows it.
    void currentVoice()
      .then((c) => setVoicePos(c.index && c.total ? `${c.index}/${c.total}` : ""))
      .catch(() => {
        /* browser preview */
      });
  }, [syncParams]);

  // Ctrl+F5 / F6 step through the catalog, same as the old shell.
  const shiftVoice = useCallback(async (delta: number) => {
    try {
      const cat = await invoke<{
        models?: Array<Record<string, unknown>>;
        selected_idx?: number;
      }>("voices_list");
      const list = cat.models || [];
      if (!list.length) return;
      const cur = Number(cat.selected_idx ?? -1);
      const next = ((cur < 0 ? 0 : cur) + delta + list.length) % list.length;
      const m = list[next];
      const res = await invoke<{
        model?: Record<string, unknown>;
        pitch?: number;
        formant?: number;
        profile_summary?: string;
      }>("voices_select", {
        path: String(m.path ?? ""),
        dir: String(m.dir ?? ""),
        name: String(m.name ?? ""),
      });
      // Through the shared handler: the hotkeys used to set only the name, so
      // stepping voices with Ctrl+F5/F6 left the dock's tag, position, pitch
      // and profile showing the previous voice — and never pushed the new
      // voice's parameters to a running stream.
      applyVoiceChange({
        model: (res.model as { name?: string; path?: string; dir?: string }) || m,
        pitch: res.pitch,
        formant: res.formant,
        profileSummary: res.profile_summary,
      });
      if (res.pitch != null || res.formant != null) {
        try {
          await setHot({
            pitch: Number(res.pitch ?? 0),
            formant: Number(res.formant ?? 0),
          });
        } catch {
          /* worker may be idle */
        }
      }
    } catch {
      /* catalog unavailable */
    }
  }, [applyVoiceChange]);

  // Tray menu and global hotkeys drive the same actions as the dock, so the
  // shortcuts keep working while the window is hidden.
  //
  // The handlers close over `engine` and `shiftVoice`, and `useEngine` returns
  // a fresh object on every render — which the status poll causes once a
  // second. With those in the dependency array this effect re-ran that often,
  // and because `listen()` is async its cleanup ran while the promises were
  // still pending: it unregistered nothing. Six listeners leaked per second,
  // each one a live IPC registration on the Rust side, for as long as the app
  // stayed open. Register once and reach the current closures through a ref.
  const actionsRef = useRef({
    toggleRun: () => {},
    shiftVoice: (_d: number) => {},
    toggleMode: () => {},
    shiftPitch: (_d: number) => {},
    toggleCfgFlag: (_key: string) => {},
  });
  useEffect(() => {
    actionsRef.current = {
      toggleRun: () => void engine.toggleRun(),
      shiftVoice: (d: number) => void shiftVoice(d),
      toggleMode: () =>
        setMode((m) => {
          const next: OutputMode = m === "vc" ? "bypass" : "vc";
          void engine.onMode(next);
          return next;
        }),
      // 底栏那根音高条的范围，两处必须一致 —— 快捷键推到 25 而条子最多 24，
      // 界面和引擎就对不上了。
      shiftPitch: (d: number) =>
        setPitch((p) => {
          const next = Math.min(24, Math.max(-24, p + d));
          if (next !== p) onPitch(next);
          return next;
        }),
      // 监听自己 / 音效总开关。两个都是布尔配置项，读一次翻一次写回去。
      // config_set 那边会负责推给正在跑的引擎（监听是热推，音效本来就是热键）。
      toggleCfgFlag: (key: string) => {
        void (async () => {
          try {
            const cfg = await invoke<Record<string, unknown>>("config_get");
            await invoke("config_set", { patch: { [key]: cfg[key] !== true } });
          } catch {
            /* 引擎没起来时按了也不该炸 */
          }
        })();
      },
    };
  });

  useEffect(() => {
    let disposed = false;
    const offs: Array<() => void> = [];
    const add = async (event: string, fn: () => void) => {
      const un = await listen(event, fn);
      // Cleanup may have already run while this was in flight.
      if (disposed) un();
      else offs.push(un);
    };
    void add("tray://toggle-vc", () => actionsRef.current.toggleRun());
    void add("hotkey://toggle-vc", () => actionsRef.current.toggleRun());
    void add("hotkey://prev-voice", () => actionsRef.current.shiftVoice(-1));
    void add("hotkey://next-voice", () => actionsRef.current.shiftVoice(1));
    void add("hotkey://toggle-mode", () => actionsRef.current.toggleMode());
    void add("hotkey://pitch-up", () => actionsRef.current.shiftPitch(1));
    void add("hotkey://pitch-down", () => actionsRef.current.shiftPitch(-1));
    void add("hotkey://toggle-monitor", () =>
      actionsRef.current.toggleCfgFlag("monitor_self"),
    );
    void add("hotkey://toggle-fx", () =>
      actionsRef.current.toggleCfgFlag("fx_enabled"),
    );
    // hotkey://toggle-window 没有前端处理：窗口藏起来时 webview 可能被系统
    // 挂起，事件根本到不了这里。那个动作在 Rust 里就地做完了。
    void add("app://close-requested", () => setCloseAsk(true));
    return () => {
      disposed = true;
      offs.forEach((f) => f());
    };
  }, []);

  return (
    <div className="h-full flex flex-col bg-[var(--bg)] text-[var(--ink)] overflow-hidden relative">
      <TitleBar
        page={page}
        onPage={(id) => {
          // Opening the plaza is what clears its dot — it used to be hardcoded
          // on, so it meant nothing.
          if (id === "plaza") plaza.markSeen();
          setPage(id);
        }}
        plazaUnread={plaza.unread}
        compactNav={compactNav}
      />

      <ProvisionGate
        open={showProvision}
        initial={engine.provision}
        onDone={async () => {
          setShowProvision(false);
          setProvisionDismissed(false);
          try {
            await getProvisionStatus();
            await ensureEngine();
          } catch {
            /* refresh via hook poll */
          }
          await engine.refresh();
        }}
        onDismiss={() => {
          setShowProvision(false);
          setProvisionDismissed(true);
        }}
      />

      <PageHost page={page}>
        {(id) => {
          switch (id) {
            case "home":
              return (
                <HomePage
                  currentId={voiceId}
                  onOpenModels={openModels}
                  onVoiceChange={applyVoiceChange}
                />
              );
            case "plaza":
              return (
                <PlazaPage
                  feed={plaza.feed}
                  loading={plaza.loading}
                  onReload={reloadPlaza}
                />
              );
            case "models":
              return (
                <ModelsPage
                  banner={plaza.feed.banner}
                  onVoiceChange={applyVoiceChange}
                  onOpenPlaza={openPlaza}
                />
              );
            case "settings":
              return (
                <SettingsPage
                  status={deviceStatus as never}
                  onReloadDevices={() => void engine.reloadDevices()}
                  devicesBusy={engine.devicesBusy}
                  workerAlive={Boolean(engine.status.worker_alive)}
                  onCheckUpdate={() => void checkUpdate()}
                  updateLine={updateLine}
                  updateBusy={updateBusy}
                  onOpenHelp={openHelp}
                />
              );
            case "help":
              // 说明页要按用户真实的设备列表判断他装没装声卡，所以吃的是同一份
              // 收窄过的 deviceStatus（原始 status 每秒变两次半，会把页面刷爆）。
              return <HelpPage status={deviceStatus} />;
            case "more":
              return (
                <MorePage
                  status={engine.status}
                  provision={engine.provision}
                  onForceKill={async () => {
                    await forceKillEngine();
                    await engine.refresh();
                  }}
                  onOpenProvision={() => {
                    setProvisionDismissed(false);
                    setShowProvision(true);
                  }}
                />
              );
          }
        }}
      </PageHost>

      {closeAsk ? (
        <div className="absolute inset-0 z-[60] grid place-items-center bg-[color-mix(in_srgb,var(--ink)_28%,transparent)] p-6">
          <div className="w-full max-w-[420px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-6">
            <h2 className="text-[19px] font-semibold m-0 mb-2">关闭 RVC Fabric</h2>
            <p className="text-[13px] text-[var(--help)] m-0 mb-4 leading-relaxed">
              最小化到托盘可以让变声继续；直接关闭会停止变声并退出。
            </p>
            <label className="flex items-center gap-2.5 text-[13px] cursor-pointer mb-5 select-none">
              <input
                type="checkbox"
                checked={closeRemember}
                onChange={(e) => setCloseRemember(e.target.checked)}
                className="accent-[var(--accent)]"
              />
              记住我的选择（可在「设置 → 常规」改回）
            </label>
            <div className="flex gap-2.5 justify-end">
              <button
                type="button"
                onClick={() => void answerClose(false)}
                className="text-[13px] px-3.5 py-2 rounded-[var(--rs)] bg-transparent text-[var(--ink-muted)] border-0 cursor-pointer shadow-[inset_0_0_0_1px_var(--line)]"
              >
                直接关闭
              </button>
              <button
                type="button"
                onClick={() => void answerClose(true)}
                className="text-[13px] font-semibold px-3.5 py-2 rounded-[var(--rs)] bg-[var(--accent)] text-[var(--accent-ink)] border-0 cursor-pointer"
              >
                最小化到托盘
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* 同时最多出现一条。更新排最前 —— 它是开机 4 秒就出来的，那会儿另外
          两条的触发条件（用满 60 秒 / 变声十次）都还远没到。
          统计邀请次之，两条撞在一起会把底栏顶掉半个屏。 */}
      {updateOffer ? (
        <Nudge
          title={
            updateWorking
              ? "正在更新"
              : `有新版本 ${updateOffer.remote}，现在装吗？`
          }
          actions={
            updateWorking ? (
              <Btn onClick={() => setUpdateOffer(null)} disabled={updateBusy}>
                {updateBusy ? "下载中…" : "知道了"}
              </Btn>
            ) : (
              <>
                <Btn onClick={() => setUpdateOffer(null)}>稍后</Btn>
                <Btn primary onClick={() => void acceptUpdate()}>
                  下载并安装
                </Btn>
              </>
            )
          }
        >
          {updateWorking
            ? updateLine
            : `当前 ${updateOffer.local}。${
                updateOffer.notes ||
                (updateOffer.action === "external"
                  ? "这次要换程序本体，装完重启一次就好。"
                  : "这次只换界面，装完重启一次就好。")
              }下载期间可以照常用，不影响变声。`}
        </Nudge>
      ) : askTelemetry ? (
        <Nudge
          title="参与用户统计（可选）"
          actions={
            <>
              <Btn onClick={() => void answerTelemetry(false)}>暂不参与</Btn>
              <Btn primary onClick={() => void answerTelemetry(true)}>
                参与
              </Btn>
            </>
          }
        >
          每天检查更新时附带一个随机匿名编号、软件版本、显卡加速方式。
          不会发送账号、音色文件、录音，或任何能定位到你的信息。
          规模数据用于和赞助商谈合作，这是我们维持开发的方式之一。随时可在「设置 → 常规」关闭。
        </Nudge>
      ) : askFollow ? (
        <Nudge
          title="喜欢 RVC Fabric 吗？关注一下我们呗"
          actions={
            <>
              <Btn onClick={closeFollow}>以后再说</Btn>
              {FOLLOW_LINKS.map((l) => (
                <Btn
                  key={l.url}
                  onClick={() => {
                    void openExternal(l.url);
                    closeFollow();
                  }}
                >
                  {l.short}
                </Btn>
              ))}
            </>
          }
        >
          你已经用它变声十次了。软件是免费的，更新全靠有人看见 ——
          点一下就到，关不关注都随你，这句话只说这一次。
        </Nudge>
      ) : null}

      <Dock
        voiceName={voiceName}
        voiceTag={voiceTag}
        voiceIndex={voicePos}
        pitch={pitch}
        formant={formant}
        onPitch={handlePitch}
        onFormant={handleFormant}
        mode={mode}
        onMode={handleMode}
        running={engine.running || engine.starting}
        onToggleRun={() => void engine.toggleRun()}
        profileSummary={profileSummary}
        statusTitle={engine.title}
        statusSub={engine.sub}
        micDb={engine.micDb}
        thresholdDb={engine.thresholdDb}
      />
    </div>
  );
}
