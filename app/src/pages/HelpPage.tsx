import { useEffect, useState, memo } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Block, Btn, Group, ListItem, PageHead, PagePad } from "../components/ui";
import { GLOSSARY, tip } from "../lib/glossary";

/**
 * Answers carried over verbatim from the Tk shell's `help_content.py` and its
 * 「实体声卡连接」 dialog. The rows already said 「展开」; they just had nothing
 * behind them.
 */
const FAQ: { q: string; hint: string; a: string }[] = [
  {
    q: "对方说听不到我",
    hint: "若使用的是本软件提供的虚拟声卡，检查游戏里的麦克风是不是选成了 CABLE Output",
    a: [
      "· 游戏 / 语音 的麦克风要选 CABLE Output",
      "· 本软件的输出设备要选 CABLE Input",
      "· 确认已「开启变声」，并且模式是「变声」而非「原声」",
    ].join("\n"),
  },
  {
    q: "我自己听不到变声",
    hint: "在设置里勾「变声时监听自己」，选你的耳机",
    a: [
      "· 设置 → 勾选「变声时监听自己」",
      "· 监听设备选真实耳机，不要选 CABLE —— 选了 CABLE 就等于没监听",
    ].join("\n"),
  },
  {
    q: "声音断断续续",
    hint: "把响应阈值调低，或把采样块时长调大",
    a: [
      "· 把「采样长度」略调大（越大越稳，延迟也越高）",
      "· 关掉输入或输出降噪其中一项，降噪很吃显卡",
      "· 音高算法换 fcpe 试试",
      "· 关掉其他占用麦克风的软件",
      "· 确认装的是和自己显卡对应的运行时分版",
    ].join("\n"),
  },
  {
    q: "实体声卡怎么连",
    hint: "USB 直播声卡 / 调音台的接法",
    a: [
      "【麦克风走实体声卡】",
      "· 输入设备 = 实体声卡的录音设备（名字里带声卡型号）",
      "· 输出设备 = 仍然选 CABLE Input，对面听到变声还是靠虚拟声卡",
      "· 监听：耳机插在声卡上，监听设备选实体声卡的播放",
      "",
      "【声卡带「内录 / 立体声混音」通道】",
      "· 也可以不用 CABLE：输出设备 = 实体声卡的播放，",
      "  游戏 / 语音 的麦克风 = 声卡的内录通道（叫法以声卡说明书为准）",
      "",
      "【注意】",
      "· 先关掉声卡驱动自带的降噪 / 混响 / 变声，避免和本软件冲突",
      "· 列表里没设备：点「重载设备列表」或重启软件",
    ].join("\n"),
  },
  {
    q: "停不干净、声卡一直被占",
    hint: "「其他 → 强制结束变声引擎」",
    a: "到「其他」页点「强制结束变声引擎」，再重开软件。这只结束残留的引擎进程，不会关掉主界面。",
  },
  {
    q: "第一次开启特别慢",
    hint: "正常，冷启动要加载模型和运行时",
    a: "第一次开启变声要加载 PyTorch 和音色模型，通常 20–40 秒。之后再开会快很多。",
  },
  {
    q: "中文路径报错",
    hint: "把整个软件放到英文路径再试",
    a: "部分依赖对非 ASCII 路径处理不好。把整个安装目录移到纯英文路径（例如 D:\\RVCFabric）后重试。",
  },
];

