import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Block, Btn, Group, ListItem, PageHead, PagePad } from "../components/ui";
import { SeparateDialog } from "../components/SeparateDialog";
import { TrainDialog } from "../components/TrainDialog";
import { ExtrasDialog } from "../components/ExtrasDialog";
import { openExternal } from "../lib/plaza";
import { tip } from "../lib/glossary";
import { statusTitle } from "../lib/engine";
import type { EngineStatus, ProvisionStatus } from "../lib/engine";

/** 「申请专业优化」的开关。服务还没开放，先藏起来；后端命令仍然在。 */
const SHOW_CONSULT = false;

type Props = {
  status?: EngineStatus;
  provision?: ProvisionStatus;
  onForceKill?: () => void | Promise<void>;
  onCheckUpdate?: () => void;
  updateLine?: string;
  onOpenProvision?: () => void;
};

/**
 * Repos and socials. Plain list rows, opened in the user's own browser through
 * the shell's http/https-only `open_external`. `desc` carries the account's own
 * identifier and nothing else.
 */
const LINKS: { title: string; desc?: string; url: string }[] = [
  {
    title: "GitHub 源码",
    desc: "Turing-Mirror/RVC-Fabric",
    url: "https://github.com/Turing-Mirror/RVC-Fabric",
  },
  {
    title: "CNB 发布与制品",
    desc: "Turing-Mirror/RVC-Fabric-Releases",
    url: "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases",
  },
  {
    title: "哔哩哔哩 @图灵镜",
    url: "https://space.bilibili.com/3546871148579062",
  },
  {
    title: "抖音 @图灵镜",
    desc: "抖音号 TuringMirror",
    url: "https://v.douyin.com/6NxXcrKK9cc",
  },
  {
    title: "小红书 @图灵镜",
    desc: "小红书号 TuringMirror",
    url: "https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094",
  },
];

