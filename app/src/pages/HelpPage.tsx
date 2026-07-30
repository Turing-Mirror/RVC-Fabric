import { Block, Group, ListItem, PageHead, PagePad } from "../components/ui";

export function HelpPage() {
  return (
    <PagePad>
      <PageHead title="说明" sub="虚拟声卡连接与常见情况" />
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
