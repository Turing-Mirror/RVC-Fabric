// @vitest-environment happy-dom
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { ToolActions } from "./ToolWindow";
import { CatalogTransition } from "./CatalogTransition";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
afterEach(() => vi.useRealTimers());

it("keeps progress updates in place and settles rapid navigation on the latest page", () => {
  vi.useFakeTimers();
  const host = document.createElement("div");
  const root = createRoot(host);
  const render = (scope: string, page: number, text: string) => act(() => root.render(
    createElement(CatalogTransition, { scope, page, order: ["separate", "train"], children: createElement("button", null, text) }),
  ));
  try {
    render("separate", 1, "10%");
    const button = host.querySelector("button");
    render("separate", 1, "40%");
    expect(host.querySelector("button")).toBe(button);
    expect(host.textContent).toBe("40%");
    expect(host.querySelector("[data-switching]")).toBeNull();
    render("train", 1, "Train");
    expect(host.querySelector("[inert]")?.textContent).toBe("40%");
    render("separate", 2, "Page 2");
    act(() => vi.advanceTimersByTime(430));
    act(() => vi.advanceTimersByTime(430));
    expect(host.textContent).toBe("Page 2");
    expect(host.querySelector("[inert]")).toBeNull();
    expect(host.querySelector("[data-switching]")).toBeNull();
  } finally { act(() => root.unmount()); }
});

it("keeps only the active tool actions while the old body slides out", () => {
  vi.useFakeTimers();
  const host = document.createElement("div");
  const root = createRoot(host);
  const render = (scope: string) => act(() => root.render(
    <CatalogTransition scope={scope} order={["sts", "tts"]}>
      <p>{scope} body</p><ToolActions><button>{scope} action</button></ToolActions>
    </CatalogTransition>,
  ));
  try {
    render("sts");
    render("tts");
    expect(host.querySelector("[inert]")?.textContent).toBe("sts body");
    expect([...host.querySelectorAll("button")].map(b => b.textContent)).toEqual(["tts action"]);
    act(() => vi.advanceTimersByTime(430));
    expect(host.textContent).toBe("tts bodytts action");
  } finally { act(() => root.unmount()); }
});
