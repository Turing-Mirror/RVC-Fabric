import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn } from "./ui";
import { t } from "../i18n/t";

/**
 * 申请专业优化：照着稿子念一遍，软件打包寄出去。
 *
 * 为什么要念**指定的**稿子，而不是让用户随便说：收上来的东西五花八门 ——
 * 有人念三个字，有人全是气声，有人背景里在放歌。同一段文本才能在用户之间横向
 * 比较，也才能保证音素、语调、长句这几样都覆盖到。
 *
 * 三种语言由用户自己选，念一种也能寄。稿子和录音状态都从壳里取
 * （`consult_state`），不在前端另写一份 —— 两边各存一份文本，
 * 迟早有一边改了另一边没改，而寄出去的和屏幕上显示的就不是同一段话了。
 */

type Script = {
  langs: string[];
  [lang: string]:
    | string[]
    | { label: string; lines: string[]; romaji?: string[] }
    | undefined;
};

type ConsultState = {
  langs: string[];
  recorded: Record<string, { path: string; bytes: number } | null>;
  script: Script;
};

type LangBlock = { label: string; lines: string[]; romaji?: string[] };

function blockOf(script: Script | undefined, lang: string): LangBlock | null {
  const b = script?.[lang];
  if (!b || Array.isArray(b)) return null;
  return b;
}

