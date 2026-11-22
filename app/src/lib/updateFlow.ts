/**
 * 更新流程状态机（C2）：检查归检查，确认更新归更新。
 *
 * - `probe` / `check` 只发 `update_check`，绝不调用下载或安装入口；
 * - 发现新版只置 offer，用户明确点「下载并安装」(`accept`) 才进入下载；
 * - 安装中 `working`；失败回到可点状态并把错误留在原位置，可重试；
 * - `dismiss` 只关闭提示，不更新、不打断当前任务。
 */
import { useCallback, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { t } from "../i18n/t";

export type UpdateChannel = "stable" | "beta";

export type UpdateChannelStatus = {
  channel: UpdateChannel;
  version: string;
  beta_available: boolean;
};

/** `update_check` 的返回。字段名和 `update::decide` 里那个 json! 一一对应。 */
export type UpdateInfo = {
  local: string;
  remote: string;
  available: boolean;
  blocked_by_min_version: boolean;
  min_app_version: string;
  package_type: string;
  /** `external` = 换 exe，走签名更新器；否则是界面补丁。 */
  action: string;
  url: string;
  sha256: string;
  notes: string;
  /** Older stable backends omit channel metadata. */
  channel?: UpdateChannel;
  installed_channel?: UpdateChannel;
  switching_channel?: boolean;
  downgrade?: boolean;
  legacy_target?: boolean;
};

export function updateChannelLabel(channel: UpdateChannel): string {
  return channel === "beta" ? "Beta" : t("update.stable");
}

function offerKey(offer: UpdateInfo): string {
  return `${offer.channel ?? "stable"}:${offer.remote}`;
}

/** `14:07`。状态行里带个时间，才看得出这句话是刚查的还是上次留下的。 */
function clockNow(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes(),
  ).padStart(2, "0")}`;
}

export function useUpdateFlow() {
  const [line, setLine] = useState("");
  const [busy, setBusy] = useState(false);
  const [channelStatus, setChannelStatus] = useState<UpdateChannelStatus | null>(null);
  const channelStatusRef = useRef<UpdateChannelStatus | null>(null);
  const [selectedChannel, setSelectedChannel] = useState<UpdateChannel>("stable");
  // A selection is a check target, never a claim that the installed program changed.
  const selectedTarget = useRef<UpdateChannel | undefined>(undefined);
  const [checkedTarget, setCheckedTarget] = useState<UpdateInfo | null>(null);
  const generation = useRef(0);
  const probeGenerations = useRef(new WeakMap<UpdateInfo, number>());
  // busy 的同步镜像：setBusy 要等重渲染才生效，同一拍里连点两次会双双
  // 通过 state 判定。检查/安装任一在途都由它当场挡住。
  const busyRef = useRef(false);
  // 查到的新版本。非空 = 弹一条「要不要现在装」。
  const [offer, setOffer] = useState<UpdateInfo | null>(null);
  // 答应更新之后提示留在原地变成进度；失败时回到可点状态。
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  // 装完的明确结果态：不是「待确认」也不是「在装」—— 界面上只剩
  // 「已更新 + 重启生效 + 知道了」，不能再把安装按钮摆出来。
  const [result, setResult] = useState<{
    version: string;
    restart: boolean;
  } | null>(null);
  // Keep the channel with the version: changing channels must not inherit a
  // previous channel's completion marker.
  const doneRemote = useRef("");

  const refreshChannelStatus = useCallback(async () => {
    const status = await invoke<UpdateChannelStatus>("update_channel_status");
    channelStatusRef.current = status;
    setChannelStatus(status);
    if (selectedTarget.current === undefined) setSelectedChannel(status.channel);
  }, []);

  /** Only checks; a response for an obsolete request cannot replace the target. */
  const requestCheck = async (): Promise<UpdateInfo | null> => {
    const request = ++generation.current;
    const target = selectedTarget.current;
    const r = await invoke<UpdateInfo>("update_check", target ? { channel: target } : undefined);
    if (request !== generation.current) return null;
    probeGenerations.current.set(r, request);
    setCheckedTarget(r);
    if (r.blocked_by_min_version) {
      setLine(
        t("s.214fe7bcad", {
          v0: String(r.local),
          v1: String(r.min_app_version),
        }),
      );
      return null;
    }
    if (!r.available) {
      setLine(t("s.7ccca92d5e", { v0: String(r.local), v1: clockNow() }));
      return null;
    }
    setLine(t("s.622a22349e", { v0: String(r.remote), v1: String(r.local) }));
    return r;
  };

  /** Background checks never take over a check or installation already in progress. */
  const probe = async (): Promise<UpdateInfo | null> => {
    if (busyRef.current) return null;
    return requestCheck();
  };

  /** 真正下载并安装。整包走签名更新器，界面补丁走 update_apply。 */
  const install = async (r: UpdateInfo): Promise<{ restart: boolean }> => {
    if (r.action === "external") {
      setLine(t("s.b22f6e52ac", { v0: String(r.remote) }));
      const b = await invoke<Record<string, unknown>>(
        "update_app",
        r.channel ? { channel: r.channel, version: r.remote } : { version: r.remote },
      );
      if (!b?.installed) {
        // 更新器跑完但没装上（取消/校验不过）：这是终态失败，不是
        // 「正在更新」—— 抛出去让 runInstall 复位 working、留可重试的错误。
        throw new Error(t("s.3d1fde4601"));
      }
      setLine(t("s.995e0f4c81", { v0: String(b.version ?? r.remote) }));
      return { restart: b.restart_required !== false };
    }
    setLine(t("s.5b3dc1999a", { v0: String(r.remote) }));
    const b = await invoke<Record<string, unknown>>("update_apply", {
      url: String(r.url),
      sha256: String(r.sha256 || ""),
    });
    setLine(t("s.995e0f4c81", { v0: String(r.remote) }));
    return { restart: b?.restart_required !== false };
  };

  /** 「立即检查」：检查归检查，查到新版只弹出确认条。 */
  const check = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setLine(t("s.481ee2d4bc"));
    setOffer(null);
    setError("");
    setResult(null);
    try {
      const r = await requestCheck();
      if (r) {
        // 这个版本本会话已经装过了：状态行如实写「已是最新」，别再弹一遍。
        if (offerKey(r) === doneRemote.current) {
          setLine(t("s.7ccca92d5e", { v0: String(r.local), v1: clockNow() }));
        } else {
          setError("");
          setWorking(false);
          setResult(null);
          setOffer(r);
        }
      }
    } catch (e) {
      setLine(t("s.ac3a85a9c1", { v0: String(e) }));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const selectChannel = async (channel: UpdateChannel) => {
    if (busyRef.current) return;
    if (!channelStatusRef.current || (channel === "beta" && !channelStatusRef.current.beta_available)) {
      setLine(t("update.channelUnavailable"));
      return;
    }
    ++generation.current;
    selectedTarget.current = channel;
    setSelectedChannel(channel);
    setCheckedTarget(null);
    setOffer(null);
    setResult(null);
    setError("");
    await check();
  };

  /** 确认后的安装。失败留在原位置可重试，不永久停在「正在更新」。 */
  const runInstall = async (r: UpdateInfo) => {
    if (busyRef.current) return;
    // 同版本本会话已装好：残留的确认入口（旧提示、已知问题横幅）再点
    // 也不能再装一遍。
    if (doneRemote.current && offerKey(r) === doneRemote.current) return;
    if (r.channel && selectedTarget.current && r.channel !== selectedTarget.current) return;
    ++generation.current;
    busyRef.current = true;
    setError("");
    setResult(null);
    setWorking(true);
    setBusy(true);
    try {
      const res = await install(r);
      doneRemote.current = offerKey(r);
      setResult({ version: r.remote, restart: res.restart });
      // 装完就是终态：提示条停回可点状态，不能永远显示「正在更新」。
      setWorking(false);
    } catch (e) {
      const detail = e instanceof Error ? e.message : String(e);
      const msg = t("s.bac68ea7db", { v0: detail });
      setLine(msg);
      setError(msg);
      setWorking(false);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const accept = async () => {
    const r = offer;
    if (!r) return;
    await runInstall(r);
  };

  /** 已有提示复用、没有就先查再装 —— 已知问题横幅的「更新到 x.y.z」用它。 */
  const installOffer = async (r: UpdateInfo) => {
    // 先看所有权再动 offer：正在装/检查时不许把在装的提示换掉。
    if (busyRef.current) return;
    if (r.channel && selectedTarget.current && r.channel !== selectedTarget.current) return;
    setOffer(r);
    await runInstall(r);
  };

  /** 只把结果挂成待确认提示（开机自动检查到新版时用），不安装。 */
  const present = (r: UpdateInfo) => {
    // 检查/安装任一在途时都不许动：否则一次自动探测会把「正在更新」
    // 撤销成可再点的状态，在装的流程被重复触发。
    if (busyRef.current) return;
    // 这版本已经装过：别再弹一遍待确认提示。
    if (offerKey(r) === doneRemote.current) return;
    const request = probeGenerations.current.get(r);
    if (request !== undefined && request !== generation.current) return;
    if (r.channel && selectedTarget.current && r.channel !== selectedTarget.current) return;
    setError("");
    setWorking(false);
    setResult(null);
    setOffer(r);
  };

  const dismiss = () => {
    ++generation.current;
    setOffer(null);
    setResult(null);
  };

  return {
    line,
    busy,
    offer,
    working,
    error,
    result,
    channelStatus,
    selectedChannel,
    checkedTarget,
    refreshChannelStatus,
    selectChannel,
    probe,
    check,
    accept,
    installOffer,
    present,
    dismiss,
  };
}
