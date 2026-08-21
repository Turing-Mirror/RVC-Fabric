import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import { t } from "../i18n/t";
import { FindingList, type Finding } from "./FindingList";
import {
  MAX_SHOTS,
  imageFilesFrom,
  prepareShot,
  type Shot,
} from "../lib/shots";

/** 出包之前的文件清单。bytes 为 null 表示这份是出包时现生成的。 */
type DiagPreview = {
  items: { name: string; bytes: number | null }[];
  total_bytes: number;
};

export type DiagReport = {
  nickname: string;
  qq: string;
  description: string;
  withPerf: boolean;
  /** 用户粘进来或选中的截图，出包时写进 shots/。 */
  shots: { ext: string; data: string }[];
};

/**
 * 生成诊断包前先问一句：你是谁、遇到了什么。
 *
 * 以前这里是一个 `askConfirm`，只问「要不要顺便跑性能测试」。结果支援收到的
 * 是一个 `diag_20260817_143012.zip`，既不知道该回复谁，也得从三十个日志文件
 * 里反推用户到底想说什么 —— 那件事只有用户自己知道，日志里没有。
 *
 * 三个字段全是可选的：填不填是用户的自由，不填也照样能出包。
 */
export function DiagnosticsDialog({
  open,
  onCancel,
  onSubmit,
}: {
  open: boolean;
  onCancel: () => void;
  onSubmit: (r: DiagReport) => void;
}) {
  const [nickname, setNickname] = useState("");
  const [qq, setQq] = useState("");
  const [description, setDescription] = useState("");
  const [withPerf, setWithPerf] = useState(false);
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [preview, setPreview] = useState<DiagPreview | null>(null);
  const [shots, setShots] = useState<Shot[]>([]);
  const [shotMsg, setShotMsg] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const firstRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setNickname("");
    setQq("");
    setDescription("");
    setWithPerf(false);
    setShots([]);
    setShotMsg("");
    setDragging(false);
    const id = window.setTimeout(() => firstRef.current?.focus(), 30);
    return () => window.clearTimeout(id);
  }, [open]);

  // 只读盘，不改任何东西；出包之前先把已经能看出来的摆出来。
  useEffect(() => {
    if (!open) {
      setFindings(null);
      return;
    }
    let alive = true;
    invoke<Finding[]>("diagnostics_self_check")
      .then((v) => {
        if (alive) setFindings(Array.isArray(v) ? v : []);
      })
      .catch(() => {
        // 自检失败不该挡住出包 —— 包本身才是用户要的东西。
        if (alive) setFindings([]);
      });
    return () => {
      alive = false;
    };
  }, [open]);

  // 包里到底有什么，出包之前先摆出来。跟出包走的是同一份清单。
  useEffect(() => {
    if (!open) {
      setPreview(null);
      return;
    }
    let alive = true;
    invoke<DiagPreview>("diagnostics_preview")
      .then((v) => {
        if (alive && v && Array.isArray(v.items)) setPreview(v);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [open]);

  const addFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    setShotMsg("");
    const accepted: Shot[] = [];
    let full = false;
    let failed = "";
    for (const f of files) {
      if (shots.length + accepted.length >= MAX_SHOTS) {
        full = true;
        break;
      }
      const shot = await prepareShot(f, f.name || "clipboard");
      if (shot) accepted.push(shot);
      else if (!failed) failed = f.name || "clipboard";
    }
    if (accepted.length) setShots((prev) => [...prev, ...accepted].slice(0, MAX_SHOTS));
    if (failed) setShotMsg(t("s.diagShotUnreadable", { v0: failed }));
    else if (full) setShotMsg(t("s.diagShotsFull"));
  }, [shots.length]);

  // 粘贴：截图工具按完 Ctrl+V 就进来，不必先存成文件再选。
  useEffect(() => {
    if (!open) return;
    const onPaste = (e: ClipboardEvent) => {
      const files = imageFilesFrom(e.clipboardData);
      if (files.length === 0) return;
      // 只有真的取到图才拦下这次粘贴，否则会把往输入框里粘文字也一起吃掉。
      e.preventDefault();
      void addFiles(files);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [open, addFiles]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  const field =
    "w-full px-[13px] py-[7px] rounded-[var(--rs)] text-[13px] bg-transparent " +
    "text-[var(--ink)] shadow-[inset_0_0_0_1px_var(--line)] outline-none " +
    "focus:shadow-[inset_0_0_0_1px_var(--accent)]";

  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={
          "relative w-full max-w-[460px] max-h-[88vh] overflow-y-auto rounded-[var(--r)] " +
          "bg-[var(--surface)] p-6 shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)] " +
          (dragging ? "outline outline-1 outline-[var(--accent)]" : "")
        }
        onClick={(e) => e.stopPropagation()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!dragging) setDragging(true);
        }}
        onDragLeave={(e) => {
          // 只有真的离开对话框才收起提示；掠过子元素会连发 dragleave。
          if (e.currentTarget.contains(e.relatedTarget as Node)) return;
          setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void addFiles(imageFilesFrom(e.dataTransfer));
        }}
      >
        {dragging ? (
          <div className="pointer-events-none absolute inset-0 z-10 grid place-items-center rounded-[var(--r)] bg-[color-mix(in_srgb,var(--surface)_86%,transparent)]">
            <span className="text-[13px] text-[var(--ink-muted)]">
              {t("s.diagShotsDrop")}
            </span>
          </div>
        ) : null}
        <h3 className="m-0 mb-1 text-[15px] font-semibold">{t("s.diagTitle")}</h3>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--meta)] leading-relaxed">
          {t("s.diagLead")}
        </p>

        <label className="block mb-3">
          <span className="block mb-1.5 text-[12.5px] text-[var(--ink-muted)]">
            {t("s.diagNickname")}
          </span>
          <input
            ref={firstRef}
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            maxLength={64}
            placeholder={t("s.diagNicknameHint")}
            className={field}
          />
        </label>

        <label className="block mb-3">
          <span className="block mb-1.5 text-[12.5px] text-[var(--ink-muted)]">
            {t("s.diagQq")}
          </span>
          <input
            value={qq}
            onChange={(e) => setQq(e.target.value)}
            maxLength={32}
            inputMode="numeric"
            placeholder={t("s.diagQqHint")}
            className={field}
          />
        </label>

        <label className="block mb-3">
          <span className="block mb-1.5 text-[12.5px] text-[var(--ink-muted)]">
            {t("s.diagDesc")}
          </span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={4000}
            rows={4}
            placeholder={t("s.diagDescHint")}
            className={field + " resize-y leading-relaxed"}
          />
        </label>

        <div className="mb-3">
          <span className="block mb-1.5 text-[12.5px] text-[var(--ink-muted)]">
            {t("s.diagShots")}
          </span>
          <p className="m-0 mb-2 text-[12px] text-[var(--meta)] leading-relaxed">
            {t("s.diagShotsHint")}
          </p>
          {shots.length ? (
            <ul className="m-0 mb-2 list-none p-0 flex flex-wrap gap-2">
              {shots.map((sh) => (
                <li key={sh.id} className="relative">
                  <img
                    src={sh.url}
                    alt=""
                    className="block h-[64px] w-[64px] rounded-[var(--rs)] object-cover shadow-[inset_0_0_0_1px_var(--line)]"
                  />
                  <button
                    type="button"
                    title={t("s.diagShotRemove")}
                    aria-label={t("s.diagShotRemove")}
                    onClick={() =>
                      setShots((prev) => prev.filter((x) => x.id !== sh.id))
                    }
                    className="absolute -right-1.5 -top-1.5 h-5 w-5 rounded-full border-0 cursor-pointer bg-[var(--surface)] text-[12px] leading-none text-[var(--meta)] shadow-[0_0_0_1px_var(--line)] hover:text-[var(--ink)]"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => {
              const files = Array.from(e.target.files || []);
              e.target.value = "";
              void addFiles(files);
            }}
          />
          <Btn
            onClick={() => fileRef.current?.click()}
            disabled={shots.length >= MAX_SHOTS}
          >
            {t("s.diagShotsAdd")}
          </Btn>
          {shotMsg ? (
            <p className="m-0 mt-1.5 text-[12px] text-[var(--ink-muted)]">{shotMsg}</p>
          ) : null}
        </div>

        <label className="flex items-start gap-2.5 mb-4 cursor-pointer">
          <input
            type="checkbox"
            checked={withPerf}
            onChange={(e) => setWithPerf(e.target.checked)}
            className="mt-0.5 accent-[var(--accent)]"
          />
          <span className="text-[12.5px] text-[var(--ink-muted)] leading-relaxed">
            {t("s.diagPerf")}
          </span>
        </label>

        {/* 包里已经能看出来的问题。用户当场就能改掉一部分（选错模型、盘满），
            剩下的支援也省一轮问答。没有结论时只留一行，不占地方。 */}
        <div className="mb-4">
          <span className="block mb-1.5 text-[12.5px] text-[var(--ink-muted)]">
            {t("s.diagFindingsTitle")}
          </span>
          {findings === null ? (
            <p className="m-0 text-[12px] text-[var(--meta)]">
              {t("s.diagFindingsChecking")}
            </p>
          ) : findings.length === 0 ? (
            <p className="m-0 text-[12px] text-[var(--meta)]">
              {t("s.diagFindingsNone")}
            </p>
          ) : (
            <FindingList findings={findings} />
          )}
        </div>

        {/* 用户要把这个包发到群里，所以得先说清楚里面有什么、没有什么。
            光说不够 —— 底下那份清单是这句话的凭据，他自己能看一眼。 */}
        <div className="mb-4 rounded-[var(--rs)] bg-[color-mix(in_srgb,var(--ink)_4%,transparent)] px-3 py-2">
          <p className="m-0 text-[12px] text-[var(--meta)] leading-relaxed">
            {t("s.diagPrivacy")}
          </p>
          {preview ? (
            <details className="mt-1.5">
              <summary className="cursor-pointer text-[12px] text-[var(--meta)] select-none">
                {t("s.diagFilesSummary", {
                  a0: String(preview.items.length + shots.length),
                  a1: humanBytes(
                    preview.total_bytes +
                      shots.reduce((n, sh) => n + sh.bytes, 0),
                  ),
                })}
              </summary>
              <ul className="mt-1.5 m-0 list-none p-0 max-h-[168px] overflow-y-auto">
                {[
                  ...preview.items,
                  ...shots.map((sh, i) => ({
                    name: `shots/${String(i + 1).padStart(2, "0")}.${sh.ext}`,
                    bytes: sh.bytes,
                  })),
                ].map((f) => (
                  <li
                    key={f.name}
                    className="flex justify-between gap-3 font-mono text-[11px] text-[var(--meta)] leading-relaxed"
                  >
                    <span className="truncate">{f.name}</span>
                    <span className="shrink-0 tabular-nums">
                      {f.bytes == null
                        ? t("s.diagFilesGenerated")
                        : humanBytes(f.bytes)}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>

        <div className="flex justify-end gap-2.5">
          <Btn onClick={onCancel}>{t("dialog.cancel")}</Btn>
          <Btn
            primary
            onClick={() =>
              onSubmit({
                nickname,
                qq,
                description,
                withPerf,
                shots: shots.map((sh) => ({ ext: sh.ext, data: sh.data })),
              })
            }
          >
            {t("s.4aa2306395")}
          </Btn>
        </div>
      </div>
    </div>
  );
}


/** 清单里的体积。用户看的是量级，不是精确字节数。 */
function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
