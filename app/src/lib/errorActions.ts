/**
 * 错误码 → 一个能动手的按钮。
 *
 * 报错说清楚了「哪里不对」还不够。「缺少底模」这句话对着一个不知道底模在哪的
 * 用户，和「加载模型失败」没有本质区别 —— 他仍然只能来群里问一句「怎么办」。
 *
 * 这张表只登记**当前进程就能完成、且有明确成功反馈**的动作。做不到的宁可不
 * 登记：一个点下去什么都没发生的按钮，比没有按钮更伤。
 */
import { invoke } from "@tauri-apps/api/core";
import { openDownloadModels } from "./downloadModels";
import type { ExtrasFilter } from "../components/ExtrasDialog";
import { t } from "../i18n/t";

type Action = {
  /** 按钮文案的语言包 key。 */
  labelKey: string;
  run: () => void;
};

/** 去主窗口广场的下载区，带上分组筛选。工具窗里也管用（会把主窗口叫到前面）。 */
function toDownloads(reason: string, filter: ExtrasFilter): () => void {
  return () => openDownloadModels({ reason, filter });
}

/** 跳到说明页对应段。 */
function toHelp(section: string): () => void {
  return () => {
    void invoke("tools_open_help", { section }).catch(() => {});
  };
}

const CODE_ACTIONS: Record<string, Action> = {
  // 训练缺件：三样都住在广场的下载区。
  "train.pretrained_missing": {
    labelKey: "s.errActDownload",
    run: toDownloads("train.pretrained_missing", "train"),
  },
  "train.rmvpe_missing": {
    labelKey: "s.errActDownload",
    run: toDownloads("train.rmvpe_missing", "train"),
  },
  "train.mute_missing": {
    labelKey: "s.errActDownload",
    run: toDownloads("train.mute_missing", "train"),
  },
  // hubert 缺失/损坏走引擎资源入口（和 Runtime 同一页，不带筛选词）。
  "train.no_feature": {
    labelKey: "s.errActDownload",
    run: toDownloads("train.no_feature", "all"),
  },
  // 数据集体检不通过的三条：答案在说明页「训练音色」段，跳过去直接展开。
  "train.no_slices": {
    labelKey: "s.errActHelp",
    run: toHelp("train"),
  },
  "train.no_f0": {
    labelKey: "s.errActHelp",
    run: toHelp("train"),
  },
  "train.no_samples": {
    labelKey: "s.errActHelp",
    run: toHelp("train"),
  },
  // 运行时没装齐：同一个入口，不带筛选词。
  "runtime.not_ready": {
    labelKey: "s.errActRuntime",
    run: toDownloads("runtime.not_ready", "all"),
  },
  "runtime.missing_python": {
    labelKey: "s.errActRuntime",
    run: toDownloads("runtime.missing_python", "all"),
  },
  "engine.missing_gui": {
    labelKey: "s.errActRuntime",
    run: toDownloads("engine.missing_gui", "all"),
  },
  // 选到的是训练存档：得先在训练窗「进阶设置 → 模型提取」里转成音色。把训练
  // 窗开到用户眼前，比让他自己去猜「训练窗」在主界面哪个入口强。不走
  // ToolWindow 的 openTool —— 那个会先查引擎资源并可能弹下载框，而能碰上这个
  // 错的人显然已经有整套训练环境；也避免组件间的循环引用。
  "sts.model_is_archive": {
    labelKey: "s.errActExtract",
    run: () => {
      void invoke("tools_open", { kind: "train" }).catch(() => {});
    },
  },
};

/** 这个错误码有没有配一个能按的按钮。 */
export function actionFor(code: string | undefined | null): { label: string; run: () => void } | null {
  if (!code) return null;
  const a = CODE_ACTIONS[code];
  if (!a) return null;
  return { label: t(a.labelKey), run: a.run };
}

/** 测试用：表里登记了哪些码。 */
export function actionCodes(): string[] {
  return Object.keys(CODE_ACTIONS);
}