export function ConsultDialog({
  open,
  onCancel,
  onDone,
}: {
  open: boolean;
  onCancel: () => void;
  onDone: (path: string) => void;
}) {
  const [st, setSt] = useState<ConsultState | null>(null);
  const [lang, setLang] = useState("zh");
  const [recording, setRecording] = useState("");
  const [level, setLevel] = useState(0);
  const [seconds, setSeconds] = useState(0);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  const refresh = useCallback(async () => {
    try {
      const v = await invoke<ConsultState>("consult_state");
      setSt(v);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setErr("");
    setBusy("");
    setNote("");
    void refresh();
  }, [open, refresh]);

  // 录音进度由壳推送（和「语音转换」页那个录音器是同一个）。
  useEffect(() => {
    if (!open) return;
    const un = listen<{ phase: string; db?: number; sec?: number; message?: string }>(
      "sts-record",
      (e) => {
        const p = e.payload;
        if (typeof p.sec === "number") setSeconds(p.sec);
        if (typeof p.db === "number") setLevel(p.db);
        if (p.phase === "done" || p.phase === "error") {
          setRecording("");
          setSeconds(0);
          setLevel(0);
          if (p.phase === "error" && p.message) setErr(p.message);
          void refresh();
        }
      },
    );
    return () => {
      void un.then((f) => f());
    };
  }, [open, refresh]);

  if (!open) return null;

  const block = blockOf(st?.script, lang);
  const langs = st?.langs ?? ["zh", "en", "ja"];
  const doneCount = langs.filter((l) => st?.recorded?.[l]).length;

  const startRec = async (l: string) => {
    setErr("");
    setRecording(l);
    setSeconds(0);
    try {
      await invoke("consult_record_start", { lang: l });
    } catch (e) {
      setRecording("");
      setErr(String(e));
    }
  };

  const stopRec = () => {
    void invoke("consult_record_stop").catch(() => {});
  };

  const build = async () => {
    setErr("");
    setBusy(t("s.consultBuilding"));
    try {
      const r = await invoke<{ ok: boolean; path: string }>("consult_build", { note });
      setBusy("");
      onDone(r.path);
    } catch (e) {
      setBusy("");
      setErr(String(e));
    }
  };

  const clearAll = async () => {
    try {
      const v = await invoke<ConsultState>("consult_clear");
      setSt(v);
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={busy ? undefined : onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={
          "relative w-full max-w-[560px] max-h-[88vh] overflow-y-auto rounded-[var(--r)] " +
          "bg-[var(--surface)] p-6 shadow-[0_22px_56px_-18px_rgba(20,26,33,.34)]"
        }
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-[16px] font-semibold m-0 mb-1">{t("s.dd41f552d6")}</h3>
        <p className="text-[12.5px] text-[var(--help)] leading-relaxed mt-0 mb-4">
          {t("s.consultIntro")}
        </p>

        {/* 语言选择。念一种就能寄，推荐三种都念。 */}
        <div className="flex gap-2 mb-3 flex-wrap">
          {langs.map((l) => {
            const b = blockOf(st?.script, l);
            const done = Boolean(st?.recorded?.[l]);
            return (
              <Btn key={l} on={l === lang} onClick={() => setLang(l)}>
                {(b?.label ?? l) + (done ? " ✓" : "")}
              </Btn>
            );
          })}
        </div>

        {/* 稿子。四段分别覆盖短句、音素、书面语、长句音色漂移。 */}
        <ol className="text-[13px] leading-[1.9] pl-5 m-0 mb-4">
          {(block?.lines ?? []).map((line, i) => (
            <li key={i} className="mb-2">
              <span className="whitespace-pre-line">{line}</span>
              {block?.romaji?.[i] ? (
                <div className="text-[11.5px] text-[var(--meta)] whitespace-pre-line mt-0.5">
                  {block.romaji[i]}
                </div>
              ) : null}
            </li>
          ))}
        </ol>

        <div className="flex items-center gap-3 flex-wrap mb-4">
          {/* 录音时**不管当前看的是哪一页**都显示停止按钮。
              按语言页判断的话，用户录着中文顺手翻到英文那一页看稿子，
              停止按钮就没了，而录音还在继续。 */}
          {recording ? (
            <>
              <Btn primary onClick={stopRec}>
                {t("s.consultStop")}
              </Btn>
              <span className="text-[12.5px] text-[var(--meta)]">
                {t("s.consultRecording", {
                  v0: blockOf(st?.script, recording)?.label ?? recording,
                })}
              </span>
              <span className="text-[12.5px] text-[var(--meta)] tabular-nums">
                {seconds.toFixed(1)}s · {level.toFixed(0)} dB
              </span>
            </>
          ) : (
            <Btn primary disabled={Boolean(busy)} onClick={() => void startRec(lang)}>
              {st?.recorded?.[lang] ? t("s.consultReRecord") : t("s.consultRecord")}
            </Btn>
          )}
          {doneCount > 0 ? (
            <Btn disabled={Boolean(recording) || Boolean(busy)} onClick={() => void clearAll()}>
              {t("s.consultClear")}
            </Btn>
          ) : null}
        </div>

        <label className="block text-[12.5px] text-[var(--help)] mb-1">
          {t("s.consultNote")}
        </label>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          className="w-full text-[13px] px-3 py-2 rounded-[var(--rs)] bg-transparent text-[var(--ink)] shadow-[inset_0_0_0_1px_var(--line)] outline-none resize-none mb-4"
        />

        {err ? (
          <p className="text-[12px] text-[var(--danger,#c0392b)] mt-0 mb-3 break-all">{err}</p>
        ) : null}

        <div className="flex gap-2 justify-end items-center flex-wrap">
          {busy ? (
            <span className="text-[12.5px] text-[var(--meta)] mr-auto">{busy}</span>
          ) : (
            <span className="text-[12.5px] text-[var(--meta)] mr-auto">
              {t("s.consultProgress", { v0: String(doneCount), v1: String(langs.length) })}
            </span>
          )}
          <Btn disabled={Boolean(busy)} onClick={onCancel}>
            {t("s.4d0b4688c7")}
          </Btn>
          <Btn
            primary
            disabled={doneCount === 0 || Boolean(busy) || Boolean(recording)}
            busy={Boolean(busy)}
            onClick={() => void build()}
          >
            {t("s.consultBuild")}
          </Btn>
        </div>
      </div>
    </div>
  );
}
