import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import { Field, RangeBar } from "./controls";
import { SegmentControl } from "./SegmentControl";
import { t } from "../i18n/t";

type Tab = "merge" | "change" | "extract" | "onnx";

const FIELD =
  "w-full min-w-0 rounded-[var(--rs)] border border-[var(--hairline)] bg-transparent px-2 py-1.5 text-[13px]";
const PATH =
  "flex-1 min-w-0 truncate text-[12.5px] text-[var(--ink-muted)] font-mono";

function pickPth(set: (p: string) => void) {
  void invoke<string | null>("ckpt_pick", { kind: "pth" }).then((p) => p && set(p));
}

/**
 * 训练窗进阶：原版 ckpt 融合 / 改信息 / 提取小模型 / ONNX 导出。
 * 问号跟设置页一样走 Field 的 tip。
 */
export function CkptAdvanced() {
  const [tab, setTab] = useState<Tab>("merge");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [pathA, setPathA] = useState("");
  const [pathB, setPathB] = useState("");
  const [path, setPath] = useState("");
  const [dest, setDest] = useState("");
  const [name, setName] = useState("");
  const [info, setInfo] = useState("");
  const [alpha, setAlpha] = useState(0.5);
  const [sr, setSr] = useState("48k");
  const [version, setVersion] = useState("v2");
  const [ifF0, setIfF0] = useState(true);

  const run = async (req: Record<string, unknown>) => {
    if (busy) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await invoke<{ message?: string; weights?: string; info?: string; onnx?: string }>(
        "ckpt_run",
        { req },
      );
      setMsg(r.info || r.message || r.weights || r.onnx || t("s.ckptDone"));
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-5 border-t border-[var(--hairline)] pt-4">
      <SegmentControl<Tab>
        value={tab}
        onChange={setTab}
        options={[
          { id: "merge", label: t("s.ckptMerge") },
          { id: "change", label: t("s.ckptChange") },
          { id: "extract", label: t("s.ckptExtract") },
          { id: "onnx", label: t("s.ckptOnnx") },
        ]}
      />
      <div className="mt-4 flex flex-col gap-3.5">
        {tab === "merge" ? (
          <>
            <Field
              label={t("s.ckptModelA")}
              tip={t("s.ckptModelAHint")}
              control={
                <div className="flex items-center gap-2">
                  <span className={PATH}>{pathA || t("s.53e2db7016")}</span>
                  <Btn onClick={() => pickPth(setPathA)}>{t("s.70b208202c")}</Btn>
                </div>
              }
            />
            <Field
              label={t("s.ckptModelB")}
              tip={t("s.ckptModelBHint")}
              control={
                <div className="flex items-center gap-2">
                  <span className={PATH}>{pathB || t("s.53e2db7016")}</span>
                  <Btn onClick={() => pickPth(setPathB)}>{t("s.70b208202c")}</Btn>
                </div>
              }
            />
            <Field
              label={t("s.ckptAlpha")}
              tip={t("s.ckptAlphaHint")}
              control={
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <RangeBar
                      value={alpha}
                      min={0}
                      max={1}
                      step={0.01}
                      defaultValue={0.5}
                      onChange={setAlpha}
                      ariaLabel={t("s.ckptAlpha")}
                    />
                  </div>
                  <span className="w-[44px] text-right text-[13px] tabular-nums">
                    {alpha.toFixed(2)}
                  </span>
                </div>
              }
            />
            <Field
              label={t("s.ckptSaveName")}
              tip={t("s.ckptSaveNameHint")}
              control={
                <input
                  className={FIELD}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              }
            />
            <Field
              label={t("s.ckptInfo")}
              tip={t("s.ckptInfoHint")}
              control={
                <input
                  className={FIELD}
                  value={info}
                  onChange={(e) => setInfo(e.target.value)}
                />
              }
            />
            <div className="flex flex-wrap gap-3">
              <Field
                label={t("s.ab4dae189d")}
                tip={t("s.ckptSrHint")}
                control={
                  <select className={FIELD} value={sr} onChange={(e) => setSr(e.target.value)}>
                    {["32k", "40k", "48k"].map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                }
              />
              <Field
                label={t("s.ckptVersion")}
                tip={t("s.ckptVersionHint")}
                control={
                  <select
                    className={FIELD}
                    value={version}
                    onChange={(e) => setVersion(e.target.value)}
                  >
                    <option value="v2">v2</option>
                    <option value="v1">v1</option>
                  </select>
                }
              />
              <Field
                label={t("s.ckptIfF0")}
                tip={t("s.ckptIfF0Hint")}
                control={
                  <label className="flex items-center gap-2 text-[13px] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={ifF0}
                      onChange={(e) => setIfF0(e.target.checked)}
                    />
                    {t("s.ckptIfF0Yes")}
                  </label>
                }
              />
            </div>
            <div className="flex justify-end">
              <Btn
                primary
                disabled={busy || !pathA || !pathB || !name.trim()}
                onClick={() =>
                  void run({
                    action: "merge",
                    path_a: pathA,
                    path_b: pathB,
                    alpha,
                    name: name.trim(),
                    info,
                    sample_rate: sr,
                    version,
                    if_f0: ifF0,
                  })
                }
              >
                {busy ? t("s.ckptRunning") : t("s.ckptMergeDo")}
              </Btn>
            </div>
          </>
        ) : null}

        {tab === "change" ? (
          <>
            <Field
              label={t("s.ckptModel")}
              tip={t("s.ckptChangeHint")}
              control={
                <div className="flex items-center gap-2">
                  <span className={PATH}>{path || t("s.53e2db7016")}</span>
                  <Btn onClick={() => pickPth(setPath)}>{t("s.70b208202c")}</Btn>
                  <Btn
                    disabled={busy || !path}
                    onClick={() => void run({ action: "show", path })}
                  >
                    {t("s.ckptShow")}
                  </Btn>
                </div>
              }
            />
            <Field
              label={t("s.ckptInfo")}
              tip={t("s.ckptInfoHint")}
              control={
                <input
                  className={FIELD}
                  value={info}
                  onChange={(e) => setInfo(e.target.value)}
                />
              }
            />
            <Field
              label={t("s.ckptSaveAs")}
              tip={t("s.ckptSaveAsHint")}
              control={
                <input
                  className={FIELD}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              }
            />
            <div className="flex justify-end">
              <Btn
                primary
                disabled={busy || !path}
                onClick={() =>
                  void run({
                    action: "change",
                    path,
                    info,
                    name: name.trim(),
                  })
                }
              >
                {busy ? t("s.ckptRunning") : t("s.ckptChangeDo")}
              </Btn>
            </div>
          </>
        ) : null}

        {tab === "extract" ? (
          <>
            <Field
              label={t("s.ckptBigModel")}
              tip={t("s.ckptExtractHint")}
              control={
                <div className="flex items-center gap-2">
                  <span className={PATH}>{path || t("s.53e2db7016")}</span>
                  <Btn onClick={() => pickPth(setPath)}>{t("s.70b208202c")}</Btn>
                </div>
              }
            />
            <Field
              label={t("s.ckptSaveName")}
              tip={t("s.ckptSaveNameHint")}
              control={
                <input
                  className={FIELD}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              }
            />
            <Field
              label={t("s.ckptInfo")}
              tip={t("s.ckptInfoHint")}
              control={
                <input
                  className={FIELD}
                  value={info}
                  onChange={(e) => setInfo(e.target.value)}
                />
              }
            />
            <div className="flex flex-wrap gap-3">
              <Field
                label={t("s.ab4dae189d")}
                tip={t("s.ckptSrHint")}
                control={
                  <select className={FIELD} value={sr} onChange={(e) => setSr(e.target.value)}>
                    {["32k", "40k", "48k"].map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                }
              />
              <Field
                label={t("s.ckptVersion")}
                tip={t("s.ckptVersionHint")}
                control={
                  <select
                    className={FIELD}
                    value={version}
                    onChange={(e) => setVersion(e.target.value)}
                  >
                    <option value="v2">v2</option>
                    <option value="v1">v1</option>
                  </select>
                }
              />
              <Field
                label={t("s.ckptIfF0")}
                tip={t("s.ckptIfF0Hint")}
                control={
                  <label className="flex items-center gap-2 text-[13px] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={ifF0}
                      onChange={(e) => setIfF0(e.target.checked)}
                    />
                    {t("s.ckptIfF0Yes")}
                  </label>
                }
              />
            </div>
            <div className="flex justify-end">
              <Btn
                primary
                disabled={busy || !path || !name.trim()}
                onClick={() =>
                  void run({
                    action: "extract",
                    path,
                    name: name.trim(),
                    info,
                    sample_rate: sr,
                    version,
                    if_f0: ifF0,
                  })
                }
              >
                {busy ? t("s.ckptRunning") : t("s.ckptExtractDo")}
              </Btn>
            </div>
          </>
        ) : null}

        {tab === "onnx" ? (
          <>
            <Field
              label={t("s.ckptModel")}
              tip={t("s.ckptOnnxHint")}
              control={
                <div className="flex items-center gap-2">
                  <span className={PATH}>{path || t("s.53e2db7016")}</span>
                  <Btn onClick={() => pickPth(setPath)}>{t("s.70b208202c")}</Btn>
                </div>
              }
            />
            <Field
              label={t("s.ckptOnnxOut")}
              tip={t("s.ckptOnnxOutHint")}
              control={
                <div className="flex items-center gap-2">
                  <span className={PATH}>{dest || t("s.ckptOnnxOutAuto")}</span>
                  <Btn
                    onClick={() => {
                      void invoke<string | null>("ckpt_pick", { kind: "onnx" }).then(
                        (p) => p && setDest(p),
                      );
                    }}
                  >
                    {t("s.70b208202c")}
                  </Btn>
                </div>
              }
            />
            <div className="flex justify-end">
              <Btn
                primary
                disabled={busy || !path}
                onClick={() => void run({ action: "onnx", path, dest })}
              >
                {busy ? t("s.ckptRunning") : t("s.ckptOnnxDo")}
              </Btn>
            </div>
          </>
        ) : null}

        {msg ? (
          <p className="m-0 text-[12.5px] text-[var(--ink-muted)] break-all whitespace-pre-wrap">
            {msg}
          </p>
        ) : null}
      </div>
    </div>
  );
}
