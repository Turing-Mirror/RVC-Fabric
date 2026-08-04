import { useEffect, useState, memo } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Block, Btn, Group, ListItem, PageHead, PagePad } from "../components/ui";
import { tip, useGlossary, useGlossarySectionTitle } from "../lib/glossary";

/**
 * Answers carried over verbatim from the Tk shell's `help_content.py` and its
 * 「实体声卡连接」 dialog. The rows already said 「展开」; they just had nothing
 * behind them.
 */
const FAQ: { q: string; hint: string; a: string }[] = [
  {
    q: "对方说听不到我",
    hint: "检查游戏/语音里的麦克风是否选成了 CABLE Output",
    a: [
      "1. 游戏/语音的麦克风设为 CABLE Output",
      "2. 本软件的输出设备设为 CABLE Input",
      "3. 确认已「开启变声」，且模式是「实时变声」而非「旁路原声」",
    ].join("\n"),
  },
  {
    q: "我自己听不到变声",
    hint: "在设置里开启「变声时监听自己」，监听设备选真实耳机",
    a: [
      "1. 设置 → 设备与音频 → 勾选「变声时监听自己」",
      "2. 监听设备选真实耳机或音箱，不要选 CABLE 等虚拟声卡",
    ].join("\n"),
  },
  {
    q: "声音断断续续",
    hint: "可尝试调低响应阈值，或调大采样块时长",
    a: [
      "1. 适当调大「采样块时长」（越大越稳，延迟也越高）",
      "2. 关闭输入或输出降噪中的一项（降噪较吃显卡）",
      "3. 音高算法换 FCPE 或 RMVPE 试听",
      "4. 关闭其他占用麦克风的软件",
      "5. 确认安装的是与显卡匹配的运行时版本",
    ].join("\n"),
  },
  {
    q: "实体声卡怎么连",
    hint: "硬件声卡、USB 直播声卡及调音台的路由接法",
    a: [
      "**模式 A：麦克风走实体声卡**",
      "1. 输入设备：实体声卡的录音通道（名字里带声卡型号）",
      "2. 输出设备：仍选 CABLE Input，对面听到变声仍靠虚拟声卡",
      "3. 监听：耳机插在声卡上，监听设备选实体声卡的播放通道",
      "",
      "**模式 B：走声卡内录 / 立体声混音**",
      "1. 输出设备：实体声卡的播放通道",
      "2. 游戏/语音麦克风：声卡的内录通道（叫法以声卡说明书为准）",
      "",
      "**注意**",
      "1. 先关掉声卡驱动自带的降噪/混响/变声，避免与本软件冲突",
      "2. 设备列表里没有设备时，点「重载设备列表」或重启软件",
    ].join("\n"),
  },
  {
    q: "停不干净、声卡一直被占",
    hint: "到「其他」页用「强制结束变声引擎」",
    a: "「其他」页点「强制结束变声引擎」，再重新开启变声即可。该操作只结束残留的引擎进程，不会关闭主界面。",
  },
  {
    q: "第一次开启特别慢",
    hint: "正常，冷启动需要加载模型和运行时",
    a: "首次开启变声需加载 PyTorch 和音色模型，通常 20–40 秒；之后再开会快很多。",
  },
  {
    q: "中文路径报错",
    hint: "把软件放到纯英文路径再试",
    a: "部分底层依赖对中文/非 ASCII 路径兼容性较差。把安装目录移到纯英文路径（如 `D:\\RVCFabric`）后重试。",
  },
];

/**
 * 设备列表里认得出来的「能把变声送进游戏」的通道。
 *
 * 不是只认 CABLE：装了 VoiceMeeter 的人已经有虚拟声卡了，让他再装一个
 * VB-Cable 只会多两个设备、多一层能接错的地方。带内录/立体声混音的实体声卡
 * 同样能走通（说明页「实体声卡怎么连」那条讲的就是这个）。
 *
 * `kind` 决定给出什么建议，所以分开写而不是合成一个正则。
 */
const ROUTES: { kind: "virtual" | "physical"; label: string; keys: string[] }[] = [
  {
    kind: "virtual",
    label: "VB-Cable",
    // 不能拿厂商名「vb-audio」当特征：VoiceMeeter 也是 VB-Audio 出的，
    // 它的设备名叫「VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)」，
    // 照厂商名匹配会把只装了 VoiceMeeter 的人判成「VB-Cable 已装好」，
    // 然后让他照着 CABLE Input 去接一个根本不存在的设备。
    // 认设备名本身：VB-Cable 装出来的就叫 CABLE Input / CABLE Output。
    keys: ["cable input", "cable output", "vb-audio virtual cable"],
  },
  {
    kind: "virtual",
    label: "VoiceMeeter",
    keys: ["voicemeeter", "voice meeter"],
  },
  {
    kind: "virtual",
    label: "其他虚拟声卡",
    keys: ["virtual audio", "virtual cable", "虚拟声卡", "synchronous audio"],
  },
  {
    kind: "physical",
    label: "声卡内录 / 立体声混音",
    keys: ["立体声混音", "stereo mix", "what u hear", "wave out mix", "内录"],
  },
];

