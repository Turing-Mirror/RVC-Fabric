import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import { Field, Toggle } from "./controls";
import { Select } from "./Select";
import { MicTest } from "./MicTest";
import { Modal } from "./Modal";
import { t } from "../i18n/t";
import { useI18n } from "../i18n";
import { useConfig } from "../hooks/useConfig";
import { setConfig } from "../lib/config";
import { assessDevices } from "../lib/deviceSetup";
import { buildRoutes, detectRoutes, deviceNames, useVbCable } from "../lib/routes";
import { formatLocalizedList } from "../lib/voiceDisplay";
import type { PageId } from "../lib/nav";

/**
 * 新手引导：运行时装好之后，从这里一步步走到「对方听得见」。
 *
 * 与运行时的弹窗是同一种样子：一次只做一件事，做完了点下一步。每一步的完成与否
 * 按真实状态判断（装没装声卡、选没选音色、变声开没开），不靠用户自己勾。
 * 需要去别的页面办的事（下载音色）先把引导收成右下角的一个小按钮，办完点它回来。
 * 说明页里的「第一次变声」是同一条路径的文字版，从那里也能再打开引导。
 */

export type GuideStep = "cable" | "voice" | "devices" | "try" | "share";
export const GUIDE_STEPS: GuideStep[] = ["cable", "voice", "devices", "try", "share"];

/** 各步是否已完成。取自 onboarding_status 与引擎状态。 */
type Done = Partial<Record<GuideStep, boolean>>;

type Props = {
  open: boolean;
  step: GuideStep;
  onStep: (s: GuideStep) => void;
  /** 收起成小按钮，稍后继续。 */
  onMinimize: () => void;
  /** 走完了，或用户明确不要了。 */
  onFinish: () => void;
  /** 引擎报的设备列表与状态，和设置页、说明页同一份。 */
  status?: Record<string, unknown>;
  workerAlive: boolean;
  devicesBusy: boolean;
  onReloadDevices: () => void;
  running: boolean;
  starting: boolean;
  micDb?: number;
  onToggleRun: () => void;
  onNavigate: (page: PageId) => void;
};

