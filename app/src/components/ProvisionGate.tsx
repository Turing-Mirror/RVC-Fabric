import { TransferProgress } from "trm-ui";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useEffect, useState } from "react";
import {
  cancelProvision,
  startProvision,
  type ProvisionProgress,
  type ProvisionStatus,
} from "../lib/engine";
import { getAssetsStatus } from "../lib/downloadModels";
import { useI18n } from "../i18n";
import { joinClauses } from "../lib/text";
import { ErrorNote } from "./ErrorNote";
import { MainGpuPicker, MAIN_GPU_AUTO, mainGpuTip } from "./MainGpuPicker";
import { Modal } from "./Modal";
import { Btn, HelpMark } from "./ui";

type Dependency = "core" | "vcredist" | "vbcable";

type Props = {
  open: boolean;
  initial?: ProvisionStatus;
  coreOnly?: boolean;
  onDone: () => void;
  onDismiss?: () => void;
};

function formatBytes(n: number): string {
  if (n >= 1e9) return (n / 1e9).toFixed(2) + " GB";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + " MB";
  if (n >= 1e3) return (n / 1e3).toFixed(0) + " KB";
  return Math.round(n) + " B";
}

function isCancelError(error: string, cancelled: string): boolean {
  return error.includes(cancelled) || error.toLowerCase().includes("cancel");
}

