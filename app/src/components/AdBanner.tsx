import { useEffect, useState } from "react";
import { dismissAd, fetchPlaza, openExternal, type PlazaItem } from "../lib/plaza";

/**
 * The one dismissible placement.
 *
 * The plaza's own cards have no close button — carrying placements is that
 * page's job. Here on the models page a banner is an interruption to what the
 * user came to do, so it closes, and the choice is remembered across restarts.
 * At most one is ever shown (`plaza::pick_models_banner`).
 */
export function AdBanner() {
  const [item, setItem] = useState<PlazaItem | null>(null);

  useEffect(() => {
    let alive = true;
    void fetchPlaza()
      .then((f) => {
        if (alive) setItem(f.banner ?? null);
      })
      .catch(() => {
        /* a placement that cannot load is simply not shown */
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!item) return null;
  const clickable = Boolean(item.url);

  return (
    <div className="mt-3 flex items-center gap-3.5 rounded-[var(--r)] bg-[var(--group)] px-4 py-3">
      {item.image_url ? (
        <img
          src={item.image_url}
          alt=""
          loading="lazy"
          className="w-[72px] h-11 rounded-[var(--rs)] flex-none grayscale object-cover"
        />
      ) : null}
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-semibold flex items-center gap-2 flex-wrap">
          {item.title}
          {item.is_ad ? (
            <span className="text-[11.5px] px-2 py-0.5 rounded-[5px] whitespace-nowrap text-[var(--notify)] shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--notify)_48%,transparent)]">
              商业推广
            </span>
          ) : null}
        </div>
        {item.body ? (
          <div className="text-[12.5px] text-[var(--help)] truncate">{item.body}</div>
        ) : null}
      </div>
      {clickable ? (
        <button
          type="button"
          onClick={() => void openExternal(item.url)}
          className="flex-none border-0 bg-transparent cursor-pointer text-[13px] text-[var(--accent)] px-2 py-1 rounded-[var(--rs)] hover:bg-[var(--accent-soft)]"
        >
          {item.action_label || "查看"}
        </button>
      ) : null}
      <button
        type="button"
        aria-label="不再显示"
        title="不再显示"
        onClick={() => {
          void dismissAd(item.id);
          setItem(null);
        }}
        className="flex-none border-0 bg-transparent cursor-pointer text-[15px] leading-none text-[var(--meta)] px-2 py-1 rounded-[var(--rs)] hover:text-[var(--ink)] hover:bg-[color-mix(in_srgb,var(--ink)_6%,transparent)]"
      >
        ×
      </button>
    </div>
  );
}