export function SetupGuide(props: Props) {
  const { open, step, onStep, onMinimize, onFinish } = props;
  const { locale } = useI18n();
  const [done, setDone] = useState<Done>({});
  // 换步的方向：往后翻从右边进，往前翻从左边进
  const [dir, setDir] = useState<1 | -1>(1);
  const index = GUIDE_STEPS.indexOf(step);

  // 状态每两秒读一次：装声卡、下音色都是在别处完成的，回来时这里要已经知道
  useEffect(() => {
    if (!open) return;
    let alive = true;
    const read = () =>
      void invoke<{ voice?: boolean; cable?: boolean; convert?: boolean }>("onboarding_status")
        .then((s) => alive && setDone((d) => ({ ...d, cable: !!s.cable, voice: !!s.voice, try: !!s.convert })))
        .catch(() => {});
    read();
    const id = window.setInterval(read, 2000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [open]);

  const go = (to: number) => {
    const next = GUIDE_STEPS[Math.max(0, Math.min(GUIDE_STEPS.length - 1, to))];
    setDir(to > index ? 1 : -1);
    onStep(next);
  };
  const last = index === GUIDE_STEPS.length - 1;
  const labels = useMemo(
    () => GUIDE_STEPS.map((s) => t(`s.guide.${s}.title`)),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 随语言重算
    [locale],
  );

  return (
    <Modal open={open} z={60}>
      <div className="guide-panel w-full max-w-[600px] rounded-[var(--r)] bg-[var(--surface)] shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] p-7">
        <div className="flex items-baseline gap-3">
          <h2 className="text-[22px] font-semibold m-0">{t("s.guide.title")}</h2>
          <span className="text-[12.5px] text-[var(--meta)]">{t("s.guide.count", { v0: index + 1, v1: GUIDE_STEPS.length })}</span>
          <button
            type="button"
            onClick={onMinimize}
            className="ml-auto border-0 bg-transparent p-0 text-[12.5px] text-[var(--meta)] hover:text-[var(--ink)] cursor-pointer"
          >
            {t("s.guide.later")}
          </button>
        </div>

        {/* 五段进度。完成的一段是实心，当前一段的底色随换步滑过去 */}
        <div className="relative mt-5 grid gap-1.5" style={{ gridTemplateColumns: `repeat(${GUIDE_STEPS.length}, minmax(0, 1fr))` }}>
          {GUIDE_STEPS.map((s, i) => (
            <button
              key={s}
              type="button"
              onClick={() => go(i)}
              className="group border-0 bg-transparent p-0 text-left cursor-pointer"
              aria-current={i === index ? "step" : undefined}
            >
              <span className="block h-1 rounded-full overflow-hidden bg-[color-mix(in_srgb,var(--ink)_8%,transparent)]">
                <span
                  className="block h-full rounded-full bg-[var(--accent)] origin-left transition-transform duration-500 ease-[var(--ease)]"
                  style={{ transform: `scaleX(${done[s] ? 1 : i === index ? 0.5 : i < index ? 1 : 0})`, opacity: done[s] || i <= index ? 1 : 0 }}
                />
              </span>
              <span className={`block mt-2 text-[11.5px] truncate transition-colors ${i === index ? "text-[var(--ink)] font-medium" : "text-[var(--meta)] group-hover:text-[var(--ink-muted)]"}`}>
                {labels[i]}
                {done[s] ? <span className="ml-1 text-[var(--accent)]">✓</span> : null}
              </span>
            </button>
          ))}
        </div>

        <div className="relative mt-6 min-h-[248px]">
          <div key={step} className="guide-step" style={{ "--dir": dir } as CSSProperties}>
            {step === "cable" ? <CableStep status={props.status} /> : null}
            {step === "voice" ? <VoiceStep done={!!done.voice} onNavigate={(p) => { onMinimize(); props.onNavigate(p); }} /> : null}
            {step === "devices" ? <DevicesStep {...props} /> : null}
            {step === "try" ? <TryStep {...props} /> : null}
            {step === "share" ? <ShareStep /> : null}
          </div>
        </div>

        <div className="mt-7 flex items-center gap-2">
          {index > 0 ? <Btn onClick={() => go(index - 1)}>{t("s.guide.prev")}</Btn> : null}
          <span className="flex-1" />
          {!last && !done[step] ? <Btn onClick={() => go(index + 1)}>{t("s.guide.skip")}</Btn> : null}
          {last ? (
            <Btn primary onClick={onFinish}>{t("s.guide.finish")}</Btn>
          ) : (
            <Btn primary={Boolean(done[step]) || step === "devices"} onClick={() => go(index + 1)}>{t("s.guide.next")}</Btn>
          )}
        </div>
      </div>
    </Modal>
  );
}

function Lead({ children }: { children: ReactNode }) {
  return <p className="text-[13px] text-[var(--help)] m-0 mb-5 leading-relaxed">{children}</p>;
}

function Title({ children }: { children: ReactNode }) {
  return <div className="text-[16px] font-semibold mb-2">{children}</div>;
}

/** 第一步：虚拟声卡。已有别的虚拟声卡时直接说明，不劝人再装一套。 */
function CableStep({ status }: { status?: Record<string, unknown> }) {
  const { locale } = useI18n();
  const vb = useVbCable();
  const names = useMemo(() => [...deviceNames(status?.input_devices), ...deviceNames(status?.output_devices)], [status?.input_devices, status?.output_devices]);
  const routes = useMemo(buildRoutes, [locale]);
  const virtual = detectRoutes(names, routes).filter((r) => r.kind === "virtual");
  const has = virtual.length > 0 || vb.installed;
  return (
    <div>
      <Title>{t("s.guide.cable.title")}</Title>
      <Lead>{t("s.guide.cable.body")}</Lead>
      {has ? (
        <div className="text-[13px] text-[var(--ink)]">
          {virtual.length ? t("s.guide.cable.found", { v0: formatLocalizedList(virtual.map((r) => r.label)) }) : t("s.guide.cable.installed")}
        </div>
      ) : (
        <div className="flex items-center gap-3 flex-wrap">
          <Btn primary disabled={!!vb.busy} onClick={() => void vb.install()}>
            {vb.busy === "install" ? t("s.1cac8ac7f5") : t("s.b386a7fb53")}
          </Btn>
          {vb.msg ? <span className="text-[12.5px] text-[var(--help)]">{vb.msg}</span> : null}
        </div>
      )}
      <p className="text-[12.5px] text-[var(--meta)] m-0 mt-5 leading-relaxed">{t("s.guide.cable.restart")}</p>
    </div>
  );
}

/** 第二步：音色。下载与导入在别的页面，去之前先把引导收起来。 */
function VoiceStep({ done, onNavigate }: { done: boolean; onNavigate: (p: PageId) => void }) {
  return (
    <div>
      <Title>{t("s.guide.voice.title")}</Title>
      <Lead>{t("s.guide.voice.body")}</Lead>
      {done ? <div className="mb-4 text-[13px] text-[var(--ink)]">{t("s.guide.voice.done")}</div> : null}
      <div className="flex items-center gap-2 flex-wrap">
        <Btn primary={!done} onClick={() => onNavigate("plaza")}>{t("s.guide.voice.plaza")}</Btn>
        <Btn onClick={() => onNavigate("models")}>{t("s.guide.voice.import")}</Btn>
        <Btn onClick={() => onNavigate("home")}>{t("s.guide.voice.dsp")}</Btn>
      </div>
    </div>
  );
}

function options(list: unknown): { id: string; label: string }[] {
  return deviceNames(list).map((n) => ({ id: n, label: n }));
}

/** 第三步：输入、输出与监听。设备列表要等引擎读出来；能自动配的一键配好。 */
function DevicesStep({ status, workerAlive, devicesBusy, onReloadDevices }: Props) {
  const c = useConfig();
  const [msg, setMsg] = useState("");
  const inputs = options(status?.input_devices);
  const outputs = options(status?.output_devices);
  const ready = inputs.length > 0 || outputs.length > 0;
  const auto = async () => {
    const advice = assessDevices(c.cfg, status ?? {});
    if (advice.patch) await setConfig(advice.patch);
    setMsg(advice.reasons.map((k) => t(k)).join(" "));
  };
  return (
    <div>
      <Title>{t("s.guide.devices.title")}</Title>
      <Lead>{t("s.guide.devices.body")}</Lead>
      {ready ? (
        <div className="flex flex-col gap-4">
          <Field label={t("s.c15e33676a")} control={<Select full value={c.str("sg_input_device")} options={inputs} onChange={(v) => c.set("sg_input_device", v, true)} />} />
          <Field label={t("s.3aa83c304c")} control={<Select full value={c.str("sg_output_device")} options={outputs} onChange={(v) => c.set("sg_output_device", v, true)} />} />
          <Toggle label={t("s.dcf690b953")} checked={c.bool("monitor_self")} onChange={(v) => c.set("monitor_self", v, true)} />
          {c.bool("monitor_self") ? (
            <Field label={t("s.550c08627b")} control={<Select full value={c.str("monitor_device")} options={outputs} onChange={(v) => c.set("monitor_device", v, true)} />} />
          ) : null}
          <div className="flex items-center gap-2 flex-wrap">
            <Btn onClick={() => void auto()}>{t("s.devAutoBtn")}</Btn>
            {msg ? <span className="text-[12.5px] text-[var(--help)]">{msg}</span> : null}
          </div>
          <MicTest deviceReady={ready} />
        </div>
      ) : (
        <div className="flex items-center gap-3 flex-wrap text-[12.5px] text-[var(--help)]">
          <span>{devicesBusy ? t("s.abd52d0c37") : workerAlive ? t("s.1831f7eb53") : t("s.guide.devices.load")}</span>
          <Btn disabled={devicesBusy} onClick={onReloadDevices}>{devicesBusy ? t("s.f950213ab7") : t("s.966b701690")}</Btn>
        </div>
      )}
    </div>
  );
}

/** 第四步：开一次变声，看电平、听监听。 */
function TryStep({ running, starting, micDb, onToggleRun }: Props) {
  const level = micDb === undefined ? 0 : Math.max(0, Math.min(1, (micDb + 60) / 60));
  return (
    <div>
      <Title>{t("s.guide.try.title")}</Title>
      <Lead>{t("s.guide.try.body")}</Lead>
      <div className="flex items-center gap-4">
        <Btn primary={!running} busy={starting} onClick={onToggleRun}>
          {running ? t("s.guide.try.stop") : t("s.guide.try.start")}
        </Btn>
        <div className="flex-1 min-w-0">
          <div className="text-[12px] text-[var(--meta)] mb-1.5">{running ? t("s.guide.try.running") : t("s.guide.try.level")}</div>
          <div className="h-1.5 rounded-full overflow-hidden bg-[color-mix(in_srgb,var(--ink)_8%,transparent)]">
            <div className="h-full rounded-full bg-[var(--accent)] origin-left transition-transform duration-150" style={{ transform: `scaleX(${running ? level : 0})` }} />
          </div>
        </div>
      </div>
    </div>
  );
}

/** 第五步：在对方的软件里把麦克风改成 CABLE Output。 */
function ShareStep() {
  const rows: [string, string][] = [
    [t("s.guide.share.qqName"), t("s.guide.share.qq")],
    ["Discord", t("s.guide.share.discord")],
    ["OBS", t("s.guide.share.obs")],
    [t("s.guide.share.gameName"), t("s.guide.share.game")],
  ];
  return (
    <div>
      <Title>{t("s.guide.share.title")}</Title>
      <Lead>{t("s.guide.share.body")}</Lead>
      <div className="flex flex-col gap-2.5">
        {rows.map(([name, path]) => (
          <div key={name} className="flex items-baseline gap-4 text-[13px]">
            <span className="w-[92px] flex-none text-[var(--ink)]">{name}</span>
            <span className="text-[var(--ink-muted)]">{path}</span>
          </div>
        ))}
      </div>
      <p className="text-[12.5px] text-[var(--meta)] m-0 mt-5 leading-relaxed">{t("s.guide.share.check")}</p>
    </div>
  );
}

/** 收起后留在右下角的小按钮：点它回到引导的那一步。 */
export function GuidePill({ step, onOpen, onClose }: { step: GuideStep; onOpen: () => void; onClose: () => void }) {
  return (
    <div className="guide-pill fixed right-5 bottom-[92px] z-[40] flex items-center rounded-full bg-[var(--surface)] shadow-[0_8px_24px_-10px_rgba(20,26,33,.35),inset_0_0_0_1px_var(--hairline)]">
      <button type="button" onClick={onOpen} className="h-10 pl-4 pr-2 border-0 bg-transparent cursor-pointer text-[13px] text-[var(--ink)]">
        {t("s.guide.resume")}
        <span className="ml-2 text-[12px] text-[var(--meta)]">{t("s.guide.count", { v0: GUIDE_STEPS.indexOf(step) + 1, v1: GUIDE_STEPS.length })}</span>
      </button>
      <button type="button" onClick={onClose} aria-label={t("s.guide.close")} title={t("s.guide.close")} className="h-10 w-9 grid place-items-center border-0 bg-transparent cursor-pointer text-[var(--meta)] hover:text-[var(--ink)] rounded-full">
        ×
      </button>
    </div>
  );
}
