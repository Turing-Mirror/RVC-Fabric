import { Block, Btn, Group, ListItem, PageHead, PagePad } from "../components/ui";
import type { EngineStatus, ProvisionStatus } from "../lib/engine";

type Props = {
  status?: EngineStatus;
  provision?: ProvisionStatus;
  onForceKill?: () => void | Promise<void>;
};

export function MorePage({ status, provision, onForceKill }: Props = {}) {
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
            title="壳版本"
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)]">1.3.0 · Tauri</span>
            }
          />
          <ListItem
            title="Runtime"
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
            desc="不依赖 torch；用于推荐运行时分版"
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
                ? "可在壳内下载"
                : "下载能力尚未接入；请用启动器补全"
            }
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)]">
                {provision?.recommended_variant || "—"}
              </span>
            }
          />
          <ListItem
            title="引擎状态"
            right={
              <span className="text-[13.5px] text-[var(--ink-muted)]">
                {status?.state || "—"}
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
      <Block title="维护">
        <Group>
          <ListItem
            title="生成诊断包"
            desc="先跑一次约一分钟的性能测试，再把日志和机型信息打包"
            right={<Btn>生成</Btn>}
          />
          <ListItem
            title="检查更新"
            desc="尚未连接更新服务"
            right={<Btn>检查</Btn>}
          />
          <ListItem title="打开性能报告文件夹" right={<Btn>打开</Btn>} />
          <ListItem
            title="打开原版实时面板"
            desc="高级功能，一般用不到"
            right={<Btn>打开</Btn>}
          />
          <ListItem
            title="申请专业优化"
            desc="打包样本与档案，我们做针对性调参"
            right={<Btn>生成咨询包</Btn>}
          />
          <ListItem
            title="强制结束变声引擎"
            desc="卡住了才用"
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
    </PagePad>
  );
}