export function ProvisionGate({ open, initial, coreOnly = false, onDone, onDismiss }: Props) {
  const { t } = useI18n();
  const preferred = initial?.installed_variant || initial?.recommended_variant;
  const [variant, setVariant] = useState(preferred && preferred !== "unknown" ? preferred : "nvidia");
  const [runtimeComplete, setRuntimeComplete] = useState(false);
  const [pending, setPending] = useState<Dependency[]>([]);
  const [coreSize, setCoreSize] = useState(0);
  const [busy, setBusy] = useState(false);
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [pausing, setPausing] = useState(false);
  const [progress, setProgress] = useState<ProvisionProgress | null>(null);
  const [error, setError] = useState("");
  const [mainGpu, setMainGpu] = useState(MAIN_GPU_AUTO);

  useEffect(() => {
    if (!open) return;
    setVariant(preferred && preferred !== "unknown" ? preferred : "nvidia");
  }, [open, preferred]);

  useEffect(() => {
    if (!open) return;
    setRuntimeComplete(false);
    setRestartNeeded(false);
    setPending([]);
    setError("");
    setProgress(null);
    let disposed = false;
    if (coreOnly) {
      void getAssetsStatus().then(assets => {
        if (!disposed) setCoreSize(assets.engine_core_size_bytes ?? 0);
      });
    }
    void invoke<Record<string, unknown>>("config_get")
      .then(cfg => { if (!disposed) setMainGpu(Number(cfg.main_gpu ?? MAIN_GPU_AUTO)); })
      .catch(() => {});
    let unlisten: (() => void) | undefined;
    void listen<ProvisionProgress>("provision-progress", event => {
      setProgress(event.payload);
    }).then(un => {
      if (disposed) un();
      else unlisten = un;
    }).catch(() => {});
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [open, coreOnly]);

  const rows: NonNullable<ProvisionStatus["variants"]> = initial?.variants?.length ? initial.variants : [
    { id: "nvidia", label: t("s.4c65a5e25e") },
    { id: "nvidia50", label: t("s.e7a64d4aaf") },
    { id: "amd", label: t("s.variantAmd") },
  ];
  const variants = rows.map(row => ({ ...row, label: row.id === "nvidia" ? t("s.4c65a5e25e") : row.label }));
  const selected = variants.find(row => row.id === variant);
  const force = Boolean(selected?.active && selected.installed);
  const action = !selected?.installed ? "runtimeActions.download"
    : !force ? "runtimeActions.switch"
    : selected.update_available ? "runtimeActions.update"
    : "runtimeActions.redownload";

  const step = runtimeComplete
    ? (pending.length > 0 ? pending[0] : "done")
    : (coreOnly ? "core" : "runtime");
  const title = step === "runtime" ? t("s.405125fb37")
    : step === "core" ? t("extras.engineTitle")
    : step === "vcredist" ? t("s.vcrTitle")
    : step === "vbcable" ? t("s.3d4e683008")
    : t("s.f2e88c071e");

  function advance() {
    if (coreOnly) setRuntimeComplete(true);
    setPending(steps => steps.slice(1));
    setProgress(null);
    setError("");
  }

  async function start() {
    setBusy(true);
    setError("");
    setProgress(null);
    try {
      if (step === "runtime") {
        const result = await startProvision(variant, force);
        if (!result.ok) throw new Error(result.message || t("s.44c7946c76"));
        const [assets, vcrInstalled] = await Promise.all([
          getAssetsStatus(),
          invoke<boolean>("vcredist_installed").catch(() => true),
        ]);
        const next: Dependency[] = [];
        if (assets.engine_core_ready === false) next.push("core");
        if (!vcrInstalled) next.push("vcredist");
        if (assets.vbcable_installed === false) next.push("vbcable");
        setCoreSize(assets.engine_core_size_bytes ?? 0);
        setPending(next);
        setRuntimeComplete(true);
        setProgress(null);
      } else if (step === "core") {
        await invoke("assets_ensure_engine_core");
        advance();
      } else if (step === "vcredist" || step === "vbcable") {
        await invoke("assets_ensure_" + step);
        setProgress({ phase: "installing", done: 0, total: 0, percent: 0 });
        await invoke(step === "vcredist" ? "vcredist_install" : "assets_install_vbcable");
        if (step === "vbcable") setRestartNeeded(true);
        advance();
      }
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      if (step === "runtime" && isCancelError(message, t("s.a5ffdc95ee"))) {
        onDismiss?.();
      } else {
        setError(message);
      }
    } finally {
      setBusy(false);
      setPausing(false);
    }
  }

  async function pause() {
    setPausing(true);
    try {
      await cancelProvision();
    } catch (cause) {
      setError(String(cause));
      setPausing(false);
    }
  }

  const phase = progress?.phase ?? "";
  const done = progress?.done ?? 0;
  const total = progress?.total ?? 0;
  const retry = /^retry:(\d+)$/.exec(phase);
  const preparing = phase === "" || phase === "prepare" || phase === "catalog";
  const downloading = !preparing && !["verify", "extract", "installing", "done"].includes(phase);
  const canPause = step === "runtime" && (preparing || downloading);
  const message = pausing ? t("s.setupPausing")
    : retry ? t("s.dlReconnect", { v0: Number(retry[1]) })
    : phase === "verify" ? t("s.setupVerifying")
    : phase === "extract" ? t("s.setupInstalling")
    : phase === "installing" ? t(step === "vbcable" ? "s.vbcableInstalling" : "s.vcrInstalling")
    : preparing || phase.startsWith("connecting:") ? t("s.setupConnecting")
    : phase === "done" ? t("s.2105061e3e")
    : t("s.setupDownloading");

  if (!open) return <Modal open={false} />;
  return (
    <Modal z={50} contained>
      <div className="w-full max-w-[520px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_var(--scrim)] p-7">
        <h2 className="text-[22px] font-semibold m-0 mb-4">{title}</h2>
        {step === "runtime" && !busy ? (
          <>
            <div className="flex flex-col gap-2" role="group" aria-label={t("s.6a6564705b")}>
              {variants.map(row => {
                const active = row.id === variant;
                const size = row.size_label && row.size_label !== "0 B" ? row.size_label
                  : row.size_bytes ? formatBytes(row.size_bytes) : "";
                return (
                  <button
                    key={row.id}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setVariant(row.id)}
                    className={[
                      "text-left border-0 rounded-[var(--rs)] px-3.5 py-2.5 cursor-pointer text-[13.5px] transition-colors",
                      active
                        ? "bg-[var(--accent-soft)] text-[var(--ink)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--accent)_40%,transparent)]"
                        : "bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] text-[var(--ink-muted)]",
                    ].join(" ")}
                  >
                    <span className="inline-flex items-center flex-wrap gap-x-2 gap-y-0.5">
                      <span>{row.label}</span>
                      {initial?.recommended_variant === row.id ? (
                        <span className="text-[11.5px] text-[var(--accent-text)]">{t("s.62b46f24ae")}</span>
                      ) : null}
                      <span className="text-[11.5px] text-[var(--meta)]">
                        {row.installed ? joinClauses([
                          row.active ? t("runtimeMigration.active") : t("runtimeMigration.installed"),
                          row.installed_version ? t("s.metaVersion", { v0: row.installed_version }) : "",
                        ]) : size}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
            {(initial?.nvidia_gpus?.length ?? 0) > 1 && variant.startsWith("nvidia") ? (
              <div className="mt-4">
                <div className="text-[12.5px] text-[var(--meta)] mb-2 flex items-center gap-2">
                  {t("s.6b26feecc1")}<HelpMark title={mainGpuTip()} />
                </div>
                <MainGpuPicker
                  full
                  gpus={initial?.nvidia_gpus ?? []}
                  value={mainGpu}
                  onChange={value => {
                    setMainGpu(value);
                    void invoke("config_set", { patch: { main_gpu: value } }).catch(() => {});
                  }}
                />
              </div>
            ) : null}
          </>
        ) : null}
        {!busy && step === "core" ? (
          <p className="m-0 text-[13px] text-[var(--help)]">
            {t("s.provCoreAsk")}
            {coreSize > 0 ? t("s.e592773b6a", { v0: formatBytes(coreSize) }) : ""}
          </p>
        ) : null}
        {!busy && step === "vcredist" ? (
          <p className="m-0 text-[13px] text-[var(--help)]">{t("s.vcrNeeded")}</p>
        ) : null}
        {!busy && step === "vbcable" ? (
          <p className="m-0 text-[13px] text-[var(--help)]">{t("s.c946d45a63")}</p>
        ) : null}
        {step === "done" && restartNeeded ? (
          <p className="m-0 text-[13px] text-[var(--help)]">{t("s.vbcableDone")}</p>
        ) : null}
        {busy ? (
          <TransferProgress
            message={message}
            percent={total > 1 && phase !== "installing" ? Math.min(100, 100 * done / total) : undefined}
            speed={downloading && progress?.speed_bps ? progress.speed_label : undefined}
            detail={downloading && done > 0 ? (total > 1 ? formatBytes(done) + " / " + formatBytes(total) : formatBytes(done)) : undefined}
          />
        ) : null}
        {!busy && error ? <ErrorNote text={error} compact /> : null}
        <div className="flex items-center gap-2 justify-end mt-5">
          {busy ? (
            canPause ? <Btn onClick={() => void pause()} disabled={pausing}>{t("s.setupPause")}</Btn> : null
          ) : step === "done" ? (
            <Btn primary onClick={onDone}>{t("s.33246f6a5e")}</Btn>
          ) : (
            <>
              {step === "runtime" && onDismiss ? <Btn onClick={onDismiss}>{t("s.479fcc1cc0")}</Btn> : null}
              {step !== "runtime" ? <Btn onClick={advance}>{t("s.479fcc1cc0")}</Btn> : null}
              <Btn primary onClick={() => void start()}>
                {error ? t("s.setupRetry")
                  : step === "runtime" ? t(action)
                  : step === "core" ? t("s.provCoreGet")
                  : step === "vbcable" ? t("s.087db63ab1")
                  : t("s.vcrInstall")}
              </Btn>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
