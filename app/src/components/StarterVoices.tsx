import { useEffect, useState } from "react";
import { Btn } from "./ui";
import { t } from "../i18n/t";
import { useI18n } from "../i18n";
import { coverSrc, fetchStoreCatalog, type StoreVoice } from "../lib/voices";
import { displayVoiceName } from "../lib/voiceDisplay";
import { cancelStoreJob, enqueueStoreDownload, useStoreJobs } from "../lib/storeJobs";
import { stagger } from "./Motion";

/** 首页推荐几个。取广场清单里排在最前的官方音色：清单的顺序由维护者编排，排在前面的就是推荐的。 */
const STARTER_COUNT = 3;

/**
 * 还没有音色时，首页直接给出几个官方音色，点一下就下载安装，不必先去广场找。
 * 下载走广场同一条队列：离开首页也不中断，装好后首页随之刷新。
 */
export function StarterVoices({ onInstalled, onOpenPlaza }: { onInstalled: () => void; onOpenPlaza: () => void }) {
  const { locale } = useI18n();
  const [voices, setVoices] = useState<StoreVoice[] | null>(null);
  const jobs = useStoreJobs();

  useEffect(() => {
    let alive = true;
    void fetchStoreCatalog(true)
      .then((c) => alive && setVoices((c.voices ?? []).filter((v) => v.official && !v.installed).slice(0, STARTER_COUNT)))
      .catch(() => alive && setVoices([]));
    return () => {
      alive = false;
    };
  }, []);

  // 有一个装好了就刷新首页；首页一旦有了音色，这一块也就不再出现
  useEffect(() => {
    if (jobs.generation > 0) onInstalled();
  }, [jobs.generation, onInstalled]);

  if (!voices?.length) return null;
  return (
    <div>
      <div className="grid grid-cols-3 gap-4 max-[720px]:grid-cols-1">
        {voices.map((v, i) => {
          const running = jobs.running.includes(v.id);
          const queued = jobs.queued.includes(v.id);
          const pct = Math.round(jobs.prog[v.id]?.percent ?? 0);
          const cover = coverSrc(v.cover_url || v.cover_local || "");
          return (
            <div key={v.id} className="rise bg-[var(--group)] rounded-[var(--r)] overflow-hidden" style={stagger(i)}>
              <div className="aspect-[16/9] bg-[color-mix(in_srgb,var(--accent)_10%,var(--group))]" style={cover ? { backgroundImage: `url("${cover}")`, backgroundSize: "cover", backgroundPosition: "center" } : undefined} />
              <div className="px-4 py-3">
                <div className="text-[14px] font-semibold truncate">{displayVoiceName(v, locale)}</div>
                <div className="mt-0.5 text-[11.5px] text-[var(--meta)] truncate">{[v.series, v.size_label].filter(Boolean).join(" · ")}</div>
                <div className="mt-3 flex items-center gap-2">
                  {running || queued ? (
                    <>
                      <div className="flex-1 h-1.5 rounded-full bg-[var(--line)] overflow-hidden">
                        <div className="h-full bg-[var(--accent)] transition-[width] duration-300" style={{ width: `${queued ? 0 : pct}%` }} />
                      </div>
                      <span className="text-[11.5px] text-[var(--meta)] tabular-nums w-10 text-right">{queued ? t("s.starterQueued") : `${pct}%`}</span>
                      <Btn onClick={() => cancelStoreJob(v.id)}>{t("s.starterCancel")}</Btn>
                    </>
                  ) : (
                    <Btn primary onClick={() => enqueueStoreDownload(v)}>{t("s.starterGet")}</Btn>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {jobs.error ? <p role="alert" className="m-0 mt-3 text-[12.5px] text-[var(--danger)]">{jobs.error}</p> : null}
      <div className="mt-3 text-center">
        <button type="button" onClick={onOpenPlaza} className="bg-transparent border-0 cursor-pointer text-[12.5px] text-[var(--accent)] hover:underline underline-offset-2">
          {t("s.starterMore")}
        </button>
      </div>
    </div>
  );
}
