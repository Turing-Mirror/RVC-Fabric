import { useEffect, useState, memo } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Block, Btn, Group, ListItem, PageHead, PagePad } from "../components/ui";
import { tip, useGlossary, useGlossarySectionTitle } from "../lib/glossary";
import { t } from "../i18n/t";

/**
 * Answers carried over verbatim from the Tk shell's `help_content.py` and its
 * 「实体声卡连接」 dialog. The rows already said 「展开」; they just had nothing
 * behind them.
 */
const FAQ: { q: string; hint: string; a: string }[] = [
  {
    q: t("s.73996ce817"),
    hint: t("s.8152d450a3"),
    a: [
      t("s.d8e4f74b8b"),
      t("s.ac66eb660d"),
      t("s.ab4550db36"),
    ].join("\n"),
  },
  {
    q: t("s.e410af7f1f"),
    hint: t("s.ad0e3472be"),
    a: [
      t("s.d02e026f75"),
      t("s.52c469558c"),
    ].join("\n"),
  },
  {
    q: t("s.ca98fe8db7"),
    hint: t("s.68458a0d6c"),
    a: [
      t("s.d9cb071850"),
      t("s.504a366966"),
      t("s.4bbfde15f2"),
      t("s.e6408f03f4"),
      t("s.561d709070"),
    ].join("\n"),
  },
  {
    q: t("s.c96a64f150"),
    hint: t("s.8d5976502c"),
    a: [
      t("s.b5fba7b794"),
      t("s.49c4c2a8bb"),
      t("s.e7181ea0d6"),
      t("s.60d612146d"),
      "",
      t("s.c777a891cf"),
      t("s.1a3fe8f826"),
      t("s.efc83ad78c"),
      "",
      t("s.ea5083770c"),
      t("s.983328d89b"),
      t("s.3800ff2864"),
    ].join("\n"),
  },
  {
    q: t("s.0ec38407bc"),
    hint: t("s.cd8301f295"),
    a: t("s.83d8ae170a"),
  },
  {
    q: t("s.29a29efed7"),
    hint: t("s.7cdb0a7622"),
    a: t("s.23cb78c4b5"),
  },
  {
    q: t("s.8e6b1ba01b"),
    hint: t("s.55e39bd8d0"),
    a: t("s.d69e96920e"),
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
    label: t("s.1d2f7d6189"),
    keys: ["virtual audio", "virtual cable", t("s.7d7d710ba5"), "synchronous audio"],
  },
  {
    kind: "physical",
    label: t("s.402fd697c1"),
    keys: [t("s.75df86cca5"), "stereo mix", "what u hear", "wave out mix", t("s.bd52e3bc24")],
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
    if (r.label === t("s.1d2f7d6189") && hits.some((h) => h.kind === "virtual")) {
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
        setVbMsg(t("s.3076e38c53"));
        await invoke("assets_ensure_vbcable");
        await refreshVb();
      }
      setVbMsg(t("s.17d9ff0c09"));
      await invoke("assets_install_vbcable");
      // Only say it launched once it actually did.
      setVbMsg(t("s.65c66af000"));
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
      <PageHead title={t("s.26670dda42")} sub={t("s.e137006ffd")} />

      <Block title={t("s.b386a7fb53")}>
        <p className="text-[12.5px] text-[var(--help)] leading-relaxed m-0 mb-4 max-w-[74ch]">{t("s.5695956a42")}</p>
        {/* 先照着用户机器上真实的设备列表说一句话。
            已经有 VoiceMeeter 的人再装一个 VB-Cable，只会多两个设备、
            多一层能接错的地方 —— 那不是帮忙。 */}
        <div className="rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] px-3.5 py-3 mb-4 text-[12.5px] leading-relaxed max-w-[74ch]">
          {!known ? (
            <span className="text-[var(--help)]">{t("s.60f0f911ec")}</span>
          ) : found.length === 0 ? (
            <span className="text-[var(--ink-muted)]">
              在你的 {names.length} 个设备里没找到可用的转发通道，
              需要装虚拟声卡。点下面的「安装虚拟声卡」即可。
            </span>
          ) : (
            <span className="text-[var(--ink-muted)]">{t("s.a1fdfdae84")}<b className="font-semibold">{found.map((f) => f.label).join("、")}</b>。
              <br />
              {hasVirtual
                ? hasCable
                  ? t("s.a8bd2d876d")
                  : t("s.10481886ca")
                : t("s.4951a916f7")}
            </span>
          )}
        </div>
        <Group>
          <ListItem
            title="VB-Cable"
            titleTip={tip(t("s.7d7d710ba5"))}
            desc={
              vbMsg ||
              (hasCable
                ? t("s.3d2c784f94")
                : vbReady === "checking"
                ? t("s.481ee2d4bc")
                : vbReady === "unknown"
                  ? t("s.1b94ca3bf5")
                  : vbReady
                    ? t("s.71c000a0a8")
                    : t("s.7be46937d4"))
            }
            right={
              <Btn disabled={vbBusy} onClick={() => void installVb()}>
                {vbBusy ? t("s.1cac8ac7f5") : t("s.b386a7fb53")}
              </Btn>
            }
          />
        </Group>
      </Block>

      <Block title={t("s.149ab7bf0a")}>
        <Group>
          <ListItem
            title={t("s.69f4bc1200")}
            desc={t("s.0f14377cdd")}
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">{t("s.bbefc72e6f")}</span>}
          />
          <ListItem
            title={t("s.b4b5016e9f")}
            desc={t("s.0709bd6ae7")}
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">CABLE Input</span>}
          />
          <ListItem
            title={t("s.6f63f33852")}
            desc={t("s.2898cbf891")}
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">{t("s.d5ca969dc3")}</span>}
          />
          <ListItem
            title={t("s.d0a420e1ca")}
            desc={t("s.cad046a475")}
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">CABLE Output</span>}
          />
          <ListItem
            title={t("s.364b26a260")}
            desc={t("s.26ad7c406b")}
            right={<span className="text-[13.5px] text-[var(--ink-muted)]">{t("s.d5ca969dc3")}</span>}
          />
        </Group>
      </Block>
      <Block title={t("s.209d309d58")} note={String(FAQ.length)}>
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
                  {open === f.q ? t("s.5d5815647c") : t("s.b0e24833f7")}
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
                  {openTerm === term.term ? t("s.5d5815647c") : t("s.b0e24833f7")}
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
