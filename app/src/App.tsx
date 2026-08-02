import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Dock, type OutputMode } from "./components/Dock";
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
  const checkUpdate = async () => {
    if (updateBusy) return;
    setUpdateBusy(true);
    setUpdateLine("正在检查…");
    try {
      const r = await invoke<Record<string, unknown>>("update_check");
      if (r.blocked_by_min_version) {
        setUpdateLine(`需要先更新到 ${String(r.min_app_version)} 才能继续`);
        return;
      }
      if (!r.available) {
        setUpdateLine(`已是最新（${String(r.local)}）`);
        return;
      }
      if (r.action === "external") {
        // Rust side changed → replace the exe through the signed updater.
        setUpdateLine(`有新版本 ${String(r.remote)}，正在下载程序更新…`);
        const b = await invoke<Record<string, unknown>>("update_app");
        setUpdateLine(
          b.installed
            ? `已更新到 ${String(b.version ?? r.remote)}，重启程序后生效`
            : `暂时取不到程序更新包，可先到发布页手动下载`,
        );
        return;
      }
      setUpdateLine(`发现 ${String(r.remote)}，正在下载界面更新…`);
      await invoke("update_apply", { url: String(r.url), sha256: String(r.sha256 || "") });
      setUpdateLine(`已更新到 ${String(r.remote)}，重启程序后生效`);
    } catch (e) {
      setUpdateLine(`检查更新失败：${String(e)}`);
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

      {askTelemetry ? (
        <div className="mx-[30px] mb-2 rounded-[var(--r)] bg-[var(--group)] px-4 py-3 flex items-start gap-3 flex-wrap max-[720px]:mx-4">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold mb-1">参与用户统计（可选）</div>
            <div className="text-[12.5px] text-[var(--help)] leading-relaxed">
              每天检查更新时附带一个随机匿名编号、软件版本、显卡加速方式。
              不会发送账号、音色文件、录音，或任何能定位到你的信息。
              规模数据用于和赞助商谈合作，这是我们维持开发的方式之一。随时可在「设置 → 常规」关闭。
            </div>
          </div>
          <div className="flex gap-2 items-center">
            <button
              type="button"
              onClick={() => void answerTelemetry(true)}
              className="text-[12.5px] font-semibold px-3.5 py-1.5 rounded-[var(--rs)] bg-[var(--accent)] text-[var(--accent-ink)] border-0 cursor-pointer"
            >
              参与
            </button>
            <button
              type="button"
              onClick={() => void answerTelemetry(false)}
              className="text-[12.5px] px-3.5 py-1.5 rounded-[var(--rs)] bg-transparent text-[var(--ink-muted)] cursor-pointer border-0 shadow-[inset_0_0_0_1px_var(--line)]"
            >
              暂不参与
            </button>
          </div>
        </div>
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
