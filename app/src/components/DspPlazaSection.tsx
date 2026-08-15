import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Btn } from "./ui";
import { t } from "../i18n/t";

type CatalogPreset = {
  id: string;
  name: string;
  desc?: string;
  author?: string;
  params: Record<string, Record<string, number>>;
  installed?: boolean;
};

/**
 * 广场上的 DSP 预设。
 *
 * 跟音色包不一样：预设直接内嵌在清单里，不走单独下载。一份几百字节，为它
 * 开一次 HTTP、算一次 sha256、走一遍进度条，全是给 55MB 模型设计的流程，
 * 套在这上面纯属折腾。清单本来就会缓存，所以离线也装得上。
 *
 * 因为「装」是瞬间完成的，这里不画进度条 —— 画一个永远一闪而过的进度条，
 * 只会让人以为自己没点上。
 */
export function DspPlazaSection({ reloadToken }: { reloadToken?: number }) {
  const [list, setList] = useState<CatalogPreset[] | null>(null);
  const [msg, setMsg] = useState("");
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await invoke<{ presets: CatalogPreset[] }>("dsp_catalog");
      setList(r.presets || []);
      setMsg("");
    } catch (e) {
      setList([]);
      setMsg(String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, reloadToken]);

  const install = async (p: CatalogPreset) => {
    if (busyId) return;
    setBusyId(p.id);
    try {
      await invoke("dsp_preset_install", { id: p.id });
      await load();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusyId("");
    }
  };

  if (list == null) {
    return (
      <div className="text-[13px] text-[var(--ink-muted)] py-3">
        {t("s.dspPresetsLoading")}
      </div>
    );
  }

  return (
    <>
      <p className="m-0 mb-3 text-[12.5px] text-[var(--ink-muted)] leading-snug">
        {t("s.dspPlazaBlurb")}
      </p>
      {msg ? (
        <div className="text-[12.5px] text-[var(--meta)] mb-2">{msg}</div>
      ) : null}
      {!list.length ? (
        <div className="text-[13px] text-[var(--ink-muted)] py-3">
          {t("s.dspPlazaEmpty")}
        </div>
      ) : (
        <div className="flex flex-col">
          {list.map((p) => (
            <div
              key={p.id}
              className="flex items-center gap-3 py-2.5 border-b border-[var(--hairline)] last:border-b-0"
            >
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-semibold truncate">{p.name}</div>
                <div className="text-[12px] text-[var(--meta)] truncate">
                  {[p.desc, p.author].filter(Boolean).join(" · ")}
                </div>
              </div>
              {p.installed ? (
                <Btn disabled>{t("s.dspPlazaInstalled")}</Btn>
              ) : (
                <Btn disabled={!!busyId} onClick={() => void install(p)}>
                  {busyId === p.id ? t("s.2282c91c77") : t("s.dspPlazaInstall")}
                </Btn>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
