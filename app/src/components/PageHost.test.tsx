// @vitest-environment happy-dom
/**
 * C-01 页面生命周期回归：离场的页在推移期间保持运行、不重新初始化；
 * 停稳后停掉副作用但保留状态；切页 N 次后台账无净增长。
 */
import { act, useState } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mountCounts, resetMountCounts } from "../lib/lifecycle";
import type { PageId } from "../lib/nav";
import { mount, type Mounted } from "../test/dom";
import { usePageActive } from "trm-ui";
import { PageHost } from "./PageHost";

const pages: PageId[] = ["home", "models", "plaza", "more", "settings", "help"];

function Stub({ id }: { id: PageId }) {
  const active = usePageActive();
  const [draft, setDraft] = useState("");
  return (
    <div data-testid={`pane-${id}`} data-active={String(active)}>
      {id}
      <button onClick={() => setDraft("Voice draft")}>{draft || "Edit"}</button>
    </div>
  );
}

function host(page: PageId) {
  return <PageHost page={page}>{(id) => <Stub id={id} />}</PageHost>;
}

describe("PageHost lifecycle (C-01)", () => {
  let m: Mounted;
  let finish: (() => void)[] = [];
  const original = HTMLElement.prototype.animate;
  const settle = async () => {
    await act(async () => {
      finish[finish.length - 1]?.();
      await Promise.resolve();
    });
  };
  beforeEach(() => {
    resetMountCounts();
    finish = [];
    // 可手动结束的动画替身：推移进行中两页都在，finish 之后才卸下离场页。
    HTMLElement.prototype.animate = function () {
      let done!: () => void;
      let fail!: (reason: unknown) => void;
      const finished = new Promise<void>((resolve, reject) => { done = resolve; fail = reject; });
      finish.push(done);
      return { finished, cancel: () => fail(new Error("cancelled")) } as unknown as Animation;
    } as typeof HTMLElement.prototype.animate;
  });
  afterEach(() => {
    m?.unmount();
    HTMLElement.prototype.animate = original;
  });

  it("leaving page keeps running while the pages move, then pauses", async () => {
    m = mount(host("home"));
    act(() => m.root.render(host("models")));
    expect(mountCounts().get("page:home")).toEqual({ mounts: 1, unmounts: 0 });
    expect(mountCounts().get("page:models")).toEqual({ mounts: 1, unmounts: 0 });
    await settle();
    expect(mountCounts().get("page:home")).toEqual({ mounts: 1, unmounts: 1 });
    expect(mountCounts().get("page:models")).toEqual({ mounts: 1, unmounts: 0 });
  });

  it("navigating back to a still-leaving page does not remount it", async () => {
    m = mount(host("home"));
    act(() => m.root.render(host("models")));
    act(() => m.root.render(host("home")));
    await settle();
    const home = mountCounts().get("page:home");
    expect(home?.mounts).toBe(1);
    expect(home?.unmounts).toBe(0);
  });

  it("leaving panes become inactive and inert immediately, including a quick return", () => {
    m = mount(host("home"));
    act(() => m.root.render(host("models")));
    const home = m.container.querySelector('[data-testid="pane-home"]')!;
    expect(home.getAttribute("data-active")).toBe("false");
    expect(home.parentElement?.hasAttribute("inert")).toBe(true);
    expect(home.parentElement?.getAttribute("aria-hidden")).toBe("true");
    act(() => m.root.render(host("home")));
    expect(home.getAttribute("data-active")).toBe("true");
    expect(home.parentElement?.hasAttribute("inert")).toBe(false);
  });

  it("100 switches leave only the current page and Community running", async () => {
    m = mount(host("home"));
    for (let i = 0; i < 100; i += 1) {
      const next = pages[i % pages.length];
      act(() => m.root.render(host(next)));
      await settle();
    }
    const lastPage = pages[99 % pages.length];
    for (const id of pages) {
      const count = mountCounts().get(`page:${id}`)!;
      expect(count.mounts - count.unmounts).toBe(id === "plaza" || id === lastPage ? 1 : 0);
    }
    // 社区页露面后一直运行，没有重启过。
    expect(mountCounts().get("page:plaza")).toEqual({ mounts: 1, unmounts: 0 });
  });

  it("every page keeps its node and state across 100 switches", async () => {
    m = mount(host("home"));
    const findPane = (id: PageId) => m.container.querySelector<HTMLElement>(`[data-testid="pane-${id}"]`);
    const kept = new Map<PageId, HTMLElement>();
    for (const id of pages) {
      act(() => m.root.render(host(id)));
      await settle();
      const pane = findPane(id)!;
      act(() => pane.querySelector("button")!.click());
      kept.set(id, pane);
    }

    for (let i = 0; i < 100; i += 1) {
      const next = pages[i % pages.length];
      act(() => m.root.render(host(next)));
      await settle();
      for (const id of pages) {
        const pane = findPane(id)!;
        expect(pane).toBe(kept.get(id));
        expect(pane.getAttribute("data-active")).toBe(String(id === next));
        expect(pane.parentElement?.hasAttribute("inert")).toBe(id !== next);
        expect(pane.parentElement?.getAttribute("aria-hidden")).toBe(id === next ? null : "true");
        expect(pane.querySelector("button")?.textContent).toBe("Voice draft");
        // 停用副作用的页由 React 藏起来；社区页照常运行，只是不可见。
        expect(pane.style.display).toBe(id === next || id === "plaza" ? "" : "none");
      }
    }
  });
});
