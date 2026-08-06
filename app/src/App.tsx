import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Dock, type OutputMode } from "./components/Dock";
import { Nudge } from "./components/Nudge";
import { Btn } from "./components/ui";
import { followLinks } from "./lib/links";
import { openExternal } from "./lib/plaza";
import { comboFromEvent, localHotkeyMap, typingInto } from "./lib/hotkeys";
import { PageHost } from "./components/PageHost";
import { ProvisionGate } from "./components/ProvisionGate";
import { TitleBar } from "./components/TitleBar";
import { useEngine } from "./hooks/useEngine";
import { usePlaza } from "./hooks/usePlaza";
import { forceKillEngine, setHot, swapModel } from "./lib/engine";
import type { PageId } from "./lib/nav";
import { currentVoice } from "./lib/voices";
import { invoke } from "@tauri-apps/api/core";
import { applyAppearance } from "./lib/appearance";
import { listen } from "@tauri-apps/api/event";
import { HelpPage } from "./pages/HelpPage";
import { HomePage } from "./pages/HomePage";
import { ModelsPage } from "./pages/ModelsPage";
import { MorePage } from "./pages/MorePage";
import { PlazaPage } from "./pages/PlazaPage";
import { SettingsPage } from "./pages/SettingsPage";
import { registerDownloadModelsOpener } from "./lib/downloadModels";
import { t } from "./i18n/t";

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
  // 「下载模型」：用户主动打开，或音频工具缺引擎资源时跳转。
  const [extrasOpen, setExtrasOpen] = useState(false);
  const [extrasReason, setExtrasReason] = useState("");
  // Self-update: check reports the catalog's latest; applying swaps the
  // external frontend/ dir and takes effect on restart.
  const [updateLine, setUpdateLine] = useState("");
  // 检查更新唯一的反馈原来只有一行灰色小字，用户点完看不出点没点上，
  // 会以为按钮坏了。按钮自己也要进入「检查中…」并禁用。
  const [updateBusy, setUpdateBusy] = useState(false);

  // 开机时把外观（配色 / 背景图 / 磨砂 / 不透明度）套上。之后用户在设置页
  // 每改一下都由 useConfig 就地再套一次，所以这里只跑一次就够 —— 以前依赖数组
  // 写的是 [page]，等于「换页才刷新外观」，改完当场毫无反应。
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const cfg = await invoke<Record<string, unknown>>("config_get");
        if (alive) applyAppearance(cfg);
      } catch {
        /* config unavailable outside Tauri */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);
  // 启动时自动查到的新版本。非空 = 弹一条「要不要现在装」。
  const [updateOffer, setUpdateOffer] = useState<UpdateInfo | null>(null);

  /** 只查，不装。返回后端那份原样的结果，顺手把状态行写好。 */
  const probeUpdate = async (): Promise<UpdateInfo | null> => {
    const r = (await invoke<Record<string, unknown>>(
      "update_check",
    )) as UpdateInfo;
    if (r.blocked_by_min_version) {
      setUpdateLine(
        t("s.214fe7bcad", {
          v0: String(r.local),
          v1: String(r.min_app_version),
        }),
      );
      return null;
    }
    if (!r.available) {
      // 「已是最新」必须带上版本号和时间。只说一句「已是最新」，用户分不清
      // 是真查过了还是根本没查动。
      setUpdateLine(
        t("s.7ccca92d5e", { v0: String(r.local), v1: clockNow() }),
      );
      return null;
    }
    setUpdateLine(
      t("s.622a22349e", {
        v0: String(r.remote),
        v1: String(r.local),
      }),
    );
    return r;
  };

  /** 真正下载并安装。整包走签名更新器，界面补丁走 update_apply。 */
  const installUpdate = async (r: UpdateInfo) => {
    if (r.action === "external") {
      // Rust side changed → replace the exe through the signed updater.
      setUpdateLine(t("s.b22f6e52ac", { v0: String(r.remote) }));
      const b = await invoke<Record<string, unknown>>("update_app");
      setUpdateLine(
        b.installed
          ? t("s.995e0f4c81", {
              v0: String(b.version ?? r.remote),
            })
          : t("s.3d1fde4601"),
      );
      return;
    }
    setUpdateLine(t("s.5b3dc1999a", { v0: String(r.remote) }));
    await invoke("update_apply", {
      url: String(r.url),
      sha256: String(r.sha256 || ""),
    });
    setUpdateLine(t("s.995e0f4c81", { v0: String(r.remote) }));
  };

  /** 设置页那个「立即检查」：查到了就直接装，这是用户主动点的。 */
  const checkUpdate = async () => {
    if (updateBusy) return;
    setUpdateBusy(true);
    setUpdateLine(t("s.481ee2d4bc"));
    try {
      const r = await probeUpdate();
      if (r) await installUpdate(r);
    } catch (e) {
      setUpdateLine(t("s.ac3a85a9c1", { v0: String(e) }));
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
      setUpdateLine(t("s.bac68ea7db", { v0: String(e) }));
    } finally {
      setUpdateBusy(false);
    }
  };
  const [pitch, setPitch] = useState(0);
  const [formant, setFormant] = useState(0);
  const [mode, setMode] = useState<OutputMode>("vc");
  const [voiceName, setVoiceName] = useState(t("s.262d11e2d6"));
  const [voiceId, setVoiceId] = useState("");
  const [profileSummary, setProfileSummary] = useState(t("s.72077749f7"));
  const [voiceTag, setVoiceTag] = useState("");
  const [voicePos, setVoicePos] = useState("");
  const [showProvision, setShowProvision] = useState(false);
  const [provisionDismissed, setProvisionDismissed] = useState(false);

  const engine = useEngine();
  const plaza = usePlaza();
  const { syncParams, refreshProvision } = engine;

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
          setVoiceName(String(c.model.name || t("s.262d11e2d6")));
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
  const openDownloadModels = useCallback((reason?: string) => {
    setPage("more");
    setExtrasReason(reason || "");
    setExtrasOpen(true);
  }, []);

  useEffect(() => {
    registerDownloadModelsOpener((opts) => {
      openDownloadModels(opts?.reason);
    });
    return () => registerDownloadModelsOpener(null);
  }, [openDownloadModels]);
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
    setVoiceName(model.name || t("s.262d11e2d6"));
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
    // 正在变声的时候换模型：热换，不重开流。
    //
    // 引擎现在认 pth_path 这个热更新键了 —— 音频线程在两块之间把 RVC 实例
    // 换掉，设备、缓冲区、延迟设置全都不动。用户听到的是零点几秒的接缝，
    // 而不是停流重开的那二三十秒。
    //
    // 采样率跟随模型、而新模型的采样率又不一样时，引擎自己退回重开流 ——
    // 那种情况下整条流水线的尺寸都变了，换不了。
    //
    // 没在跑的时候后端会报「worker 未运行」，那不是故障：配置已经是新的，
    // 下次开启自然就对，所以吞掉。
    void swapModel().catch(() => {});
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

  // 取消了「全局」的那些快捷键，在这里接。
  //
  // Rust 只注册勾了「全局」的组合 —— 全局快捷键是独占的，被抢走的组合用户在
  // 别的软件里就按不出原本的功能了，所以每个都可以单独关掉。关掉的那些改由
  // 本窗口的 keydown 接住：只在 RVC Fabric 是当前窗口时生效，正好是用户要的。
  //
  // 不会和全局的重复触发：localHotkeyMap 只收 `_global` 为 false 的。
  useEffect(() => {
    let map = new Map<string, string>();
    let alive = true;
    const reload = () => {
      void invoke<Record<string, unknown>>("config_get")
        .then((cfg) => {
          if (alive) map = localHotkeyMap(cfg);
        })
        .catch(() => {
          /* 浏览器预览下没有配置 */
        });
    };
    reload();
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || typingInto(e.target)) return;
      const action = map.get(comboFromEvent(e));
      if (!action) return;
      e.preventDefault();
      const a = actionsRef.current;
      switch (action) {
        case "toggle-vc":
          a.toggleRun();
          break;
        case "toggle-mode":
          a.toggleMode();
          break;
        case "prev-voice":
          a.shiftVoice(-1);
          break;
        case "next-voice":
          a.shiftVoice(1);
          break;
        case "pitch-up":
          a.shiftPitch(1);
          break;
        case "pitch-down":
          a.shiftPitch(-1);
          break;
        case "toggle-monitor":
          a.toggleCfgFlag("monitor_self");
          break;
        case "toggle-fx":
          a.toggleCfgFlag("fx_enabled");
          break;
        // toggle-window 非全局时没有意义：窗口就在眼前，用不着「显示」它，
        // 而藏起来之后这个监听器也就收不到键了。忽略。
        default:
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    // 设置页改完会重新注册一次全局快捷键；借同一个时机把这份表也重读。
    const un = listen("hotkeys://changed", reload);
    return () => {
      alive = false;
      window.removeEventListener("keydown", onKey);
      void un.then((f) => f());
    };
  }, []);

  return (
    // 根容器不铺底色：底色在 html 上，壁纸层夹在中间。这里再铺一层不透明的
    // --bg 会把壁纸盖死 —— 这正是「背景图设了没反应」的另一半原因。
    <div className="h-full flex flex-col text-[var(--ink)] overflow-hidden relative">
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
          // 这里以前调的是 getProvisionStatus()，**结果直接扔掉** —— 问了等于
          // 没问，engine.provision 还是补全之前那份 runtime_ready: false。
          // 于是运行时装好了，「开启变声」照样被 toggleRun 开头那道闸拦下来
          // 说「运行时未就绪」，只能重启软件。refreshProvision 会把结果写回
          // 状态，并且在 false → true 的那一下顺手把引擎拉起来。
          try {
            await refreshProvision();
          } catch {
            /* 轮询兜底 */
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
                  extrasOpen={extrasOpen}
                  extrasReason={extrasReason}
                  onExtrasOpenChange={(open) => {
                    setExtrasOpen(open);
                    if (!open) setExtrasReason("");
                  }}
                  onOpenDownloadModels={openDownloadModels}
                />
              );
          }
        }}
      </PageHost>

      {closeAsk ? (
        <div className="absolute inset-0 z-[60] grid place-items-center bg-[color-mix(in_srgb,var(--ink)_28%,transparent)] p-6">
          <div className="w-full max-w-[420px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-6">
            <h2 className="text-[19px] font-semibold m-0 mb-2">{t("s.43b19c9a61")}</h2>
            <p className="text-[13px] text-[var(--help)] m-0 mb-4 leading-relaxed">{t("s.bc19958103")}</p>
            <label className="flex items-center gap-2.5 text-[13px] cursor-pointer mb-5 select-none">
              <input
                type="checkbox"
                checked={closeRemember}
                onChange={(e) => setCloseRemember(e.target.checked)}
                className="accent-[var(--accent)]"
              />{t("s.f75c86ad46")}</label>
            <div className="flex gap-2.5 justify-end">
              <button
                type="button"
                onClick={() => void answerClose(false)}
                className="text-[13px] px-3.5 py-2 rounded-[var(--rs)] bg-transparent text-[var(--ink-muted)] border-0 cursor-pointer shadow-[inset_0_0_0_1px_var(--line)]"
              >{t("s.3a070016e2")}</button>
              <button
                type="button"
                onClick={() => void answerClose(true)}
                className="text-[13px] font-semibold px-3.5 py-2 rounded-[var(--rs)] bg-[var(--accent)] text-[var(--accent-ink)] border-0 cursor-pointer"
              >{t("s.aea56dcdfe")}</button>
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
              ? t("s.87c1bc6fe6")
              : t("s.a462205ca5", { v0: updateOffer.remote })
          }
          actions={
            updateWorking ? (
              <Btn onClick={() => setUpdateOffer(null)} disabled={updateBusy}>
                {updateBusy ? t("s.65188d08a2") : t("s.cb63c62e50")}
              </Btn>
            ) : (
              <>
                <Btn onClick={() => setUpdateOffer(null)}>{t("s.479fcc1cc0")}</Btn>
                <Btn primary onClick={() => void acceptUpdate()}>{t("s.f4df9977ea")}</Btn>
              </>
            )
          }
        >
          {updateWorking
            ? updateLine
            : t("s.3956a2d8bb", {
                v0: updateOffer.local,
                v1:
                  updateOffer.notes ||
                  t("s.58941d30b7"),
              })}
        </Nudge>
      ) : askTelemetry ? (
        <Nudge
          title={t("s.b9feeeb3a8")}
          actions={
            <>
              <Btn onClick={() => void answerTelemetry(false)}>{t("s.206f264868")}</Btn>
              <Btn primary onClick={() => void answerTelemetry(true)}>{t("s.d9702f047c")}</Btn>
            </>
          }
        >{t("s.9546e0b7e2")}</Nudge>
      ) : askFollow ? (
        <Nudge
          title={t("s.d359cf1384")}
          actions={
            <>
              <Btn onClick={closeFollow}>{t("s.6aa652ccb5")}</Btn>
              {followLinks().map((l) => (
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
        >{t("s.7f3ebfb67b")}</Nudge>
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
