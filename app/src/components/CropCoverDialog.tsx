import { useCallback, useEffect, useRef, useState } from "react";
import { Btn } from "./ui";
import { t } from "../i18n/t";
import {
  coverSrc,
  pickCoverImage,
  setVoiceCover,
  type VoiceModel,
} from "../lib/voices";

/**
 * 封面裁剪对话框（模型页「⋯」→「更换封面」）。
 *
 * 交互移植自发布仓里的 cover-tool 网页：滚轮缩放 / 拖动平移，选区可拖动、
 * 八个手柄缩放，4:3 · 1:1 · 自由比例；输出统一短边 512 的 jpg（质量 0.85）。
 * 原工具的 git 推送、CNB 附件上传在软件内一律不存在 —— 这里只把裁好的图
 * 写进该音色自己的目录，纯本地操作。
 *
 * 右侧保留「软件内显示模拟」：4:3 卡片 + contain。第三方竖立绘不裁剪时
 * 在卡片里只剩一小条，裁完才撑满 —— 这个对比就是本对话框存在的理由。
 */

type Ratio = "4:3" | "1:1" | "free";

const RATIO_PAIRS: Record<Exclude<Ratio, "free">, [number, number]> = {
  "4:3": [4, 3],
  "1:1": [1, 1],
};

function loadImageEl(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("image load failed"));
    img.src = src;
  });
}

