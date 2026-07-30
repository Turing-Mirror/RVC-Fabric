import { useEffect, useState } from "react";
import { Dock, type OutputMode } from "./components/Dock";
import { PageHost } from "./components/PageHost";
import { ProvisionGate } from "./components/ProvisionGate";
import { TitleBar } from "./components/TitleBar";
import { useEngine } from "./hooks/useEngine";
import { ensureEngine, forceKillEngine, getProvisionStatus } from "./lib/engine";
import type { PageId } from "./lib/nav";
import { currentVoice } from "./lib/voices";
import { invoke } from "@tauri-apps/api/core";
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
          const { convertFileSrc } = await import("@tauri-apps/api/core");
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
        setUpdateLine(`有新版本 ${String(r.remote)}，需要重新下载安装包`);
        return;
      }
      setUpdateLine(`发现 ${String(r.remote)}，正在下载界面更新…`);
      await invoke("update_apply", { url: String(r.url), sha256: String(r.sha256 || "") });
      setUpdateLine(`已更新到 ${String(r.remote)}，重启程序后生效`);
    } catch (e) {
      setUpdateLine(`检查更新失败：${String(e)}`);
    }
  };
  const [pitch, setPitch] = useState(0);
  const [formant, setFormant] = useState(0);
  const [mode, setMode] = useState<OutputMode>("vc");
  const [voiceName, setVoiceName] = useState("未选择模型");
  const [voiceId, setVoiceId] = useState("");
  const [profileSummary, setProfileSummary] = useState("默认（原始参数）");
  const [showProvision, setShowProvision] = useState(false);
  const [provisionDismissed, setProvisionDismissed] = useState(false);

  const engine = useEngine();

  // Telemetry consent: ask only after the user has actually got value out of
  // the product — 60 s of clean conversion — not at first launch.
  const [askTelemetry, setAskTelemetry] = useState(false);
  useEffect(() => {
    let timer: number | null = null;
    let cancelled = false;
    void (async () => {
      const cfg = await invoke<Record<string, unknown>>("config_get").catch(() => null);
      if (!cfg || cancelled) return;
      if (cfg.telemetry_opt_in !== null && cfg.telemetry_opt_in !== undefined) {
        if (cfg.telemetry_opt_in === true) void invoke("telemetry_tick").catch(() => {});
        return;
      }
      if (!engine.running) return;
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

  // Tray menu and global hotkeys drive the same actions as the dock, so the
  // shortcuts keep working while the window is hidden.
  useEffect(() => {
    const offs: Array<() => void> = [];
    const wire = async () => {
      offs.push(await listen("tray://toggle-vc", () => void engine.toggleRun()));
      offs.push(await listen("hotkey://toggle-vc", () => void engine.toggleRun()));
      offs.push(
        await listen("hotkey://toggle-mode", () => {
          setMode((m) => {
            const next: OutputMode = m === "vc" ? "bypass" : "vc";
            void engine.onMode(next);
            return next;
          });
        }),
      );
    };
    void wire();
    return () => offs.forEach((f) => f());
  }, [engine]);

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
        }
        if (c.pitch != null) setPitch(Number(c.pitch));
        if (c.formant != null) setFormant(Number(c.formant));
        if (c.profile_summary) setProfileSummary(c.profile_summary);
      })
      .catch(() => {
        /* browser preview */
      });
  }, []);

  const handlePitch = (v: number) => {
    setPitch(v);
    engine.onPitch(v);
  };
  const handleFormant = (v: number) => {
    setFormant(v);
    engine.onFormant(v);
  };
  const handleMode = (m: OutputMode) => {
    setMode(m);
    engine.onMode(m);
  };

  return (
    <div className="h-full flex flex-col bg-[var(--bg)] text-[var(--ink)] overflow-hidden relative">
      <TitleBar
        page={page}
        onPage={setPage}
        plazaUnread
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
                  onOpenModels={() => setPage("models")}
                  onSelect={(id) => setVoiceId(id)}
                />
              );
            case "plaza":
              return <PlazaPage />;
            case "models":
              return (
                <ModelsPage
                  onVoiceChange={({ model, pitch: p, formant: f, profileSummary: ps }) => {
                    setVoiceName(model.name || "未选择模型");
                    setVoiceId(model.path || model.dir || model.name || "");
                    if (p != null) setPitch(Number(p));
                    if (f != null) setFormant(Number(f));
                    if (ps) setProfileSummary(ps);
                  }}
                />
              );
            case "settings":
              return (
                <SettingsPage
                  status={engine.status}
                  onReloadDevices={() => void engine.refresh()}
                  onCheckUpdate={() => void checkUpdate()}
                  updateLine={updateLine}
                />
              );
            case "help":
              return <HelpPage />;
            case "more":
              return (
                <MorePage
                  onCheckUpdate={() => void checkUpdate()}
                  updateLine={updateLine}
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
