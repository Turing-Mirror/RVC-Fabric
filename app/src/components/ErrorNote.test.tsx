// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { ErrorNote } from "./ErrorNote";
import { mount, tick, type Mounted } from "../test/dom";
import { setTLocale } from "../i18n/t";
let view: Mounted | undefined;
afterEach(() => { view?.unmount(); view = undefined; });
it("shows a failed action in place and keeps the original error", async () => {
  setTLocale("zh-CN");
  const run = vi.fn().mockRejectedValue(new Error("window unavailable"));
  view = mount(<ErrorNote localOnly text="original raw evidence" extraAction={{ label: "Action", run }} />);
  await act(async () => {
    [...view!.container.querySelectorAll("button")].find(button => button.textContent === "Action")!.click();
  });
  await tick();
  expect(run).toHaveBeenCalledTimes(1);
  expect(view.container.textContent).toContain("未能");
  expect(view.container.textContent).toContain("暂时无法判断原因");
  expect(view.container.textContent).not.toContain("window unavailable");
  // Shared ErrorNote displays the failed-action message next to this card.
  expect(view.container.querySelector('[role="status"], [role="alert"]')).not.toBeNull();
});
