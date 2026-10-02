// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";
import { MoreMenuPopup, type MoreMenuCloseReason } from "./MoreMenu";

const anchor = { left: 100, right: 180, top: 40, bottom: 60 };
const mounts: Mounted[] = [];

function menuItems(): HTMLButtonElement[] {
  return Array.from(document.querySelectorAll<HTMLButtonElement>("[role=menuitem]"));
}

describe("MoreMenuPopup", () => {
  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
    document.querySelectorAll("[data-more-menu]").forEach((el) => el.remove());
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
