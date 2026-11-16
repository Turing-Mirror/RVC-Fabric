import type { Config } from "./config";

/** Window-local last known configuration, retained across page mounts. */
export class ConfigSnapshot {
  private value: { config: Config; loaded: boolean } = { config: {}, loaded: false };
  private listeners = new Set<() => void>();
  private changed = new Map<string, number>();
  private pending: Config = {};
  revision = 0;
  get = () => this.value;
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };

  private publish(config: Config, loaded: boolean) {
    const previous = this.value.config;
    const keys = new Set([...Object.keys(previous), ...Object.keys(config)]);
    const changed = [...keys].filter(k => !Object.is(previous[k], config[k]) || (k in previous) !== (k in config));
    if (!changed.length && loaded === this.value.loaded) return;
    this.revision += 1;
    changed.forEach(k => this.changed.set(k, this.revision));
    this.value = { config, loaded };
    this.listeners.forEach(fn => fn());
  }

  patch(patch: Config) {
    Object.assign(this.pending, patch);
    this.publish({ ...this.value.config, ...patch }, this.value.loaded);
  }

  receive(config: Config, since = this.revision, confirmed: Config = {}) {
    const acknowledged: string[] = [];
    for (const key of Object.keys(confirmed)) {
      if (key in this.pending && Object.is(this.pending[key], confirmed[key])) {
        delete this.pending[key];
        acknowledged.push(key);
      }
    }
    const next = { ...config };
    // Reads and write responses may arrive after a newer event or local edit.
    this.changed.forEach((revision, key) => {
      if (revision <= since) return;
      if (key in this.value.config) next[key] = this.value.config[key];
      else delete next[key];
    });
    this.publish({ ...next, ...this.pending }, true);
    // Acknowledgement changes ordering even when the optimistic value is identical.
    if (acknowledged.length) {
      this.revision += 1;
      acknowledged.forEach(key => this.changed.set(key, this.revision));
    }
    return this.value.config;
  }
}

export const configSnapshot = new ConfigSnapshot();