export function MorePage({
  status,
  provision,
  onForceKill,
  onOpenProvision,
  onCheckUpdate,
  updateLine,
}: Props = {}) {
  // Where the UI itself is served from. Surfaced so a UI patch that did not
  // take effect is diagnosable instead of invisible (OTA strategy A).
  const [uiSource, setUiSource] = useState("—");
  const [sepOpen, setSepOpen] = useState(false);
  const [trainOpen, setTrainOpen] = useState(false);
  const [extrasOpen, setExtrasOpen] = useState(false);
  // Where the app thinks it is installed. The row below used to only describe
  // that this is resolved automatically, without ever showing the answer —
  // which is the first thing worth knowing when a report says "找不到 Runtime".
  const [root, setRoot] = useState("—");
  const [logFile, setLogFile] = useState("");
  const [version, setVersion] = useState("—");
  const [busyMsg, setBusyMsg] = useState("");

  // Both of these are 20–40s cold starts (torch/CUDA). Say so on the row
  // itself; a button that looks like it did nothing gets clicked again.
  const [legacyMsg, setLegacyMsg] = useState<{ panel?: string; webui?: string }>({});
  const openLegacy = async (which: "panel" | "webui") => {
    setLegacyMsg((m) => ({ ...m, [which]: "正在启动…" }));
    try {
      const r = await invoke<{ message?: string; url?: string }>(
        which === "panel" ? "legacy_open_panel" : "legacy_open_webui",
      );
      setLegacyMsg((m) => ({ ...m, [which]: r?.message || "已启动" }));
      if (which === "webui" && r?.url) {
        // Gradio needs a few seconds to bind the port; opening immediately
        // lands on a connection-refused page.
        setTimeout(() => {
          void invoke("open_external", { url: r.url }).catch(() => {});
        }, 4000);
      }
    } catch (e) {
      setLegacyMsg((m) => ({ ...m, [which]: `启动失败：${String(e)}` }));
    }
  };

  const run = async (label: string, cmd: string, args?: Record<string, unknown>) => {
    setBusyMsg(`${label}…`);
    try {
      const r = await invoke<{ path?: string }>(cmd, args);
      setBusyMsg(`${label}完成：${r?.path ?? ""}`);
    } catch (e) {
      setBusyMsg(`${label}失败：${String(e)}`);
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
    return () => {
      alive = false;
    };
  }, []);

  const delay = Number(status?.delay_ms || 0);
  const infer = Number(status?.infer_ms || 0);
  const latency =
    status?.state === "running"
      ? `${delay} ms（推理 ${infer} ms）`
      : status?.worker_alive
        ? "待命"
        : "—";

  const gpus = provision?.gpus?.length
    ? provision.gpus.join(" · ")
    : "未检测";
  const runtimeLine = provision?.runtime_ready
    ? provision.installed_variant
      ? `已就绪 · ${provision.installed_variant}`
      : "已就绪"
    : "未就绪（需补全）";

  return (
    <PagePad>
      <PageHead title="其他" sub="状态与维护" />
      <Block title="运行状态">
        <Group>
          <ListItem
            title="RVC Fabric 版本"
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)]">{version}</span>
            }
          />
          <ListItem
            title="产品根目录"
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
            title="界面来源"
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
            title="运行时"
            titleTip={tip("运行时")}
            desc={
              provision?.recommend_reason ||
              (status?.product_root ? String(status.product_root) : "产品根目录自动解析")
            }
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)]">{runtimeLine}</span>
            }
          />
          <ListItem
            title="显卡（系统枚举）"
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)] max-w-[220px] text-right truncate" title={gpus}>
                {gpus}
              </span>
            }
          />
          <ListItem
            title="推荐运行时"
            desc={
              provision?.download_supported
                ? provision.need_provision
                  ? "可在软件内下载补全"
                  : "已就绪；可强制重装"
                : "请用启动器补全"
            }
            right={
              <span className="flex items-center gap-2">
                <span className="text-[13.5px] text-[var(--ink-muted)]">
                  {provision?.recommended_variant || "—"}
                </span>
                {onOpenProvision ? (
                  <Btn onClick={onOpenProvision}>
                    {provision?.need_provision ? "补全…" : "重装…"}
                  </Btn>
                ) : null}
              </span>
            }
          />
          <ListItem
            title="引擎状态"
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)]">
                {status ? statusTitle(status) : "—"}
                {status?.pid ? ` · pid ${status.pid}` : ""}
              </span>
            }
          />
          <ListItem
            title="往返延迟"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">{latency}</span>}
          />
        </Group>
      </Block>
      <Block title="音频工具">
        <Group>
          <ListItem
            title="人声分离"
            desc="把歌曲拆成人声和伴奏，训练音色前用它清掉背景音乐或噪音"
            right={<Btn onClick={() => setSepOpen(true)}>打开</Btn>}
          />
          <ListItem
            title="训练音色"
            desc="用一个人的干声素材训一个新音色。需要 N 卡，可能需要几小时，由硬件配置决定。"
            right={<Btn onClick={() => setTrainOpen(true)}>打开</Btn>}
          />
          <ListItem
            title="下载模型"
            desc="分离模型与训练底模，按需下载"
            right={<Btn onClick={() => setExtrasOpen(true)}>打开</Btn>}
          />
        </Group>
      </Block>
      <SeparateDialog open={sepOpen} onClose={() => setSepOpen(false)} />
      <TrainDialog open={trainOpen} onClose={() => setTrainOpen(false)} />
      <ExtrasDialog
        open={extrasOpen}
        onClose={() => setExtrasOpen(false)}
        title="下载模型"
      />

      <Block title="维护">
        <Group>
          <ListItem
            title="生成诊断包"
            desc={busyMsg.startsWith("生成诊断包") ? busyMsg : "进行一次约一分钟的性能测试，打包日志、机型信息与当前设置"}
            right={
              <Btn onClick={() => void run("生成诊断包", "diagnostics_build")}>生成</Btn>
            }
          />
          <ListItem
            title="检查更新"
            desc={updateLine || "检查是否有新版本"}
            right={<Btn onClick={onCheckUpdate}>检查</Btn>}
          />
          <ListItem
            title="打开性能报告文件夹"
            right={
              <Btn onClick={() => void invoke("reveal_user_dir", { name: "perf_reports" })}>
                打开
              </Btn>
            }
          />
          <ListItem
            title="打开日志"
            desc={logFile || undefined}
            right={
              <Btn onClick={() => void invoke("reveal_user_dir", { name: "logs" })}>
                打开
              </Btn>
            }
          />
          <ListItem
            title="打开原版实时面板"
            desc={legacyMsg.panel || "高级功能，一般不用"}
            right={
              <Btn onClick={() => void openLegacy("panel")}>打开</Btn>
            }
          />
          <ListItem
            title="打开原版 WebUI"
            desc={legacyMsg.webui || "高级功能，一般不用"}
            right={<Btn onClick={() => void openLegacy("webui")}>打开</Btn>}
          />
          {/* 「申请专业优化」暂时隐藏（服务还没开）。后端 consult_build 保留，
              开放时把 SHOW_CONSULT 改成 true 就行，不要删代码。 */}
          {SHOW_CONSULT ? (
            <ListItem
              title="申请专业优化"
              desc={busyMsg.startsWith("生成咨询包") ? busyMsg : "打包当前音色的配置与档案，我们做针对性调参（不含模型文件）"}
              right={
                <Btn onClick={() => void run("生成咨询包", "consult_build", { note: "" })}>
                  生成咨询包
                </Btn>
              }
            />
          ) : null}
          <ListItem
            title="强制结束变声引擎"
            desc="解决卡死"
            right={
              <Btn
                onClick={() => {
                  void onForceKill?.();
                }}
              >
                结束
              </Btn>
            }
          />
        </Group>
      </Block>
      <Block title="仓库与社媒">
        <Group>
          {LINKS.map((l) => (
            <ListItem
              key={l.title}
              title={l.title}
              desc={l.desc}
              right={<Btn onClick={() => void openExternal(l.url)}>打开</Btn>}
            />
          ))}
        </Group>
      </Block>
    </PagePad>
  );
}
