// @vitest-environment happy-dom
/**
 * useModalKeys 回归：弹层共用的键盘/焦点契约（C3）。
 *
 * 修复前 App 的 killAsk/closeAsk 自定义确认层没有任何键盘处理：Escape 关不掉、
 * 焦点还留在遮罩后面的按钮上、Tab 直接跑出弹层到背景页面。现在它们和
 * WebDialog 走同一套契约。
 */
import { act } from "react";
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, pressKey, tick, type Mounted } from "../test/dom";
import { useModalKeys } from "./useModalKeys";

// 弹层挂着全局 keydown 监听 —— 每个用例都得卸干净，否则上一个弹层的
// 监听器会抢下一个用例的按键。
const mounts: Mounted[] = [];
afterEach(() => {
  while (mounts.length) mounts.pop()?.unmount();
});

function Probe({
  open,
  onEscape,
}: {
  open: boolean;
  onEscape?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useModalKeys(open, ref, { onEscape });
  return (
    <div>
      <button type="button" data-bg>
        背景按钮
      </button>
      {open ? (
        <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true">
          <button type="button" data-a>
            取消
          </button>
          <button type="button" data-b>
            确定
          </button>
        </div>
      ) : null}
    </div>
  );
}

describe("useModalKeys", () => {
  it("打开时焦点收进弹层；Escape 走取消语义；长按 Escape 不连发", async () => {
    const onEscape = vi.fn();
    const m = mount(<Probe open onEscape={onEscape} />);
    mounts.push(m);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 5));
    });
    const dlg = m.container.querySelector("[role=dialog]")!;
    expect(
      dlg.contains(document.activeElement),
      "打开后焦点应在弹层内",
    ).toBe(true);
    pressKey(document.body, "Escape");
    expect(onEscape).toHaveBeenCalledTimes(1);
    act(() => {
      document.body.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Escape",
          bubbles: true,
          cancelable: true,
          repeat: true,
        }),
      );
    });
    expect(onEscape).toHaveBeenCalledTimes(1);
  });

  it("Tab 在弹层里转圈，不会漏到遮罩后面的页面", async () => {
    const m = mount(<Probe open />);
    mounts.push(m);
    const dlg = m.container.querySelector("[role=dialog]") as HTMLElement;
    const first = dlg.querySelector("[data-a]") as HTMLElement;
    const last = dlg.querySelector("[data-b]") as HTMLElement;
    act(() => last.focus());
    pressKey(last, "Tab");
    expect(document.activeElement).toBe(first);
    act(() => first.focus());
    act(() => {
      first.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Tab",
          shiftKey: true,
          bubbles: true,
          cancelable: true,
        }),
      );
    });
    expect(document.activeElement).toBe(last);
    // 焦点在弹层外（比如还没收进来时）按 Tab 也被拉回第一个控件
    const bg = m.container.querySelector("[data-bg]") as HTMLElement;
    act(() => bg.focus());
    pressKey(bg, "Tab");
    expect(document.activeElement).toBe(first);
  });

  it("关闭时把焦点还给打开前的控件", async () => {
    const bg = document.createElement("button");
    document.body.appendChild(bg);
    try {
      act(() => bg.focus());
      const m = mount(<Probe open />);
      mounts.push(m);
      await act(async () => {
        await new Promise((r) => setTimeout(r, 5));
      });
      expect(
        (m.container.querySelector("[role=dialog]") as HTMLElement).contains(
          document.activeElement,
        ),
      ).toBe(true);
      act(() => {
        m.root.render(<Probe open={false} />);
      });
      await tick();
      expect(document.activeElement).toBe(bg);
    } finally {
      bg.remove();
    }
  });

  it("未打开时不拦任何按键", () => {
    const onEscape = vi.fn();
    const m = mount(<Probe open={false} onEscape={onEscape} />);
    mounts.push(m);
    pressKey(document.body, "Escape");
    pressKey(document.body, "Tab");
    expect(onEscape).not.toHaveBeenCalled();
  });
});
