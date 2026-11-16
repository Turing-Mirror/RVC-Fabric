import { describe, expect, it } from "vitest";
import { ConfigSnapshot } from "./configSnapshot";

describe("configuration first-frame snapshot", () => {
  it("distinguishes not loaded from saved empty configuration", () => {
    const store = new ConfigSnapshot();
    expect(store.get().loaded).toBe(false);
    store.receive({});
    expect(store.get()).toEqual({ config: {}, loaded: true });
    expect(store.get()).toBe(store.get());
  });
  it("retains custom content between subscribers and supports clearing it", () => {
    const store = new ConfigSnapshot();
    store.receive({ home_banner_text: "My title", home_banner_sub: "My subtitle" });
    const off = store.subscribe(() => {});
    off();
    expect(store.get().config.home_banner_text).toBe("My title");
    store.patch({ home_banner_text: "" });
    expect(store.get().config.home_banner_text).toBe("");
  });
  it("keeps a debounced edit when a new page reads old disk data", () => {
    const store = new ConfigSnapshot();
    store.receive({ home_banner_text: "old" });
    store.patch({ home_banner_text: "new" });
    store.receive({ home_banner_text: "old", unrelated: 7 }, store.revision);
    expect(store.get().config).toEqual({ home_banner_text: "new", unrelated: 7 });
    store.receive({ home_banner_text: "new" }, store.revision, { home_banner_text: "new" });
    store.receive({ home_banner_text: "external" });
    expect(store.get().config.home_banner_text).toBe("external");
  });
  it("does not let a late initial read overwrite a newer external event", () => {
    const store = new ConfigSnapshot();
    const revision = store.revision;
    store.receive({ home_banner_text: "external" });
    store.receive({ home_banner_text: "old", theme_mode: "light" }, revision);
    expect(store.get().config).toEqual({ home_banner_text: "external", theme_mode: "light" });
  });
  it("keeps a newer edit when an older write completes", () => {
    const store = new ConfigSnapshot();
    store.receive({ home_banner_text: "old" });
    store.patch({ home_banner_text: "first" });
    const revision = store.revision;
    store.patch({ home_banner_text: "second" });
    store.receive({ home_banner_text: "first" }, revision, { home_banner_text: "first" });
    expect(store.get().config.home_banner_text).toBe("second");
  });
  it("protects a confirmed optimistic edit from a read started before confirmation", () => {
    const store = new ConfigSnapshot();
    store.receive({ home_banner_text: "old" });
    store.patch({ home_banner_text: "new" });
    const revision = store.revision;
    store.receive({ home_banner_text: "new" }, revision, { home_banner_text: "new" });
    store.receive({ home_banner_text: "old" }, revision);
    expect(store.get().config.home_banner_text).toBe("new");
  });
  it("does not restore keys removed by a newer full snapshot", () => {
    const store = new ConfigSnapshot();
    store.receive({ home_banner_text: "old", removed: true });
    const revision = store.revision;
    store.receive({ home_banner_text: "new" });
    store.receive({ home_banner_text: "old", removed: true }, revision);
    expect(store.get().config).toEqual({ home_banner_text: "new" });
  });
});
