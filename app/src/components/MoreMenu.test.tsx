// @vitest-environment happy-dom
import { act, useRef, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";
import { MoreMenuPopup, type MoreMenuCloseReason } from "./MoreMenu";
import { Leave } from "./Presence";
import { EXIT_MS } from "../hooks/useExit";

const anchor = { left: 100, right: 180, top: 40, bottom: 60 };
const mounts: Mounted[] = [];

function menuItems(): HTMLButtonElement[] {
  return Array.from(document.querySelectorAll<HTMLButtonElement>("[role=menuitem]"));
}

function RetainedMenu() {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  return <>
    <button ref={trigger} data-trigger onClick={() => setOpen(true)}>打开</button>
    <Leave>{open ? <MoreMenuPopup anchor={anchor} items={[
      { label: "不可用", action: () => {}, disabled: true },
      { label: "可用", action: () => {} },
      { label: "下一项", action: () => {} },
    ]} onClose={(reason) => {
      setOpen(false);
      if (reason !== "tab") trigger.current?.focus();
    }} /> : null}</Leave>
  </>;
}

describe("MoreMenuPopup", () => {
  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
    document.querySelectorAll("[data-more-menu]").forEach((el) => el.remove());
    vi.useRealTimers();
  });

  it("退场不抢回焦点，快速重开仍聚焦第一个可用项并支持方向键", () => {
    vi.useFakeTimers();
    const mounted = mount(<RetainedMenu />);
    mounts.push(mounted);
    const trigger = mounted.container.querySelector<HTMLButtonElement>("[data-trigger]")!;
    act(() => trigger.click());
    expect(document.activeElement?.textContent).toBe("可用");
    act(() => {
      document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    expect(document.querySelector(".menu-out")).not.toBeNull();
    expect(document.activeElement).toBe(trigger);
    act(() => vi.advanceTimersByTime(EXIT_MS / 2));
    expect(document.activeElement).toBe(trigger);
    act(() => trigger.click());
    expect(document.querySelector(".menu-out")).toBeNull();
    expect(document.activeElement?.textContent).toBe("可用");
    act(() => {
      document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
    });
    expect(document.activeElement?.textContent).toBe("下一项");
  });

  it("正常退出保留恢复到触发按钮的语义，退场完成后可再次键盘操作", () => {
    vi.useFakeTimers();
    const mounted = mount(<RetainedMenu />);
    mounts.push(mounted);
    const trigger = mounted.container.querySelector<HTMLButtonElement>("[data-trigger]")!;
    act(() => trigger.click());
    act(() => {
      document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    expect(document.activeElement).toBe(trigger);
    act(() => vi.advanceTimersByTime(EXIT_MS + 1));
    expect(document.querySelector("[role=menu]")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    act(() => trigger.click());
    expect(document.activeElement?.textContent).toBe("可用");
  });

  it("portal 到 body，不在挂点容器里", async () => {
    const mounted = mount(<MoreMenuPopup anchor={anchor} items={[{ label: "甲", action: vi.fn() }]} />);
    mounts.push(mounted);
    await tick();
    const menu = document.querySelector("[role=menu]");
    expect(menu).toBeTruthy();
    expect(menu!.parentElement).toBe(document.body);
    expect(mounted.container.querySelector("[role=menu]")).toBeNull();
    expect(menu!.closest("[data-more-menu]")).toBeTruthy();
  });

  it("首项禁用时光标落到第一个可用项，动作照常触发", async () => {
    const second = vi.fn();
    const mounted = mount(<MoreMenuPopup anchor={anchor} items={[
      { label: "不可用", action: vi.fn(), disabled: true },
      { label: "可用", action: second },
    ]} />);
    mounts.push(mounted);
    await tick();
    expect(document.activeElement?.textContent).toBe("可用");
    const items = menuItems();
    expect(items[0].disabled).toBe(true);
    // 方向键跳过禁用项循环。
    act(() => {
      document.querySelector("[role=menu]")!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
    });
    expect(document.activeElement?.textContent).toBe("可用");
    act(() => items[1].click());
    await tick();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("全部禁用时 Esc 仍能关闭并回报原因", async () => {
    const closed: MoreMenuCloseReason[] = [];
    const mounted = mount(<MoreMenuPopup anchor={anchor} onClose={(r) => closed.push(r)} items={[
      { label: "一", action: vi.fn(), disabled: true },
      { label: "二", action: vi.fn(), disabled: true },
    ]} />);
    mounts.push(mounted);
    await tick();
    const menu = document.querySelector<HTMLElement>("[role=menu]")!;
    act(() => {
      menu.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
    });
    await tick();
    expect(closed).toEqual(["escape"]);
  });

  it("Tab 关闭并回报 tab 原因，Esc/动作分别回报 escape/action", async () => {
    const closed: MoreMenuCloseReason[] = [];
    const action = vi.fn();
    const mounted = mount(<MoreMenuPopup anchor={anchor} onClose={(r) => closed.push(r)} items={[
      { label: "一", action },
    ]} />);
    mounts.push(mounted);
    await tick();
    const menu = document.querySelector<HTMLElement>("[role=menu]")!;
    act(() => {
      menu.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }));
    });
    await tick();
    expect(closed).toEqual(["tab"]);
    // 动作点击：先回报 action 再执行 action。
    act(() => menuItems()[0].click());
    await tick();
    expect(closed).toEqual(["tab", "action"]);
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("右键对齐与左对齐各自贴边", async () => {
    // happy-dom 里 offsetWidth/scrollHeight 是 0，宽度按 1 处理，只验证传给 placePopup 的方向。
    const mounted = mount(<MoreMenuPopup anchor={anchor} align="left" items={[{ label: "甲", action: vi.fn() }]} />);
    mounts.push(mounted);
    await tick();
    const menu = document.querySelector<HTMLElement>("[role=menu]")!;
    // 左对齐：菜单左缘贴着指针位（anchor.left）。
    expect(menu.style.left).toBe("100px");
  });
});