/** 设备名可能是字符串，也可能是 `{name}`，两边都得认。 */
function deviceNames(list: unknown): string[] {
  if (!Array.isArray(list)) return [];
  return list
    .map((d) => (typeof d === "string" ? d : String((d as { name?: string })?.name ?? "")))
    .filter(Boolean);
}

function detectRoutes(names: string[]): { kind: "virtual" | "physical"; label: string }[] {
  const lower = names.map((n) => n.toLowerCase());
  const hits: { kind: "virtual" | "physical"; label: string }[] = [];
  for (const r of ROUTES) {
    // 「其他虚拟声卡」是兜底桶，已经认出具体是哪一款就别再报一遍：
    // VB-Cable 的设备名是「VB-Audio Virtual Cable」，两条都能命中，
    // 报成「VB-Cable、其他虚拟声卡」会让人以为自己装了两套。
    if (r.label === "其他虚拟声卡" && hits.some((h) => h.kind === "virtual")) {
      continue;
    }
    if (r.keys.some((k) => lower.some((n) => n.includes(k)))) {
      hits.push({ kind: r.kind, label: r.label });
    }
  }
  return hits;
}

type HelpProps = {
  /** 引擎报的设备列表。空的时候是引擎还没起来，不代表用户没装声卡。 */
  status?: { input_devices?: unknown; output_devices?: unknown };
};

function HelpPageImpl({ status }: HelpProps = {}) {
  const glossary = useGlossary();
  const glossaryTitle = useGlossarySectionTitle();
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
      setVbMsg("已启动官方安装程序，请在弹窗中确认（需要管理员权限）");
    } catch (e) {
      setVbMsg(`失败：${String(e)}`);
    } finally {
      setVbBusy(false);
    }
  };

  const names = [
    ...deviceNames(status?.input_devices),
    ...deviceNames(status?.output_devices),
  ];
  const known = names.length > 0;
  const found = detectRoutes(names);
  const hasVirtual = found.some((f) => f.kind === "virtual");
  const hasCable = found.some((f) => f.label === "VB-Cable");

  return (
    <PagePad>
      <PageHead title="说明" sub="虚拟声卡连接、常见情况与专有名词" />

      <Block title="安装虚拟声卡">
        <p className="text-[12.5px] text-[var(--help)] leading-relaxed m-0 mb-4 max-w-[74ch]">
          想让游戏 / 语音 里的人听到变声，必须先装虚拟声卡（VB-Cable）。
          装完重启一次电脑，设备列表里才会出现 CABLE Input / CABLE Output。
        </p>
        {/* 先照着用户机器上真实的设备列表说一句话。
            已经有 VoiceMeeter 的人再装一个 VB-Cable，只会多两个设备、
            多一层能接错的地方 —— 那不是帮忙。 */}
        <div className="rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] px-3.5 py-3 mb-4 text-[12.5px] leading-relaxed max-w-[74ch]">
          {!known ? (
            <span className="text-[var(--help)]">
              还没读到设备列表，暂时没法判断你装没装声卡。
              引擎启动后（或在「设置 → 设备与音频」点一次「重载设备列表」）再回来看。
            </span>
          ) : found.length === 0 ? (
            <span className="text-[var(--ink-muted)]">
              在你的 {names.length} 个设备里没找到可用的转发通道，
              需要装虚拟声卡。点下面的「安装虚拟声卡」即可。
            </span>
          ) : (
            <span className="text-[var(--ink-muted)]">
              已在你的设备列表里找到：
              <b className="font-semibold">{found.map((f) => f.label).join("、")}</b>。
              <br />
              {hasVirtual
                ? hasCable
                  ? "VB-Cable 已经装好了，不用再装一遍。直接照下面「虚拟声卡怎么连」接线就行。"
                  : "你已经有虚拟声卡了，不必再装 VB-Cable —— 多装一套只会多出几个容易接错的设备。把软件输出选到它的输入端，游戏麦克风选到它的输出端即可。"
                : "这是实体声卡的内录通道，也能走通：软件输出选实体声卡的播放，游戏麦克风选这个内录通道。展开下面「实体声卡怎么连」有详细接法。"}
            </span>
          )}
        </div>
        <Group>
          <ListItem
            title="VB-Cable"
            titleTip={tip("虚拟声卡")}
            desc={
              vbMsg ||
              (hasCable
                ? "系统里已经有 CABLE 设备，不用再装。重装只在设备损坏时才需要"
                : vbReady === "checking"
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
      <Block title={glossaryTitle} note={String(glossary.length)}>
        <Group>
          {glossary.map((term) => (
            <ListItem
              key={term.id || term.term}
              title={term.term}
              desc={term.brief}
              expanded={openTerm === term.term}
              onClick={() =>
                setOpenTerm((cur) => (cur === term.term ? "" : term.term))
              }
              right={
                <span className="text-[13.5px] text-[var(--ink-muted)]">
                  {openTerm === term.term ? "收起" : "展开"}
                </span>
              }
            >
              {term.detail}
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
