/**
 * 更新流程状态机（C2）：检查归检查，确认更新归更新。
 *
 * - `probe` / `check` 只发 `update_check`，绝不调用下载或安装入口；
 * - 发现新版只置 offer，用户明确点「下载并安装」(`accept`) 才进入下载；
 * - 安装中 `working`；失败回到可点状态并把错误留在原位置，可重试；
 * - `dismiss` 只关闭提示，不更新、不打断当前任务。
 */
import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { t } from "../i18n/t";

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
};

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
  // 查到的新版本。非空 = 弹一条「要不要现在装」。
  const [offer, setOffer] = useState<UpdateInfo | null>(null);
  // 答应更新之后提示留在原地变成进度；失败时回到可点状态。
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  /** 只查，不装。返回后端那份原样的结果，顺手把状态行写好。 */
  const probe = async (): Promise<UpdateInfo | null> => {
    const r = (await invoke<Record<string, unknown>>(
      "update_check",
    )) as UpdateInfo;
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

  /** 真正下载并安装。整包走签名更新器，界面补丁走 update_apply。 */
  const install = async (r: UpdateInfo) => {
    if (r.action === "external") {
      setLine(t("s.b22f6e52ac", { v0: String(r.remote) }));
      const b = await invoke<Record<string, unknown>>("update_app");
      setLine(
        b?.installed
          ? t("s.995e0f4c81", { v0: String(b.version ?? r.remote) })
          : t("s.3d1fde4601"),
      );
      return;
    }
    setLine(t("s.5b3dc1999a", { v0: String(r.remote) }));
    await invoke("update_apply", {
      url: String(r.url),
      sha256: String(r.sha256 || ""),
    });
    setLine(t("s.995e0f4c81", { v0: String(r.remote) }));
  };

  /** 「立即检查」：检查归检查，查到新版只弹出确认条。 */
  const check = async () => {
    if (busy) return;
    setBusy(true);
    setLine(t("s.481ee2d4bc"));
    try {
      const r = await probe();
      if (r) {
        setError("");
        setWorking(false);
        setOffer(r);
      }
    } catch (e) {
      setLine(t("s.ac3a85a9c1", { v0: String(e) }));
    } finally {
      setBusy(false);
    }
  };

  /** 确认后的安装。失败留在原位置可重试，不永久停在「正在更新」。 */
  const runInstall = async (r: UpdateInfo) => {
    setError("");
    setWorking(true);
    setBusy(true);
    try {
      await install(r);
    } catch (e) {
      const msg = t("s.bac68ea7db", { v0: String(e) });
      setLine(msg);
      setError(msg);
      setWorking(false);
    } finally {
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
    setOffer(r);
    await runInstall(r);
  };

  /** 只把结果挂成待确认提示（开机自动检查到新版时用），不安装。 */
  const present = (r: UpdateInfo) => {
    setError("");
    setWorking(false);
    setOffer(r);
  };

  const dismiss = () => setOffer(null);

  return {
    line,
    busy,
    offer,
    working,
    error,
    probe,
    check,
    accept,
    installOffer,
    present,
    dismiss,
  };
}
