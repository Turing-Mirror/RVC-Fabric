import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Btn, HelpMark } from "./ui";
import { ErrorNote } from "./ErrorNote";
import { RangeBar } from "./controls";
import { openDownloadModels } from "../lib/downloadModels";
import { openHelpSection } from "../lib/helpNav";
import { ToolActions, ToolBody } from "./ToolWindow";
import { t } from "../i18n/t";
import { pickPath } from "../lib/nativeDialog";

type Status = {
  runtime_ready?: boolean;
  worker_present?: boolean;
  core_present?: boolean;
  model_dir?: string;
  models?: string[];
  busy?: boolean;
};

type Progress = {
  phase: "start" | "run" | "done" | "error";
  done: number;
  total: number;
  message: string;
};

const ROW = "flex items-center gap-3 py-2.5";
/**
 * 表单左边那一列。
 *
 * 宽度原来是照着中文标签配的，四个汉字五十来像素刚好塞得下。八种语言里
 * 这就不成立了：法语的「Enregistrer les modèles dans」有两百多像素，会在
 * 词中间断成三行；连中文的「导出格式」加上后面那个问号图标也已经超了。
 * 放宽到能装下绝大多数语言，剩下几个特别长的折成两行，配 leading-tight
 * 看起来是有意为之，而不是挤坏了。
 */
const LABEL = "w-[96px] shrink-0 text-[13px] leading-tight";
const FIELD =
  "rounded-[var(--rs)] border border-[var(--hairline)] bg-transparent px-2 py-1.5 text-[13px]";
const PATH =
  "flex-1 min-w-0 truncate text-[12.5px] text-[var(--ink-muted)] font-mono";
const FORMATS = ["wav", "flac", "mp3", "m4a"] as const;

/**
 * 人声分离（PyMSS）。
 *
 * 一次一个文件，没有队列 —— 分离很吃显存，排队跑只会让人以为卡死了。要批量
 * 的话再说，先把单个跑通。
 */