export function CropCoverDialog({
  model,
  onClose,
  onSaved,
}: {
  model: VoiceModel;
  onClose: () => void;
  /** 保存成功后回调（参数是给页面 toast 的一句话）。 */
  onSaved: (message?: string) => void | Promise<void>;
}) {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [srcLabel, setSrcLabel] = useState("");
  const [ratio, setRatio] = useState<Ratio>("4:3");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [preview, setPreview] = useState({ after: "", before: "", note: "" });

  const wrapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);
  // 变换与选区放 ref 里：拖动是每帧的事，不该牵着 React 重渲染。
  const tf = useRef({ scale: 1, ox: 0, oy: 0 });
  const crop = useRef({ x: 0, y: 0, w: 0, h: 0 });
  const ratioRef = useRef<Ratio>("4:3");
  const imgRef = useRef<HTMLImageElement | null>(null);

  const clampCrop = useCallback(() => {
    const im = imgRef.current;
    if (!im) return;
    const iw = im.naturalWidth;
    const ih = im.naturalHeight;
    const MIN = 8;
    const c = crop.current;
    c.w = Math.min(Math.max(c.w, MIN), iw);
    c.h = Math.min(Math.max(c.h, MIN), ih);
    c.x = Math.min(Math.max(c.x, 0), Math.max(0, iw - c.w));
    c.y = Math.min(Math.max(c.y, 0), Math.max(0, ih - c.h));
  }, []);

  const applyRatio = useCallback(() => {
    const r = ratioRef.current;
    if (r === "free") return;
    const im = imgRef.current;
    if (!im) return;
    const [rw, rh] = RATIO_PAIRS[r];
    const iw = im.naturalWidth;
    const ih = im.naturalHeight;
    let { x, y, w, h } = crop.current;
    const cx = x + w / 2;
    const cy = y + h / 2;
    if (w / h > rw / rh) h = (w * rh) / rw;
    else w = (h * rw) / rh;
    x = cx - w / 2;
    y = cy - h / 2;
    if (x < 0) {
      x = 0;
      w = Math.min(w, iw);
    }
    if (y < 0) {
      y = 0;
      h = Math.min(h, ih);
    }
    if (x + w > iw) {
      w = iw - x;
      h = (w * rh) / rw;
    }
    if (y + h > ih) {
      h = ih - y;
      w = (h * rw) / rh;
    }
    crop.current = { x, y, w, h };
    clampCrop();
  }, [clampCrop]);

  const positionBox = useCallback(() => {
    const box = boxRef.current;
    if (!box) return;
    const { scale, ox, oy } = tf.current;
    const c = crop.current;
    box.style.left = `${ox + c.x * scale}px`;
    box.style.top = `${oy + c.y * scale}px`;
    box.style.width = `${c.w * scale}px`;
    box.style.height = `${c.h * scale}px`;
  }, []);

  const draw = useCallback(() => {
    const cv = canvasRef.current;
    const im = imgRef.current;
    if (!cv || !im) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const { scale, ox, oy } = tf.current;
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = "#18181b";
    ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(scale, scale);
    ctx.drawImage(im, 0, 0, im.naturalWidth, im.naturalHeight);
    ctx.restore();
  }, []);

  const renderCrop = useCallback(() => {
    const im = imgRef.current;
    if (!im) return null;
    let { x, y, w, h } = crop.current;
    x = Math.round(x);
    y = Math.round(y);
    w = Math.max(1, Math.round(w));
    h = Math.max(1, Math.round(h));
    // 裁出选区，短边统一到 512（不足放大、超出缩小），保持比例不拉伸。
    const k = 512 / Math.min(w, h);
    const outW = Math.max(1, Math.round(w * k));
    const outH = Math.max(1, Math.round(h * k));
    const cv = document.createElement("canvas");
    cv.width = outW;
    cv.height = outH;
    const g = cv.getContext("2d");
    if (!g) return null;
    g.imageSmoothingQuality = "high";
    g.drawImage(im, x, y, w, h, 0, 0, outW, outH);
    return { canvas: cv, w: outW, h: outH };
  }, []);

  const updatePreview = useCallback(() => {
    const out = renderCrop();
    if (!out) return;
    setPreview({
      after: out.canvas.toDataURL("image/jpeg", 0.85),
      before: imgRef.current?.src || "",
      note: t("crop.previewNote", { v0: `${out.w}×${out.h}` }),
    });
  }, [renderCrop]);

  const fitCanvas = useCallback(() => {
    const wrap = wrapRef.current;
    const cv = canvasRef.current;
    const im = imgRef.current;
    if (!wrap || !cv || !im) return;
    const cw = Math.max(120, wrap.clientWidth);
    const iw = im.naturalWidth;
    const ih = im.naturalHeight;
    cv.width = cw;
    cv.height = Math.max(40, Math.round((cw * ih) / iw));
    const vs = Math.min(cv.width / iw, cv.height / ih);
    tf.current = {
      scale: vs,
      ox: (cv.width - iw * vs) / 2,
      oy: (cv.height - ih * vs) / 2,
    };
    draw();
    positionBox();
  }, [draw, positionBox]);

  const startEditor = useCallback(
    (im: HTMLImageElement) => {
      imgRef.current = im;
      const r = ratioRef.current;
      const iw = im.naturalWidth;
      const ih = im.naturalHeight;
      let w: number;
      let h: number;
      if (r === "free") {
        w = iw;
        h = ih;
      } else {
        const [rw, rh] = RATIO_PAIRS[r];
        if (iw / ih > rw / rh) {
          h = ih;
          w = (ih * rw) / rh;
        } else {
          w = iw;
          h = (iw * rh) / rw;
        }
      }
      crop.current = { x: (iw - w) / 2, y: Math.max(0, (ih - h) * 0.3), w, h };
      // 脸通常偏上：初始选区贴向中上。
      clampCrop();
      setImg(im);
      requestAnimationFrame(() => {
        fitCanvas();
        updatePreview();
      });
    },
    [clampCrop, fitCanvas, updatePreview],
  );

  const openPicker = useCallback(async () => {
    setErr("");
    try {
      const p = await pickCoverImage();
      if (!p) return;
      const el = await loadImageEl(coverSrc(p));
      setSrcLabel(p.split(/[\\/]/).pop() || p);
      startEditor(el);
    } catch (e) {
      setErr(String(e));
    }
  }, [startEditor]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  // 画布跟随窗口宽度重排。
  useEffect(() => {
    if (!img) return;
    const ro = new ResizeObserver(() => {
      fitCanvas();
    });
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, [img, fitCanvas]);

  const zoomAt = (factor: number, mx: number, my: number) => {
    const cur = tf.current;
    const ns = Math.min(20, Math.max(0.02, cur.scale * factor));
    const k = ns / cur.scale;
    tf.current = {
      scale: ns,
      ox: mx - (mx - cur.ox) * k,
      oy: my - (my - cur.oy) * k,
    };
    draw();
    positionBox();
  };

  const canvasPoint = (e: React.PointerEvent | React.WheelEvent) => {
    const cv = canvasRef.current!;
    const rect = cv.getBoundingClientRect();
    const cx = ((e.clientX - rect.left) / rect.width) * cv.width;
    const cy = ((e.clientY - rect.top) / rect.height) * cv.height;
    return { cx, cy };
  };

  const onCanvasPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!imgRef.current || e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    e.currentTarget.style.cursor = "grabbing";
    const start = { x: e.clientX, y: e.clientY, ox: tf.current.ox, oy: tf.current.oy };
    const move = (ev: PointerEvent) => {
      tf.current.ox = start.ox + (ev.clientX - start.x);
      tf.current.oy = start.oy + (ev.clientY - start.y);
      draw();
      positionBox();
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      const cvs = canvasRef.current;
      if (cvs) cvs.style.cursor = "grab";
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const onWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    if (!imgRef.current) return;
    e.preventDefault();
    const { cx, cy } = canvasPoint(e);
    zoomAt(e.deltaY < 0 ? 1.15 : 0.87, cx, cy);
  };

  const onBoxPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!imgRef.current) return;
    e.stopPropagation();
    e.preventDefault();
    const target = e.target as HTMLElement;
    const handle = target.closest("[data-h]");
    const mode: string = handle
      ? (handle as HTMLElement).dataset.h || "move"
      : "move";
    const p0 = { x: e.clientX, y: e.clientY };
    const c0 = { ...crop.current };
    const s0 = tf.current.scale;
    const move = (ev: PointerEvent) => {
      const dx = (ev.clientX - p0.x) / s0;
      const dy = (ev.clientY - p0.y) / s0;
      let c = { ...c0 };
      const r = ratioRef.current;
      if (mode === "move") {
        c.x = c0.x + dx;
        c.y = c0.y + dy;
      } else {
        let rw: number | null = null;
        let rh: number | null = null;
        if (r !== "free") [rw, rh] = RATIO_PAIRS[r];
        let nx = c0.x;
        let ny = c0.y;
        let nw = c0.w;
        let nh = c0.h;
        if (mode.includes("e")) nw = c0.w + dx;
        if (mode.includes("s")) nh = c0.h + dy;
        if (mode.includes("w")) {
          nw = c0.w - dx;
          nx = c0.x + dx;
        }
        if (mode.includes("n")) {
          nh = c0.h - dy;
          ny = c0.y + dy;
        }
        if (rw && rh) {
          if (mode.includes("e") || mode.includes("w")) nh = (nw * rh) / rw;
          else nw = (nh * rw) / rh;
          if (mode.includes("n")) ny = c0.y + (c0.h - nh);
          if (mode.includes("w")) nx = c0.x + (c0.w - nw);
        }
        c = { x: nx, y: ny, w: nw, h: nh };
      }
      crop.current = c;
      clampCrop();
      applyRatio();
      positionBox();
      updatePreview();
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const changeRatio = (r: Ratio) => {
    ratioRef.current = r;
    setRatio(r);
    applyRatio();
    positionBox();
    updatePreview();
  };

  const save = async () => {
    if (!model.dir || busy) return;
    const out = renderCrop();
    if (!out) return;
    setBusy(true);
    setErr("");
    try {
      await setVoiceCover(model.dir, out.canvas.toDataURL("image/jpeg", 0.85));
      await onSaved(t("models.coverSaved"));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[92] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={() => {
        if (!busy) onClose();
      }}
    >
      <div
        className="w-full max-w-[860px] max-h-[86vh] overflow-auto rounded-[var(--r)] bg-[var(--surface)] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 mb-1">
          <h3 className="m-0 text-[16px] font-semibold">{t("crop.title")}</h3>
          <Btn onClick={onClose}>{t("s.6c14bd7f6f")}</Btn>
        </div>
        <p className="m-0 mb-3 text-[12.5px] text-[var(--ink-muted)]">
          {t("crop.lead", { v0: model.name })}
        </p>

        {!img ? (
          <div className="flex flex-col items-start gap-3 py-8">
            <Btn primary onClick={() => void openPicker()}>
              {t("crop.pick")}
            </Btn>
            <span className="text-[12px] text-[var(--meta)]">{t("crop.pickHint")}</span>
            {srcLabel ? (
              <span className="text-[12px] text-[var(--meta)]">{srcLabel}</span>
            ) : null}
          </div>
        ) : (
          <div className="grid gap-4 grid-cols-1 min-[900px]:grid-cols-[minmax(0,1fr)_300px]">
            <div>
              <div
                ref={wrapRef}
                className="relative w-full rounded-lg overflow-hidden bg-[#111] touch-none select-none"
              >
                <canvas
                  ref={canvasRef}
                  onPointerDown={onCanvasPointerDown}
                  onWheel={onWheel}
                  className="block w-full h-auto cursor-grab"
                />
                <div
                  ref={boxRef}
                  onPointerDown={onBoxPointerDown}
                  className="absolute border-2 border-white shadow-[0_0_0_9999px_rgba(0,0,0,0.5)] cursor-move"
                >
                  <div className="absolute left-0 right-0 top-1/3 h-px bg-white/55" />
                  <div className="absolute left-0 right-0 top-2/3 h-px bg-white/55" />
                  <div className="absolute top-0 bottom-0 left-1/3 w-px bg-white/55" />
                  <div className="absolute top-0 bottom-0 left-2/3 w-px bg-white/55" />
                  {[
                    ["nw", "-top-[7px] -left-[7px] cursor-nwse-resize"],
                    ["n", "-top-[7px] left-1/2 -translate-x-1/2 cursor-ns-resize"],
                    ["ne", "-top-[7px] -right-[7px] cursor-nesw-resize"],
                    ["e", "top-1/2 -right-[7px] -translate-y-1/2 cursor-ew-resize"],
                    ["se", "-bottom-[7px] -right-[7px] cursor-nwse-resize"],
                    ["s", "-bottom-[7px] left-1/2 -translate-x-1/2 cursor-ns-resize"],
                    ["sw", "-bottom-[7px] -left-[7px] cursor-nesw-resize"],
                    ["w", "top-1/2 -left-[7px] -translate-y-1/2 cursor-ew-resize"],
                  ].map(([h, cls]) => (
                    <span
                      key={h}
                      data-h={h}
                      className={`absolute w-3 h-3 bg-white border border-neutral-700 rounded-[3px] ${cls}`}
                    />
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-2 mt-2.5 flex-wrap">
                <Btn onClick={() => zoomAt(1.3, (canvasRef.current?.width || 0) / 2, (canvasRef.current?.height || 0) / 2)}>
                  {t("crop.zoomIn")}
                </Btn>
                <Btn onClick={() => zoomAt(1 / 1.3, (canvasRef.current?.width || 0) / 2, (canvasRef.current?.height || 0) / 2)}>
                  {t("crop.zoomOut")}
                </Btn>
                <Btn onClick={fitCanvas}>{t("crop.fit")}</Btn>
                <Btn
                  onClick={() => {
                    tf.current = { scale: 1, ox: 0, oy: 0 };
                    draw();
                    positionBox();
                  }}
                >
                  {t("crop.zoom100")}
                </Btn>
                <span className="ml-2 text-[12px] text-[var(--meta)]">
                  {t("crop.ratioLabel")}
                </span>
                {(["4:3", "1:1", "free"] as Ratio[]).map((r) => (
                  <Btn key={r} on={ratio === r} onClick={() => changeRatio(r)}>
                    {r === "free" ? t("crop.free") : r}
                  </Btn>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <div className="rounded-[var(--rs)] shadow-[inset_0_0_0_1px_var(--line)] p-2.5">
                <div className="text-[12px] text-[var(--meta)] mb-1.5">
                  {t("crop.previewAfter")}
                </div>
                <div className="aspect-[4/3] rounded-md overflow-hidden bg-[color-mix(in_srgb,var(--ink)_7%,transparent)]">
                  {preview.after ? (
                    <img src={preview.after} alt="" className="w-full h-full object-contain" />
                  ) : null}
                </div>
                {preview.note ? (
                  <div className="text-[11.5px] text-[var(--meta)] mt-1.5">{preview.note}</div>
                ) : null}
              </div>
              <div className="rounded-[var(--rs)] shadow-[inset_0_0_0_1px_var(--line)] p-2.5">
                <div className="text-[12px] text-[var(--meta)] mb-1.5">
                  {t("crop.previewBefore")}
                </div>
                <div className="aspect-[4/3] rounded-md overflow-hidden bg-[color-mix(in_srgb,var(--ink)_7%,transparent)]">
                  {preview.before ? (
                    <img src={preview.before} alt="" className="w-full h-full object-contain" />
                  ) : null}
                </div>
                <div className="text-[11.5px] text-[var(--meta)] mt-1.5">
                  {t("crop.previewBeforeNote")}
                </div>
              </div>
            </div>
          </div>
        )}

        {err ? (
          <p className="mt-3 mb-0 text-[12.5px] text-[#b8534f] break-all">{err}</p>
        ) : null}

        <div className="mt-4 flex items-center gap-2.5 flex-wrap">
          {img ? (
            <>
              <Btn primary busy={busy} onClick={() => void save()}>
                {busy ? t("crop.saving") : t("crop.save")}
              </Btn>
              <Btn onClick={() => void openPicker()}>{t("crop.repick")}</Btn>
            </>
          ) : null}
          <span className="ml-auto text-[11.5px] text-[var(--meta)]">
            {t("crop.localNote")}
          </span>
        </div>
      </div>
    </div>
  );
}
