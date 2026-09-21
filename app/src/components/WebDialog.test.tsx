// @vitest-environment happy-dom
/**
 * R02 回归：确认框的键盘语义。
 *
 * 修复前 window 级 keydown 看到 Enter 就 finish(true) —— 焦点明明在「取消」
 * 上按回车照样算确认。修复后 Enter 激活的是当前焦点所在按钮的语义。
 */
import { act } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { askConfirm, askPrompt } from "../lib/webDialog";
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

  it("输入框里的一次 Enter 只回答当前请求，不能连答排队弹窗", async () => {
    const m = mount(<WebDialogHost />);
    mounts.push(m);
    let p1!: Promise<string | null>;
    let p2!: Promise<boolean>;
    act(() => {
      p1 = askPrompt("名字？", "默认");
      p2 = askConfirm("确定吗？");
    });
    await tick();
    const input = m.container.querySelector(
      "[role=dialog] input",
    ) as HTMLInputElement;
    expect(input).not.toBeNull();
    pressKey(input, "Enter");
    await expect(p1).resolves.toBe("默认");
    // 同一次按键不得回答新弹出的确认框。
    let settled2: boolean | "pending" = "pending";
    void p2.then((v) => {
      settled2 = v;
    });
    await tick();
    expect(settled2).toBe("pending");
    expect(m.container.querySelector("[role=dialog]")).not.toBeNull();
    // 第二个弹窗需要一次新的、独立的按键。
    pressKey(document.body, "Escape");
    await expect(p2).resolves.toBe(false);
  });

  it("按住 Enter 的 repeat 事件不会连续作答排队弹窗", async () => {
    const m = mount(<WebDialogHost />);
    mounts.push(m);
    let p1!: Promise<boolean>;
    let p2!: Promise<boolean>;
    act(() => {
      p1 = askConfirm("第一个？");
      p2 = askConfirm("第二个？");
    });
    await tick();
    pressKey(document.body, "Enter");
    await expect(p1).resolves.toBe(true);
    await tick();
    // 长按产生的 repeat keydown 不许替用户回答下一个弹窗。
    act(() => {
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Enter",
          bubbles: true,
          cancelable: true,
          repeat: true,
        }),
      );
    });
    let settled2 = false;
    void p2.then(() => {
      settled2 = true;
    });
    await tick();
    expect(settled2).toBe(false);
    pressKey(document.body, "Enter");
    await expect(p2).resolves.toBe(true);
  });

  it("IME 组词中的 Enter 不提交输入框", async () => {
    const m = mount(<WebDialogHost />);
    mounts.push(m);
    let p!: Promise<string | null>;
    act(() => {
      p = askPrompt("名字？", "默认");
    });
    await tick();
    const input = m.container.querySelector(
      "[role=dialog] input",
    ) as HTMLInputElement;
    // 输入法组词还没结束，Enter 是选词不是提交。
    act(() => {
      input.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Enter",
          bubbles: true,
          cancelable: true,
          isComposing: true,
        }),
      );
    });
    let settled = false;
    void p.then(() => {
      settled = true;
    });
    await tick();
    expect(settled).toBe(false);
    // 组词结束后的 Enter 才提交。
    pressKey(input, "Enter");
    await expect(p).resolves.toBe("默认");
  });
});
