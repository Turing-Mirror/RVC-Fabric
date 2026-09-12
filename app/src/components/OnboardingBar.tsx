import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { PageId } from "../lib/nav";
import { t } from "../i18n/t";/**
 * 新手进度：一行五段，告诉新用户「走到哪了、下一步是什么」。
 *
 * 三条设计约束（都是跟用户约定过的）：
 * 1. 每段按**真实事件**自动点亮，不由用户手点 —— 运行时就绪、选了音色、
 *    虚拟声卡在位是实时推导的；「首次变声」「开启过监听」由 App 在事件
 *    发生时落盘（onboard_convert / onboard_monitor），跨重启存活。
 * 2. 「不再显示」永久关闭，写配置；全绿后只显示一次「已完成」就收起。
 * 3. 平铺在首页横幅下方，不是弹窗、不拦任何操作。
 */
type Status = {
  runtime: boolean;
  voice: boolean;
  cable: boolean;
  convert: boolean;
  monitor: boolean;
  dismissed: boolean;
};

type Step = {
  id: keyof Omit<Status, "dismissed">;
  label: string;
  page: PageId;
  /** Help-page anchor for steps that need a precise landing point. */
  focus?: string;
};

export function OnboardingBar({
  tick,
  onDismissed,
  onNavigate,
}: {
  /** App 在历史事件落盘/关闭时 +1，触发重读。 */
  tick: number;
  onDismissed?: () => void;
  /** 点某一段时跳到对应页面；说明页可以同时接收区块锚点。 */
  onNavigate: (page: PageId, focus?: string) => void;
}) {
  const [st, setSt] = useState<Status | null>(null);
  const [hidden, setHidden] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await invoke<Status>("onboarding_status");
      setSt(s);
      if (s.dismissed) setHidden(true);
    } catch {
      /* 浏览器预览没有 shell：整条不出 */
    }
  }, []);

  useEffect(() => {
    void load();
    // 配置也可能被别的窗口改动；轻量轮询兜底（30 秒一次，代价可忽略）。
    const id = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(id);
  }, [load, tick]);

  const dismiss = async () => {
    setHidden(true);
    onDismissed?.();
    try {
      await invoke("config_set", { patch: { onboard_dismiss: true } });
    } catch {
      /* 写不进就本次会话内隐藏 */
    }
  };

  if (!st || hidden) return null;

  const steps: Step[] = [
    { id: "runtime", label: t("s.obRuntime"), page: "more" },
    { id: "voice", label: t("s.obVoice"), page: "models" },
    { id: "cable", label: t("s.obCable"), page: "help", focus: "vbcable" },
    { id: "convert", label: t("s.obConvert"), page: "home" },
    { id: "monitor", label: t("s.obMonitor"), page: "settings" },
  ];
  const doneCount = steps.filter((s) => st[s.id]).length;
  const allDone = doneCount === steps.length;

  // 跳转走 App 的统一导航回调。虚拟声卡这一步直达安装区块，避免用户
  // 进入说明页后还要在长页面里寻找安装按钮。
  const go = (step: Step) => onNavigate(step.page, step.focus);

  return (
    <div className="mx-[30px] mt-4 mb-1 rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] px-4 py-3 max-[1020px]:mx-[22px] max-[720px]:mx-4">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[12px] text-[var(--meta)] shrink-0">
          {allDone ? t("s.obDone") : t("s.obLead")}
        </span>
        <div className="flex items-center gap-1.5 flex-wrap flex-1 min-w-0">
          {steps.map((s, i) => (
            <span key={s.id} className="flex items-center gap-1.5">
              {i > 0 ? (
                <span aria-hidden className="text-[var(--meta)] text-[11px]">
                  →
                </span>
              ) : null}
              <button
                type="button"
                onClick={() => go(s)}
                className={[
                  "border-0 cursor-pointer rounded-full px-2.5 py-1 text-[11.5px] leading-none",
                  st[s.id]
                    ? "bg-transparent text-[var(--meta)]"
                    : "bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] text-[var(--accent)] font-medium",
                ].join(" ")}
                title={t("s.obGoTo", { v0: s.label })}
              >
                {i + 1}. {s.label}
                {st[s.id] ? ` · ${t("s.obStepDone")}` : ""}
              </button>
            </span>
          ))}
        </div>
        {/* 关闭入口常驻：新手进度永远不能变成赶不走的东西。 */}
        <button
          type="button"
          onClick={() => void dismiss()}
          className="border-0 bg-transparent p-0 text-[11.5px] text-[var(--meta)] underline decoration-dotted underline-offset-2 cursor-pointer shrink-0"
        >
          {t("s.obDismiss")}
        </button>
      </div>
    </div>
  );
}
