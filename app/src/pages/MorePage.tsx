import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Block, Btn, Group, ListItem, PageHead, PagePad } from "../components/ui";
import { openTool } from "../components/ToolWindow";
import { QrDialog } from "../components/QrDialog";
import { MainGpuPicker, MAIN_GPU_AUTO, mainGpuTip } from "../components/MainGpuPicker";
import { openExternal } from "../lib/plaza";
import { allLinks } from "../lib/links";
import { tip } from "../lib/glossary";
import { statusTitle } from "../lib/engine";
import type { EngineStatus, ProvisionStatus } from "../lib/engine";
import { t } from "../i18n/t";
import { askConfirm } from "../lib/webDialog";

/** 「申请专业优化」的开关。服务还没开放，先藏起来；后端命令仍然在。 */
const SHOW_CONSULT = false;

type Props = {
  status?: EngineStatus;
  provision?: ProvisionStatus;
  onForceKill?: () => void | Promise<void>;
  onOpenProvision?: () => void;
  /** 「下载模型」住在广场，这里只有一个跳过去的入口。 */
  onOpenDownloadModels?: (reason?: string) => void;
};

export function MorePage({
  status,
  provision,
  onForceKill,
  onOpenProvision,
  onOpenDownloadModels,
}: Props = {}) {
  // Where the UI itself is served from. Surfaced so a UI patch that did not
  // take effect is diagnosable instead of invisible (OTA strategy A).
  const [uiSource, setUiSource] = useState("—");
  // 有二维码的社媒条目（QQ 群）点开的是图片，不是外链。
  const [qr, setQr] = useState<{ src: string; label: string } | null>(null);
  // Where the app thinks it is installed. The row below used to only describe
  // that this is resolved automatically, without ever showing the answer —
  // which is the first thing worth knowing when a report says "找不到 Runtime".
  const [root, setRoot] = useState("—");
  const [logFile, setLogFile] = useState("");
  const [cacheMb, setCacheMb] = useState("");
  const [version, setVersion] = useState("—");
  const [busyMsg, setBusyMsg] = useState("");
  // 主显卡。放在「补全运行时」旁边：装完运行时之后才谈得上用哪块卡算，
  // 而这一整块讲的就是「这台机器拿什么在跑」。
  const [mainGpu, setMainGpu] = useState<number>(MAIN_GPU_AUTO);
  const [gpuMsg, setGpuMsg] = useState("");
  const nvGpus = provision?.nvidia_gpus || [];

  const pickMainGpu = (v: number) => {
    setMainGpu(v);
    setGpuMsg("");
    void invoke("config_set", { patch: { main_gpu: v } })
      .then(() => setGpuMsg(t("s.9249d39bac")))
      .catch((e) => setGpuMsg(t("s.e0125710be", { v0: String(e) })));
  };

  // Both of these are 20–40s cold starts (torch/CUDA). Say so on the row
  // itself; a button that looks like it did nothing gets clicked again.
  const [legacyMsg, setLegacyMsg] = useState<{ panel?: string; webui?: string }>({});
  const openLegacy = async (which: "panel" | "webui") => {
    setLegacyMsg((m) => ({ ...m, [which]: t("s.4fe38132a0") }));
    try {
      const r = await invoke<{ message?: string; url?: string }>(
        which === "panel" ? "legacy_open_panel" : "legacy_open_webui",
      );
      setLegacyMsg((m) => ({ ...m, [which]: r?.message || t("s.0eeffdd75b") }));
      if (which === "webui" && r?.url) {
        // Gradio needs a few seconds to bind the port; opening immediately
        // lands on a connection-refused page.
        setTimeout(() => {
          void invoke("open_external", { url: r.url }).catch(() => {});
        }, 4000);
      }
    } catch (e) {
      setLegacyMsg((m) => ({
        ...m,
        [which]: t("s.ea582ad463", { v0: String(e) }),
      }));
    }
  };

  const run = async (label: string, cmd: string, args?: Record<string, unknown>) => {
    setBusyMsg(`${label}…`);
    try {
      const r = await invoke<{ path?: string; perf_note?: string }>(cmd, args);
      const note = r?.perf_note ? ` · ${r.perf_note}` : "";
      setBusyMsg(
        t("s.05d0e1e672", {
          v0: label,
          v1: r?.path ?? "",
          v2: note,
        }),
      );
    } catch (e) {
      setBusyMsg(t("s.179ee96e83", { v0: label, v1: String(e) }));
    }
  };

  /** 生成诊断包：先问要不要跑约一分钟的性能测试。 */
  const runDiagnostics = async () => {
    // 确定 = 先 bench；取消 = 只打日志与设置。
    const withPerf = await askConfirm(
      t("s.dd3c9cc8db") +
        t("s.50b717c880") +
        t("s.a9094fb530") +
        t("s.8ba72769d6"),
    );
    setBusyMsg(
      withPerf
        ? t("s.d7ae8f757e")
        : t("s.56ce781723"),
    );
    try {
      const r = await invoke<{ path?: string; perf_note?: string }>(
        "diagnostics_build",
        { withPerf },
      );
      const note = r?.perf_note ? ` · ${r.perf_note}` : "";
      setBusyMsg(
        t("s.ae82b8cc23", { v0: r?.path ?? "", v1: note }),
      );
    } catch (e) {
      setBusyMsg(t("s.7fae0289b6", { v0: String(e) }));
    }
  };
  useEffect(() => {
    let alive = true;
    invoke<string>("ui_source")
      .then((v) => alive && setUiSource(v || "—"))
      .catch(() => alive && setUiSource("—"));
    invoke<string>("product_root")
      .then((v) => alive && setRoot(v || "—"))
      .catch(() => alive && setRoot("—"));
    invoke<string>("shell_version")
      .then((v) => alive && setVersion(v || "—"))
      .catch(() => alive && setVersion("—"));
    invoke<string | null>("log_path")
      .then((v) => alive && setLogFile(v || ""))
      .catch(() => alive && setLogFile(""));
    invoke<{ mb?: string }>("cache_status")
      .then((v) => alive && setCacheMb(v?.mb || "0"))
      .catch(() => alive && setCacheMb(""));
    invoke<Record<string, unknown>>("config_get")
      .then((c) => alive && setMainGpu(Number(c.main_gpu ?? MAIN_GPU_AUTO)))
      .catch(() => {
        /* 浏览器预览下没有配置 */
      });
    return () => {
      alive = false;
    };
  }, []);

  const delay = Number(status?.delay_ms || 0);
  const infer = Number(status?.infer_ms || 0);
  const latency =
    status?.state === "running"
      ? t("s.4461ca9594", { v0: delay, v1: infer })
      : status?.worker_alive
        ? t("s.1a0db8dc43")
        : "—";

  const gpus = provision?.gpus?.length
    ? provision.gpus.join(" · ")
    : t("s.90b74980e4");
  const runtimeLine = provision?.runtime_ready
    ? provision.installed_variant
      ? t("s.7dd9064298", { v0: provision.installed_variant })
      : t("s.f2afde8960")
    : t("s.5abed96e7d");

  return (
    <PagePad>
      <PageHead title={t("s.1a26edf94a")} sub={t("s.d0b65d2fd2")} />
      <Block title={t("s.2a4080ad9f")}>
        <Group>
          <ListItem
            title={t("s.a8f48b775b")}
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)]">{version}</span>
            }
          />
          <ListItem
            title={t("s.2a4b19a6b1")}
            right={
              <span
                className="text-[13.5px] text-[var(--ink-muted)] max-w-[300px] text-right truncate"
                title={root}
              >
                {root}
              </span>
            }
          />
          <ListItem
            title={t("s.fe0eb943d7")}
            right={
              <span
                className="text-[13.5px] text-[var(--ink-muted)] max-w-[280px] text-right truncate"
                title={uiSource}
              >
                {uiSource}
              </span>
            }
          />
          <ListItem
            title={t("s.cef8154370")}
            titleTip={tip(t("s.cef8154370"))}
            desc={
              provision?.recommend_reason ||
              (status?.product_root ? String(status.product_root) : t("s.002dcbcd28"))
            }
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)]">{runtimeLine}</span>
            }
          />
          <ListItem
            title={t("s.f41830a38d")}
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)] max-w-[220px] text-right truncate" title={gpus}>
                {gpus}
              </span>
            }
          />
          {/* 只有一块 N 卡时不显示：那时候「选哪块」是个假选择。 */}
          {nvGpus.length > 1 ? (
            <ListItem
              title={t("s.6b26feecc1")}
              titleTip={mainGpuTip()}
              desc={
                gpuMsg ||
                t("s.63d89cdb5c")
              }
              right={
                <MainGpuPicker
                  gpus={nvGpus}
                  value={mainGpu}
                  onChange={pickMainGpu}
                />
              }
            />
          ) : null}
          <ListItem
            title={t("s.07a1fa9790")}
            desc={
              provision?.download_supported
                ? provision.need_provision
                  ? t("s.eb033e6340")
                  : t("s.1148b67ccc")
                : t("s.63e829016e")
            }
            right={
              <span className="flex items-center gap-2">
                <span className="text-[13.5px] text-[var(--ink-muted)]">
                  {provision?.recommended_variant || "—"}
                </span>
                {onOpenProvision ? (
                  <Btn onClick={onOpenProvision}>
                    {provision?.need_provision ? t("s.d5c27cb2ba") : t("s.69f5974b47")}
                  </Btn>
                ) : null}
              </span>
            }
          />
          <ListItem
            title={t("s.fbb8ddd570")}
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)]">
                {status ? statusTitle(status) : "—"}
                {status?.pid ? ` · pid ${status.pid}` : ""}
              </span>
            }
          />
          <ListItem
            title={t("s.746fcbb99c")}
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">{latency}</span>}
          />
        </Group>
      </Block>
      <Block title={t("s.21093d185d")}>
        <Group>
          <ListItem
            title={t("s.8fd038283b")}
            desc={t("s.be70b437af")}
            right={<Btn onClick={() => openTool("separate")}>{t("s.65fc81e161")}</Btn>}
          />
          <ListItem
            title={t("s.ba65bd5595")}
            desc={t("s.6a71c2fde0")}
            right={<Btn onClick={() => openTool("train")}>{t("s.65fc81e161")}</Btn>}
          />
          <ListItem
            title={t("s.6f311c47fe")}
            desc={t("s.ba7bd6e071")}
            right={<Btn onClick={() => openTool("tts")}>{t("s.65fc81e161")}</Btn>}
          />
          {/* 入口留着（老用户是从这儿找它的），功能已经搬去广场了。 */}
          <ListItem
            title={t("s.1252c81119")}
            desc={t("s.e197a257da")}
            right={
              <Btn onClick={() => onOpenDownloadModels?.()}>{t("s.65fc81e161")}</Btn>
            }
          />
        </Group>
      </Block>

      <Block title={t("s.72527e2f0e")}>
        <Group>
          <ListItem
            title={t("s.8b720e5330")}
            desc={
              busyMsg.startsWith(t("s.8b720e5330"))
                ? busyMsg
                : t("s.df51787548")
            }
            right={
              <Btn onClick={() => void runDiagnostics()}>{t("s.4aa2306395")}</Btn>
            }
          />
          <ListItem
            title={t("s.a5f158e6bc")}
            right={
              <Btn onClick={() => void invoke("reveal_user_dir", { name: "perf_reports" })}>{t("s.65fc81e161")}</Btn>
            }
          />
          <ListItem
            title={t("s.bc20b5032f")}
            desc={logFile || undefined}
            right={
              <Btn onClick={() => void invoke("reveal_user_dir", { name: "logs" })}>{t("s.65fc81e161")}</Btn>
            }
          />
          <ListItem
            title={t("s.cacheClear")}
            desc={
              busyMsg.startsWith(t("s.cacheClear"))
                ? busyMsg
                : cacheMb
                  ? t("s.cacheClearDesc", { v0: cacheMb })
                  : t("s.cacheClearHint")
            }
            right={
              <Btn
                onClick={async () => {
                  if (!(await askConfirm(t("s.cacheClearConfirm")))) return;
                  setBusyMsg(t("s.cacheClear") + "…");
                  void invoke<{ freed_mb?: string; removed_files?: number }>("cache_clear")
                    .then((r) => {
                      setBusyMsg(
                        t("s.cacheClearDone", {
                          v0: r.freed_mb ?? "0",
                          v1: r.removed_files ?? 0,
                        }),
                      );
                      setCacheMb("0");
                    })
                    .catch((e) => setBusyMsg(t("s.cacheClearFail", { v0: String(e) })));
                }}
              >
                {t("s.cacheClear")}
              </Btn>
            }
          />
          <ListItem
            title={t("s.91e6c9b862")}
            desc={legacyMsg.panel || t("s.bc94a9c280")}
            right={
              <Btn onClick={() => void openLegacy("panel")}>{t("s.65fc81e161")}</Btn>
            }
          />
          <ListItem
            title={t("s.a636b86646")}
            desc={legacyMsg.webui || t("s.bc94a9c280")}
            right={<Btn onClick={() => void openLegacy("webui")}>{t("s.65fc81e161")}</Btn>}
          />
          {/* 「申请专业优化」暂时隐藏（服务还没开）。后端 consult_build 保留，
              开放时把 SHOW_CONSULT 改成 true 就行，不要删代码。 */}
          {SHOW_CONSULT ? (
            <ListItem
              title={t("s.dd41f552d6")}
              desc={busyMsg.startsWith(t("s.1a2edaedf8")) ? busyMsg : t("s.db1fdebf6f")}
              right={
                <Btn onClick={() => void run(t("s.1a2edaedf8"), "consult_build", { note: "" })}>{t("s.1a2edaedf8")}</Btn>
              }
            />
          ) : null}
          <ListItem
            title={t("s.e327258774")}
            desc={t("s.5258b304cc")}
            right={
              <Btn
                onClick={() => {
                  void onForceKill?.();
                }}
              >{t("s.76b9880829")}</Btn>
            }
          />
        </Group>
      </Block>
      <Block title={t("s.2bd28fc9c2")}>
        <Group>
          {allLinks().map((l) => (
            <ListItem
              key={l.url}
              title={l.title}
              desc={l.desc}
              right={
                l.qr ? (
                  <Btn onClick={() => setQr({ src: l.qr!, label: l.title })}>
                    {t("social.qr")}
                  </Btn>
                ) : (
                  <Btn onClick={() => void openExternal(l.url)}>{t("s.65fc81e161")}</Btn>
                )
              }
            />
          ))}
        </Group>
      </Block>
      {qr ? (
        <QrDialog src={qr.src} label={qr.label} onClose={() => setQr(null)} />
      ) : null}
    </PagePad>
  );
}
