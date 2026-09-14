// @vitest-environment happy-dom
/**
 * R02 回归：确认框的键盘语义。
 *
 * 修复前 window 级 keydown 看到 Enter 就 finish(true) —— 焦点明明在「取消」
 * 上按回车照样算确认。修复后 Enter 激活的是当前焦点所在按钮的语义。
 */
import { act } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { askConfirm } from "../lib/webDialog";
import { mount, pressKey, tick, type Mounted } from "../test/dom";
import { WebDialogHost } from "./WebDialog";

function buttons(m: Mounted): HTMLElement[] {
  return Array.from(m.container.querySelectorAll("[role=dialog] button"));
}

describe("WebDialog 确认框键盘语义", () => {
  const mounts: Mounted[] = [];
  afterEach(() => {
    while (mounts.length) mounts.pop()?.unmount();
  });

  it("焦点在取消按钮上按 Enter 只取消，不确认", async () => {
    const m = mount(<WebDialogHost />);
    mounts.push(m);
    let p!: Promise<boolean>;
    act(() => {
      p = askConfirm("确定吗？");
    });
    await tick();
    const [cancel] = buttons(m);
    cancel.focus();
    pressKey(cancel, "Enter");
    await expect(p).resolves.toBe(false);
  });

  it("焦点在确认按钮上按 Enter 确认", async () => {
    const m = mount(<WebDialogHost />);
    mounts.push(m);
    let p!: Promise<boolean>;
    act(() => {
      p = askConfirm("确定吗？");
    });
    await tick();
    const [, ok] = buttons(m);
    ok.focus();
    pressKey(ok, "Enter");
    await expect(p).resolves.toBe(true);
  });

  it("Escape 只关闭当前弹窗", async () => {
    const m = mount(<WebDialogHost />);
    mounts.push(m);
    let p!: Promise<boolean>;
    act(() => {
      p = askConfirm("确定吗？");
    });
    await tick();
    pressKey(document.body, "Escape");
    await expect(p).resolves.toBe(false);
    // 弹窗关掉之后不能再有残留的对话框响应后续按键
    pressKey(document.body, "Enter");
    await tick();
    expect(m.container.querySelector("[role=dialog]")).toBeNull();
  });

  it("排队的下一个确认仍要被回答，不能被前一次按键吞掉", async () => {
    const m = mount(<WebDialogHost />);
    mounts.push(m);
    let p1!: Promise<boolean>;
    let p2!: Promise<boolean>;
    act(() => {
      p1 = askConfirm("第一个？");
      p2 = askConfirm("第二个？");
    });
    await tick();
    const [cancel] = buttons(m);
    cancel.focus();
    pressKey(cancel, "Enter");
    await expect(p1).resolves.toBe(false);
    // 第二个请求接管弹窗，而不是悄悄丢失
    await tick();
    expect(m.container.querySelector("[role=dialog]")).not.toBeNull();
    pressKey(document.body, "Escape");
    await expect(p2).resolves.toBe(false);
  });
});
