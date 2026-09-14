/**
 * 测试基座：把真实组件/hook 渲进 happy-dom，渲染与副作用都走 act 提交。
 * 不引入 testing-library —— 现有测试只查 DOM 与派发原生事件。
 */
import { act, type ReactElement } from "react";
import { createRoot, type Root } from "react-dom/client";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

export type Mounted = {
  container: HTMLElement;
  root: Root;
  unmount: () => void;
};

export function mount(el: ReactElement): Mounted {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(el));
  return {
    container,
    root,
    unmount: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

/** 渲一个只负责调用 hook 的探针组件，把每次渲染的返回值留在 result.current。 */
export function mountHook<T>(hook: () => T): Mounted & { result: { current: T } } {
  const box = { current: undefined as unknown as T };
  function Probe() {
    box.current = hook();
    return null;
  }
  const m = mount(<Probe />);
  return { ...m, result: box };
}

/** 等微任务队列清空 —— 让 effect 里 await 的 promise 落定。 */
export async function tick(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

/** 派发一次会冒泡到 window 的键盘按下。 */
export function pressKey(el: EventTarget, key: string): void {
  act(() => {
    el.dispatchEvent(
      new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }),
    );
  });
}
