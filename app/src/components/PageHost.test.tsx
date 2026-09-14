// @vitest-environment happy-dom
/**
 * C-01 页面生命周期回归：离场层不再是新挂载的副本，离场期间不重新执行
 * 页面初始化；切页 N 次后台账无净增长。
 */
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mountCounts, resetMountCounts } from "../lib/lifecycle";
import type { PageId } from "../lib/nav";
import { mount, type Mounted } from "../test/dom";
import { PageHost } from "./PageHost";

const pages: PageId[] = ["home", "models", "plaza", "more", "settings", "help"];

function Stub({ id }: { id: PageId }) {
  return <div data-testid={`pane-${id}`}>{id}</div>;
}

function host(page: PageId) {
  return <PageHost page={page}>{(id) => <Stub id={id} />}</PageHost>;
}

describe("PageHost lifecycle (C-01)", () => {
  let m: Mounted;
  beforeEach(() => {
    vi.useFakeTimers();
    resetMountCounts();
  });
  afterEach(() => {
    m?.unmount();
    vi.useRealTimers();
  });

  it("leaving page stays mounted during its exit animation, then unmounts", () => {
    m = mount(host("home"));
    act(() => m.root.render(host("models")));
    // 动画进行中：两页都在，旧页没有重挂
    expect(mountCounts().get("page:home")).toEqual({ mounts: 1, unmounts: 0 });
    expect(mountCounts().get("page:models")).toEqual({ mounts: 1, unmounts: 0 });
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(mountCounts().get("page:home")).toEqual({ mounts: 1, unmounts: 1 });
    expect(mountCounts().get("page:models")).toEqual({ mounts: 1, unmounts: 0 });
  });

  it("navigating back to a still-leaving page does not remount it", () => {
    m = mount(host("home"));
    act(() => m.root.render(host("models")));
    act(() => vi.advanceTimersByTime(100)); // home 还在离场动画里
    act(() => m.root.render(host("home")));
    act(() => vi.advanceTimersByTime(500));
    const home = mountCounts().get("page:home");
    expect(home?.mounts).toBe(1); // 未被离场-再进入重复挂载
    expect(home?.unmounts).toBe(0);
  });

  it("100 switches leave no net growth in mounted panes", () => {
    m = mount(host("home"));
    for (let i = 0; i < 100; i += 1) {
      const next = pages[i % pages.length];
      act(() => m.root.render(host(next)));
      act(() => vi.advanceTimersByTime(500));
    }
    const counts = mountCounts();
    let net = 0;
    counts.forEach((c) => {
      net += c.mounts - c.unmounts;
    });
    // 只剩当前页一层在台上。
    expect(net).toBe(1);
  });
});
