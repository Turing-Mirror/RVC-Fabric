import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Block, Btn, Group, ListItem, PageHead, PagePad } from "../components/ui";

export function HelpPage() {
  // Installing the driver needs UAC, so it can only ever be user-initiated.
  // Without this entry the pack is downloaded but never actually installed.
  const [vbReady, setVbReady] = useState<boolean | null>(null);
  const [vbMsg, setVbMsg] = useState("");

  const refreshVb = async () => {
    try {
      const st = await invoke<{ vbcable_pack_ready?: boolean }>("assets_status");
      setVbReady(!!st.vbcable_pack_ready);
    } catch {
      setVbReady(null);
    }
  };
  useEffect(() => {
    void refreshVb();
  }, []);

  const installVb = async () => {
    setVbMsg("");
    try {
      if (!vbReady) {
        setVbMsg("正在下载安装包…");
        await invoke("assets_ensure_vbcable");
        await refreshVb();
      }
      setVbMsg("已启动官方安装程序，请在弹出的窗口里确认（需要管理员权限）");
      await invoke("assets_install_vbcable");
    } catch (e) {
      setVbMsg(`失败：${String(e)}`);
    }
  };

  return (
    <PagePad>
      <PageHead title="说明" sub="虚拟声卡连接与常见情况" />

      <Block title="安装虚拟声卡">
        <p className="text-[12.5px] text-[var(--help)] leading-relaxed m-0 mb-4 max-w-[74ch]">
          想让游戏 / QQ 里的人听到变声，必须先装虚拟声卡（VB-Cable）。
          装完重启一次电脑，设备列表里才会出现 CABLE Input / CABLE Output。
        </p>
        <Group>
          <ListItem
            title="VB-Cable"
            desc={
              vbMsg ||
              (vbReady === null
                ? "正在检查…"
                : vbReady
                  ? "安装包已就绪，点右侧开始安装（会弹管理员确认）"
                  : "尚未下载安装包，点右侧会先下载再安装")
            }
            right={<Btn onClick={() => void installVb()}>安装虚拟声卡</Btn>}
          />
        </Group>
      </Block>

      <Block title="虚拟声卡怎么连">
        <Group>
          <ListItem
            title="软件输入"
            desc="选你真实的麦克风"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">麦克风</span>}
          />
          <ListItem
            title="软件输出"
            desc="选 CABLE Input，游戏里才收得到"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">CABLE Input</span>}
          />
          <ListItem
            title="监听（可选）"
            desc="耳机，只有你自己听得到"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">耳机</span>}
          />
          <ListItem
            title="游戏 / QQ 麦克风"
            desc="选 CABLE Output"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">CABLE Output</span>}
          />
          <ListItem
            title="Windows 默认播放"
            desc="保持耳机，不要选 CABLE"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">耳机</span>}
          />
        </Group>
      </Block>
      <Block title="常见情况" note="4">
        <Group>
          <ListItem
            clickable
            title="对方说听不到我"
            desc="先看游戏里的麦克风是不是选成了 CABLE Output"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">展开</span>}
          />
          <ListItem
            clickable
            title="我自己听不到变声"
            desc="在设置里勾「变声时监听自己」，选你的耳机"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">展开</span>}
          />
          <ListItem
            clickable
            title="声音断断续续"
            desc="把响应阈值调低，或把采样块时长调大"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">展开</span>}
          />
          <ListItem
            clickable
            title="实体声卡怎么连"
            desc="USB 直播声卡 / 调音台的接法"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">展开</span>}
          />
        </Group>
      </Block>
    </PagePad>
  );
}
