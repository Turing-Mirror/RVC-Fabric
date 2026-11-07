// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
const invoke = vi.hoisted(() => vi.fn(() => new Promise(() => {})));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(async () => () => {}) }));
vi.mock("../lib/appearance", () => ({ applyAppearance: vi.fn() }));
import { configSnapshot } from "../lib/configSnapshot";
import { useConfigSnapshot } from "./useConfigSnapshot";
import { useConfig } from "./useConfig";

it("renders the cached user value on the first frame of both home and settings remounts", async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  const el = document.createElement("div");
  document.body.append(el);
  const root = createRoot(el);
  const frames: string[] = [];
  function Home() {
    const { config, loaded } = useConfigSnapshot();
    const text = loaded ? String(config.home_banner_text || "DEFAULT") : "LOADING";
    frames.push(text);
    return <output>{text}</output>;
  }
  function Settings() {
    const { cfg, loaded } = useConfig();
    const text = loaded ? String(cfg.home_banner_text || "DEFAULT") : "LOADING";
    frames.push(text);
    return <output>{text}</output>;
  }
  try {
    await act(async () => root.render(<Home />));
    expect(frames).toEqual(["LOADING"]);
    act(() => configSnapshot.receive({ home_banner_text: "UGC title" }));
    expect(el.textContent).toBe("UGC title");
    act(() => root.render(null));
    frames.length = 0;
    await act(async () => root.render(<Settings />));
    expect(frames[0]).toBe("UGC title");
    act(() => root.render(null));
    frames.length = 0;
    // Delayed/failed refresh must not replace the initial snapshot with defaults.
    invoke.mockImplementation(() => Promise.reject(new Error("offline")));
    await act(async () => root.render(<Home />));
    expect(frames.every(text => text === "UGC title")).toBe(true);
    act(() => configSnapshot.receive({ home_banner_text: "other window" }));
    expect(el.textContent).toBe("other window");
    act(() => configSnapshot.patch({ home_banner_text: "" }));
    expect(el.textContent).toBe("DEFAULT");
  } finally {
    act(() => root.unmount());
    el.remove();
  }
});
