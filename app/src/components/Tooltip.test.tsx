// @vitest-environment happy-dom
/**
 * N04 回归：小问号（HelpMark）与开关（Toggle）的事件边界。
 *
 * 修复前 HelpMark 的 <button> 是 Toggle 里 <label> 的第一个子元素，
 * 成了 label 的 labeled control：悬停/按压整行（文字、复选框、空隙）都会
 * 把 :hover/:active 转发到问号上；点击文字被转发给问号吞掉，开关不切。
 * Tooltip 又只用一份 open 状态，鼠标一离开就关 —— 点了问号拿到的焦点
 * 也留不住说明。
 */
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, pressKey, tick, type Mounted } from "../test/dom";
import { Toggle } from "./controls";
import { HelpMark } from "./ui";

const TIP = "这一行说明文字";

function tooltipEl(): HTMLElement | null {
  return document.querySelector("[role=tooltip]");
}

function pointerOver(el: Element): void {
  act(() => {
    el.dispatchEvent(new Event("pointerover", { bubbles: true }));
  });
}

function pointerOut(el: Element): void {
  act(() => {
    el.dispatchEvent(new Event("pointerout", { bubbles: true }));
  });
}

describe("Toggle 里的小问号", () => {
  const mounts: Mounted[] = [];
  afterEach(() => {
    vi.useRealTimers();
    while (mounts.length) mounts.pop()?.unmount();
  });

  it("问号按钮不在 <label> 内：行的标签关联只属于复选框", () => {
    const m = mount(
      <Toggle checked={false} onChange={() => {}} label="开关" tip={TIP} />,
    );
    mounts.push(m);
    const label = m.container.querySelector("label")!;
    expect(label.querySelector("input[type=checkbox]")).not.toBeNull();
    // label 里不该再有任何 labelable 的按钮抢 controls 关联
    expect(label.querySelector("button")).toBeNull();
    // 问号仍然存在，在 label 之外
    expect(m.container.querySelector("button")).not.toBeNull();
  });

  it("点复选框只切换一次；点问号不切设置", async () => {
    const onChange = vi.fn();
    const m = mount(
      <Toggle checked={false} onChange={onChange} label="开关" tip={TIP} />,
    );
    mounts.push(m);
    // 勾选框就是 input 本身（样子由 index.css 画）。
    const box = m.container.querySelector("label input") as HTMLElement;
    act(() => box.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenLastCalledWith(true);

    const help = m.container.querySelector("button") as HTMLElement;
    act(() => help.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onChange).toHaveBeenCalledTimes(1);
    await tick();
    // 点问号拿到焦点 → 说明要可靠显示
    expect(tooltipEl()).not.toBeNull();
  });

  it("悬停问号显示说明；焦点还在问号上时鼠标移开不立即关", async () => {
    vi.useFakeTimers();
    const m = mount(<HelpMark title={TIP} />);
    mounts.push(m);
    const btn = m.container.querySelector("button") as HTMLElement;
    pointerOver(btn);
    expect(tooltipEl()?.textContent).toBe(TIP);
    pointerOut(btn);
    // 悬停离开有一小段收起的缓冲，不是瞬间消失
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(tooltipEl()).not.toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    expect(tooltipEl()).toBeNull();
  });

  it("键盘聚焦显示说明，Escape 关闭后可再次打开", async () => {
    const m = mount(<HelpMark title={TIP} />);
    mounts.push(m);
    const btn = m.container.querySelector("button") as HTMLElement;
    act(() => btn.focus());
    await tick();
    expect(tooltipEl()).not.toBeNull();
    pressKey(btn, "Escape");
    await tick();
    expect(tooltipEl()).toBeNull();
    act(() => btn.focus());
    await tick();
    expect(tooltipEl()).not.toBeNull();
  });

  it("聚焦问号被滚动关掉后，同一颗仍聚焦的按钮点一下能重开（C7）", async () => {
    // 复现验收用例：close() 只清了 focused 状态没清 DOM 焦点，按钮还握着
    // 焦点；再点它 focus() 是 no-op，不会再发 focus 事件，说明就一直关着。
    // 键盘激活在 DOM 层同样落成 click 事件 —— 这条断言同时覆盖键盘重开。
    const m = mount(<HelpMark title={TIP} />);
    mounts.push(m);
    const btn = m.container.querySelector("button") as HTMLElement;
    act(() => btn.click());
    await tick();
    expect(tooltipEl()).not.toBeNull();
    act(() => window.dispatchEvent(new Event("scroll")));
    await tick();
    expect(tooltipEl()).toBeNull();
    // 滚动关闭不清 DOM 焦点（设计如此：键盘用户的焦点不能丢）
    expect(document.activeElement).toBe(btn);
    act(() => btn.click());
    await tick();
    expect(tooltipEl()).not.toBeNull();
  });

  it("悬停文字区域不打开问号的说明", async () => {
    const m = mount(
      <Toggle checked={false} onChange={() => {}} label="开关" tip={TIP} />,
    );
    mounts.push(m);
    const label = m.container.querySelector("label")!;
    pointerOver(label);
    await tick();
    expect(tooltipEl()).toBeNull();
  });
});