export function SeparatePanel() {
  const [st, setSt] = useState<Status>({});
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [model, setModel] = useState("");
  const [fmt, setFmt] = useState<(typeof FORMATS)[number]>("wav");
  const [agg, setAgg] = useState(10);
  const [prog, setProg] = useState<Progress | null>(null);
  const [msg, setMsg] = useState("");
  // msg 这一格既报错也报成功。「复制完整错误 / 打开日志」只在报错时才该出现，
  // 所以两条路分开走，别让 ErrorNote 去猜。
  const [msgErr, setMsgErr] = useState(false);
  const showErr = (v: string) => {
    setMsgErr(true);
    setMsg(v);
  };
  const showInfo = (v: string) => {
    setMsgErr(false);
    setMsg(v);
  };

  const [running, setRunning] = useState(false);
  const runningRef = useRef(false);

  const load = async () => {
    try {
      const s = await invoke<Status>("separate_status");
      setSt(s);
      if (!model && s.models?.length) setModel(s.models[0]);
    } catch (e) {
      showErr(String(e));
    }
  };

  useEffect(() => {
    void load();
    // listen() 是异步的，弹窗在它 resolve 之前关掉就会把注销句柄丢掉，
    // 每开一次泄漏一个监听。和 App.tsx 里一样的处理。
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<Progress>("separate-progress", (ev) => {
      setProg(ev.payload);
      if (ev.payload.phase === "error") showErr(ev.payload.message);
    }).then((fn) => {
      if (disposed) fn();
      else un = fn;
    });
    return () => {
      disposed = true;
      un?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 开一次窗只挂一次
  }, []);

  const pick = async (dir: boolean, inputFolder = false) => {
    try {
      const p = await pickPath<string | null>("separate_pick", {
        dir,
        inputFolder,
      }, t("s.pickBusyFolder"));
      if (!p) return;
      if (dir) setOutput(p);
      else setInput(p);
    } catch (e) {
      showErr(String(e));
    }
  };

  const start = async () => {
    if (runningRef.current) return;
    showInfo("");
    setProg(null);
    runningRef.current = true;
    setRunning(true);
    try {
      const r = await invoke<{ files?: string[] }>("separate_start", {
        input,
        output,
        model,
        format: fmt,
        aggression: agg,
      });
      showInfo(t("s.8efd7ca6b1", { v0: r.files?.length ?? 0 }));
    } catch (e) {
      showErr(String(e));
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  };

  const needModels = !!st.runtime_ready && !!st.worker_present && !st.models?.length;
  const needCore =
    !!st.runtime_ready && !!st.worker_present && st.core_present === false;
  const blocked = !st.runtime_ready
    ? t("s.bc45fc14b1")
    : !st.worker_present
      ? t("s.92ba5de60f")
      : needCore
        ? t("s.6ff3d83b8f")
        : needModels
          ? t("s.f8893054c2")
          : "";

  const pct = prog?.total ? Math.round((prog.done / prog.total) * 100) : 0;

  return (
    <ToolBody>
        <div className="mb-1 flex items-center justify-between gap-2">
          <h3 className="m-0 text-[17px] font-semibold">{t("s.8fd038283b")}</h3>
          <Btn onClick={() => openHelpSection("separate")}>{t("s.trainOpenHelp")}</Btn>
        </div>
        <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)]">{t("s.497e7d9af6")}</p>

        {blocked ? (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <p className="m-0 text-[13px] text-[#b8534f]">{blocked}</p>
            {needModels || needCore ? (
              <Btn
                onClick={() => openDownloadModels({ filter: "separate" })}
              >{t("s.7a218555fd")}</Btn>
            ) : null}
          </div>
        ) : (
          <div className="mb-3 flex justify-end">
            <Btn onClick={() => openDownloadModels({ filter: "separate" })}>{t("s.1252c81119")}</Btn>
          </div>
        )}

        <div className="border-t border-[var(--hairline)]">
          <div className={ROW}>
            <span className={LABEL}>{t("s.e8850440f2")}</span>
            <span className={PATH}>{input || t("s.53e2db7016")}</span>
            <Btn onClick={() => void pick(false)}>{t("s.70b208202c")}</Btn>
            <Btn onClick={() => void pick(false, true)}>{t("s.sepFolder")}</Btn>
          </div>
          <div className={ROW}>
            <span className={LABEL}>{t("s.a0bc984876")}</span>
            <span className={PATH}>{output || t("s.53e2db7016")}</span>
            <Btn onClick={() => void pick(true)}>{t("s.70b208202c")}</Btn>
          </div>
          <div className={ROW}>
            <span className={LABEL}>{t("s.98fd0cbd9c")}</span>
            <select
              className="flex-1 min-w-0 rounded-[var(--rs)] border border-[var(--hairline)] bg-transparent px-2 py-1.5 text-[13px]"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {(st.models || []).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
              {!st.models?.length ? <option value="">{t("s.6238bf9ad5")}</option> : null}
            </select>
          </div>
          <div className={ROW}>
            <span className={`${LABEL} flex items-center gap-1.5`}>
              {t("s.sepFormat")}
              <HelpMark title={t("s.sepFormatHint")} />
            </span>
            <select
              className={FIELD}
              value={fmt}
              onChange={(e) => setFmt(e.target.value as (typeof FORMATS)[number])}
            >
              {FORMATS.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
          <div className={ROW}>
            <span className={`${LABEL} flex items-center gap-1.5`}>
              {t("s.sepAgg")}
              <HelpMark title={t("s.sepAggHint")} />
            </span>
            <div className="flex-1">
              <RangeBar
                value={agg}
                min={0}
                max={20}
                step={1}
                defaultValue={10}
                onChange={setAgg}
                ariaLabel={t("s.sepAgg")}
              />
            </div>
            <span className="w-[36px] text-right text-[13px] tabular-nums">{agg}</span>
          </div>
        </div>

        {prog ? (
          <div className="mt-4">
            <div className="h-1 w-full overflow-hidden rounded bg-[color-mix(in_srgb,var(--ink)_10%,transparent)]">
              <div
                className="h-full bg-[var(--accent)] transition-[width] duration-200"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="m-0 mt-2 text-[12px] text-[var(--meta)]">
              {prog.message} {prog.phase === "run" ? `${pct}%` : ""}
            </p>
          </div>
        ) : null}

        {msg ? (
          <ErrorNote text={msg} error={msgErr} />
        ) : null}

        <ToolActions>
          <div className="ml-auto flex items-center gap-2.5">
            {running ? (
              <Btn onClick={() => void invoke("separate_cancel")}>{t("s.4d0b4688c7")}</Btn>
            ) : (
              <Btn
                disabled={!output}
                onClick={() => void invoke("separate_reveal", { path: output })}
              >
                {t("s.344a481fa0")}
              </Btn>
            )}
            <Btn
              primary
              busy={running}
              disabled={running || !!blocked || !input || !output}
              onClick={() => void start()}
            >
              {running ? t("s.2282c91c77") : t("s.8c57156c9d")}
            </Btn>
          </div>
        </ToolActions>

    </ToolBody>
  );
}
