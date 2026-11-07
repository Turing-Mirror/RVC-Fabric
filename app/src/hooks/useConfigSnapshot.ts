import { useEffect, useSyncExternalStore } from "react";
import { getConfig } from "../lib/config";
import { configSnapshot } from "../lib/configSnapshot";

/** Read the saved/optimistic snapshot on the first render; refresh in the background. */
export function useConfigSnapshot() {
  const snapshot = useSyncExternalStore(configSnapshot.subscribe, configSnapshot.get);
  useEffect(() => { void getConfig().catch(() => {}); }, []);
  return snapshot;
}