function HelpPageImpl() {
  const [open, setOpen] = useState<string>("");
  // 名词表和常见情况各自独立展开，互不影响。
  const [openTerm, setOpenTerm] = useState<string>("");
  // Installing the driver needs UAC, so it can only ever be user-initiated.
  // Without this entry the pack is downloaded but never actually installed.
  // "checking" and "we could not check" used to be the same state (null), so a
  // failed status call showed 「正在检查…」 forever.
  const [vbReady, setVbReady] = useState<boolean | "checking" | "unknown">(
    "checking",
  );
  const [vbMsg, setVbMsg] = useState("");
  const [vbBusy, setVbBusy] = useState(false);

  const refreshVb = async () => {
    try {
      const st = await invoke<{ vbcable_pack_ready?: boolean }>("assets_status");
      setVbReady(!!st.vbcable_pack_ready);
    } catch {
      setVbReady("unknown");
    }
  };
  useEffect(() => {
    void refreshVb();
  }, []);

  const installVb = async () => {
    if (vbBusy) return;
    setVbBusy(true);
    setVbMsg("");
    try {
      if (vbReady !== true) {
        setVbMsg("正在下载安装包…");
        await invoke("assets_ensure_vbcable");
        await refreshVb();
      }
      setVbMsg("正在启动官方安装程序…");
      await invoke("assets_install_vbcable");
      // Only say it launched once it actually did.
      setVbMsg("已启动官方安装程序，请在弹出的窗口里确认（需要管理员权限）");
    } catch (e) {
      setVbMsg(`失败：${String(e)}`);
    } finally {
      setVbBusy(false);
    }
  };

  return (
    <PagePad>
      <PageHead title="说明" sub="虚拟声卡连接、常见情况与专有名词" />

      <Block title="安装虚拟声卡">
        <p className="text-[12.5px] text-[var(--help)] leading-relaxed m-0 mb-4 max-w-[74ch]">
          想让游戏 / 语音 里的人听到变声，必须先装虚拟声卡（VB-Cable）。
          装完重启一次电脑，设备列表里才会出现 CABLE Input / CABLE Output。
        </p>
        <Group>
          <ListItem
            title="VB-Cable"
            titleTip={tip("虚拟声卡")}
            desc={
              vbMsg ||
              (vbReady === "checking"
                ? "正在检查…"
                : vbReady === "unknown"
                  ? "无法查询安装包状态，点右侧仍可尝试下载并安装"
                  : vbReady
                    ? "安装包已就绪，点右侧开始安装（会弹管理员确认）"
                    : "尚未下载安装包，点右侧会先下载再安装")
            }
            right={
              <Btn disabled={vbBusy} onClick={() => void installVb()}>
                {vbBusy ? "处理中…" : "安装虚拟声卡"}
              </Btn>
            }
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
            title="游戏 / 语音 麦克风"
            desc="选 CABLE Output"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">CABLE Output</span>}
          />
          <ListItem
            title="Windows 默认播放"
            desc="保持选择耳机，不要选 CABLE"
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">耳机</span>}
          />
        </Group>
      </Block>
      <Block title="常见情况" note={String(FAQ.length)}>
        <Group>
          {FAQ.map((f) => (
            <ListItem
              key={f.q}
              title={f.q}
              desc={f.hint}
              expanded={open === f.q}
              onClick={() => setOpen((cur) => (cur === f.q ? "" : f.q))}
              right={
                <span className="text-[13.5px] text-[var(--ink-muted)]">
                  {open === f.q ? "收起" : "展开"}
                </span>
              }
            >
              {f.a}
            </ListItem>
          ))}
        </Group>
      </Block>
      <Block title="专有名词" note={String(GLOSSARY.length)}>
        <Group>
          {GLOSSARY.map((t) => (
            <ListItem
              key={t.term}
              title={t.term}
              desc={t.brief}
              expanded={openTerm === t.term}
              onClick={() => setOpenTerm((cur) => (cur === t.term ? "" : t.term))}
              right={
                <span className="text-[13.5px] text-[var(--ink-muted)]">
                  {openTerm === t.term ? "收起" : "展开"}
                </span>
              }
            >
              {t.detail}
            </ListItem>
          ))}
        </Group>
      </Block>
    </PagePad>
  );
}

/**
 * Memoised: App re-renders on every engine status tick (2.5x a second while
 * converting). Without this the whole page tree was rebuilt each time for a
 * mic-level change that only the dock cares about.
 */
export const HelpPage = memo(HelpPageImpl);
