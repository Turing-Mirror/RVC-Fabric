// @vitest-environment happy-dom
/**
 * C-01 页面生命周期回归：离场的页在推移期间保持挂载、不重新初始化；
 * 切页 N 次后台账无净增长。
 */
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mountCounts, resetMountCounts } from "../lib/lifecycle";
import type { PageId } from "../lib/nav";
import { mount, type Mounted } from "../test/dom";
import { usePageActive } from "trm-ui";
import { PageHost } from "./PageHost";

const pages: PageId[] = ["home", "models", "plaza", "more", "settings", "help"];

function Stub({ id }: { id: PageId }) {
  const active = usePageActive();
  return <div data-testid={`pane-${id}`} data-active={String(active)}>{id}</div>;
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

  it("leaving page stays mounted while the pages move, then unmounts", async () => {
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

  it("100 switches leave no net growth in mounted panes", async () => {
    m = mount(host("home"));
    for (let i = 0; i < 100; i += 1) {
      const next = pages[i % pages.length];
      act(() => m.root.render(host(next)));
      await settle();
    }
    let net = 0;
    mountCounts().forEach((c) => {
      net += c.mounts - c.unmounts;
    });
    // 只剩当前页一层在台上。
    expect(net).toBe(1);
  });
});
