import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { fetchPlaza, type PlazaFeed } from "../lib/plaza";
import { useI18n } from "../i18n";

const EMPTY: PlazaFeed = {
  items: [],
  banner: null,
  changelog: [],
  errors: [],
  app_version: "",
  newest: "",
  unread: false,
};

/**
 * One owner for the plaza feed.
 *
 * The plaza page, the models-page banner and the tab dot all need the same
 * payload; fetching it per component meant three requests for one JSON file.
 * App holds this hook and passes the result down.
 *
 * Re-fetches when UI locale changes so changelog / plaza strings resolve again.
 */
export function usePlaza() {
  const { locale } = useI18n();
  const [feed, setFeed] = useState<PlazaFeed>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [seen, setSeen] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setFeed(await fetchPlaza());
    } catch (e) {
      setFeed({ ...EMPTY, errors: [String(e)] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload, locale]);

  /** Called when the user opens the plaza: clears the dot, here and on disk. */
  const markSeen = useCallback(() => {
    setSeen(true);
    if (feed.newest) {
      void invoke("plaza_mark_seen", { newest: feed.newest }).catch(() => {});
    }
  }, [feed.newest]);

  return { feed, loading, reload, markSeen, unread: feed.unread && !seen };
}
