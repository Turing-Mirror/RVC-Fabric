import { Btn } from "./ui";
import { openDownloadModels } from "../lib/downloadModels";
import { openHelpSection } from "../lib/helpNav";
import { t } from "../i18n/t";

/** 后端 selfcheck.rs 跑出来的一条结论。 */
export type Finding = {
  code: string;
  level: "error" | "warn" | "info";
  title: string;
  evidence: { file: string; line?: number; text: string }[];
};

function levelLabel(level: Finding["level"]): string {
  if (level === "error") return t("s.chkLevelError");
  if (level === "warn") return t("s.chkLevelWarn");
  return t("s.chkLevelInfo");
}

/**
 * 结论码 → 一个能按的按钮。
 *
 * 和 lib/errorActions 同一条原则：只登记当前进程就能完成、且有明确成功反馈的
 * 动作。剩下那些（选错了模型、上次训练被显存不足带走）没有一个按钮能代劳，
 * 给一个点了没用的按钮比不给更伤。
 */

/**
 * 结论码 → 说明页里真正回答它的那一段（甚至那一条）。
 *
 * 只在说明页确实写了这件事时才登记。指到「常见情况」那一整块没什么用 ——
 * 二十一条里找自己那条，跟没指一样；所以带上问题的 key，跳过去直接展开。
 */
const HELP_TARGET: Record<string, string> = {
  "engine.killed_by_system": "faq#s.faqAlreadyRunningQ",
  "train.out_of_memory": "faq#s.faqVramQ",
  "audio.underrun": "faq#s.ca98fe8db7",
  "audio.mme_high_delay": "faq#s.faqLatencyQ",
  // 训练这几条的答案在「训练音色」那一段里，不在常见情况。
  "model.training_snapshot": "train",
  "train.stage_mismatch": "train",
  "train.preprocess_failures": "train",
};

function actionFor(f: Finding): { label: string; run: () => void } | null {
  if (f.code === "assets.pretrained_partial") {
    return {
      label: t("s.errActDownload"),
      run: () => openDownloadModels({ filter: "train" }),
    };
  }
  const target = HELP_TARGET[f.code];
  if (target) {
    return { label: t("s.errActHelp"), run: () => openHelpSection(target) };
  }
  return null;
}

/**
 * 自检结论列表。
 *
 * 出包对话框和「其他」页的自助排查用同一份渲染 —— 用户在这两处看到的应当是
 * 同一句话，否则「我这边写的是另一句」会变成新的一轮问答。
 */
export function FindingList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) return null;
  return (
    <ul className="m-0 list-none p-0">
      {findings.map((f, i) => {
        const action = actionFor(f);
        return (
          <li key={f.code + i} className="relative py-2 first:pt-0">
            {i > 0 ? (
              <div
                aria-hidden
                className="absolute top-0 left-0 right-0 h-px bg-[var(--hairline)]"
              />
            ) : null}
            <div className="flex flex-wrap gap-2 items-baseline">
              {/* 等宽的级别标签，不靠颜色分级 —— 一片红黄看不出该先处理哪个。 */}
              <span className="font-mono text-[11px] text-[var(--meta)] shrink-0">
                {levelLabel(f.level)}
              </span>
              <span className="text-[12.5px] leading-relaxed flex-1 min-w-[180px]">
                {f.title}
              </span>
              {action ? <Btn onClick={action.run}>{action.label}</Btn> : null}
            </div>
            {f.evidence.map((e, j) => (
              <div
                key={j}
                className="mt-0.5 font-mono text-[11px] text-[var(--meta)] break-all"
              >
                {e.file}
                {e.line != null ? `:${e.line}` : ""} — {e.text}
              </div>
            ))}
          </li>
        );
      })}
    </ul>
  );
}
