/**
 * 声音通道的识别与虚拟声卡的安装，说明页与新手引导共用。
 */
import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { t } from "../i18n/t";

/**
 * 设备列表里认得出来的「能把变声送进游戏」的通道。
 * 匹配键保持中英双语字面量（设备名可能是中文系统），label 走 t()。
 */
export function buildRoutes(): {
  kind: "virtual" | "physical";
  label: string;
  keys: string[];
}[] {
  return [
    {
      kind: "virtual",
      label: "VB-Cable",
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
      // Device-name match tokens: keep Chinese + English literals always.
      keys: [
        "virtual audio",
        "virtual cable",
        "虚拟音频",
        "synchronous audio",
      ],
    },
    {
      kind: "physical",
      label: t("s.402fd697c1"),
      keys: [
        "立体声混音",
        "stereo mix",
        "what u hear",
        "wave out mix",
        "波输出混合",
      ],
    },
  ];
}

/** 设备名可能是字符串，也可能是 `{name}`，两边都得认。 */
export function deviceNames(list: unknown): string[] {
  if (!Array.isArray(list)) return [];
  return list
    .map((d) => (typeof d === "string" ? d : String((d as { name?: string })?.name ?? "")))
    .filter(Boolean);
}

export function detectRoutes(
  names: string[],
  routes: ReturnType<typeof buildRoutes>,
): { kind: "virtual" | "physical"; label: string }[] {
  const lower = names.map((n) => n.toLowerCase());
  const hits: { kind: "virtual" | "physical"; label: string }[] = [];
  for (const r of routes) {
    // 「其他虚拟声卡」是兜底桶，已经认出具体是哪一款就别再报一遍：
    // VB-Cable 的设备名是「VB-Audio Virtual Cable」，两条都能命中，
    // 报成「VB-Cable、其他虚拟声卡」会让人以为自己装了两套。
    if (r.label === t("s.1d2f7d6189") && hits.some((h) => h.kind === "virtual")) {
      continue;
    }
    if (r.keys.some((k) => lower.some((n) => n.includes(k.toLowerCase())))) {
      hits.push({ kind: r.kind, label: r.label });
    }
  }
  return hits;
}


/**
 * VB-Cable 的状态与安装、卸载。安装要用户授权（UAC），只能由用户点按钮发起。
 * 「正在检查」与「检查不了」分开：状态读失败时不能一直显示正在检查。
 */
export function useVbCable() {
  const [ready, setReady] = useState<boolean | "checking" | "unknown">("checking");
  const [installed, setInstalled] = useState(false);
  const [removed, setRemoved] = useState(false);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<"install" | "uninstall" | false>(false);

  const refresh = async () => {
    try {
      const st = await invoke<{ vbcable_pack_ready?: boolean; vbcable_installed?: boolean }>("assets_status");
      setReady(!!st.vbcable_pack_ready);
      setInstalled(!!st.vbcable_installed);
    } catch {
      setReady("unknown");
    }
  };
  useEffect(() => {
    void refresh();
  }, []);

  const install = async () => {
    if (busy) return;
    setBusy("install");
    setMsg("");
    try {
      if (ready !== true) {
        setMsg(t("s.3076e38c53"));
        try {
          await invoke("assets_ensure_vbcable");
        } catch (e) {
          // 下载失败和安装失败是两回事，报错也得分开说
          throw new Error(t("s.04c4e3b2b3", { e: String(e) }));
        }
        await refresh();
      }
      setMsg(t("s.vbcableInstalling"));
      // 静默安装，装完才返回
      await invoke("assets_install_vbcable");
      setRemoved(false);
      setMsg(t("s.vbcableDone"));
      await refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const uninstall = async () => {
    if (busy) return;
    setBusy("uninstall");
    setMsg("");
    try {
      setMsg(t("s.vbcableUninstalling"));
      await invoke("assets_uninstall_vbcable");
      setRemoved(true);
      setMsg(t("s.vbcableUninstalled"));
      await refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return { ready, installed, removed, msg, busy, install, uninstall };
}
