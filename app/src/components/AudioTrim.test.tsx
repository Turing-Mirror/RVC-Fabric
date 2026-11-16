// @vitest-environment happy-dom
import { act, StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";
import { t } from "../i18n/t";
const bridge = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: bridge.invoke, convertFileSrc: (path: string) => path }));
vi.mock("../lib/useAudioWaveform", () => ({ useAudioWaveform: () => ({ duration: 10, peaks: [], loading: false, error: false }) }));
vi.mock("./WaveformRange", () => ({ WaveformRange: ({ playing }: { playing: boolean }) => <div data-playing={playing} /> }));
import { AudioTrimEditor } from "./AudioTrim";
const mounts: Mounted[] = [];
afterEach(() => { while (mounts.length) mounts.pop()?.unmount(); vi.restoreAllMocks(); });
function click(m: Mounted, key: string) {
  const button = [...m.container.querySelectorAll("button")].find(b => b.textContent === t(key));
  expect(button).toBeDefined();
  act(() => button!.click());
}

describe("trim preview ownership", () => {
  it("pauses on input replacement and ignores the previous play rejection", async () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    let reject!: (error: Error) => void;
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => new Promise((_resolve, fail) => { reject = fail; }));
    const onApply = vi.fn();
    const m = mount(<AudioTrimEditor input="a.wav" disabled={false} onApply={onApply} />); mounts.push(m);
    click(m, "neptune.previewSelection");
    act(() => m.container.querySelector("audio")!.dispatchEvent(new Event("play")));
    expect(m.container.querySelector("[data-playing]")?.getAttribute("data-playing")).toBe("true");
    act(() => m.root.render(<AudioTrimEditor input="b.wav" disabled={false} onApply={onApply} />));
    expect(m.container.querySelector("audio")!.getAttribute("src")).toBe("b.wav");
    await act(async () => reject(new Error("old abort")));
    expect(pause).toHaveBeenCalled();
    expect(m.container.querySelector("[data-playing]")?.getAttribute("data-playing")).toBe("false");
    expect(m.container.textContent).not.toContain(t("neptune.previewFailed"));
  });
  it("settles a current rejection and natural end, then pauses on close", async () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockRejectedValueOnce(new Error("unsupported")).mockResolvedValue(undefined);
    const m = mount(<AudioTrimEditor input="a.wav" disabled={false} onApply={vi.fn()} />); mounts.push(m);
    click(m, "neptune.previewSelection"); await tick();
    expect(m.container.textContent).toContain(t("neptune.previewFailed"));
    click(m, "neptune.previewSelection"); await tick();
    expect(m.container.textContent).not.toContain(t("neptune.previewFailed"));
    act(() => m.container.querySelector("audio")!.dispatchEvent(new Event("play")));
    act(() => m.container.querySelector("audio")!.dispatchEvent(new Event("ended")));
    expect(m.container.querySelector("[data-playing]")?.getAttribute("data-playing")).toBe("false");
    expect(play).toHaveBeenCalledTimes(2);
    const before = pause.mock.calls.length;
    mounts.pop()!.unmount();
    expect(pause.mock.calls.length).toBe(before + 1);
  });
  it("restores the same media element after source release and StrictMode cleanup", async () => {
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    const load = vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    bridge.invoke.mockImplementation(async () => {
      expect(audio.hasAttribute("src")).toBe(false);
      expect(load).toHaveBeenCalled();
      return "trimmed-a.wav";
    });
    const m = mount(<StrictMode><AudioTrimEditor input="a.wav" disabled={false} onApply={vi.fn()} /></StrictMode>); mounts.push(m);
    const audio = m.container.querySelector("audio")!;
    expect(audio.getAttribute("src")).toBe("a.wav");
    click(m, "neptune.applyTrim"); await tick();
    expect(audio.hasAttribute("src")).toBe(false);
    click(m, "neptune.previewSelection"); await tick();
    expect(m.container.querySelector("audio")).toBe(audio);
    expect(audio.getAttribute("src")).toBe("a.wav");
    expect(play).toHaveBeenCalledOnce();
    act(() => m.root.render(<AudioTrimEditor input="b.wav" disabled={false} onApply={vi.fn()} />));
    expect(m.container.querySelector("audio")!.getAttribute("src")).toBe("b.wav");
  });

  it("does not apply an old trim result to a newly selected input", async () => {
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    let resolve!: (output: string) => void;
    bridge.invoke.mockImplementation(() => new Promise(done => { resolve = done; }));
    const onApply = vi.fn();
    const m = mount(<AudioTrimEditor input="a.wav" disabled={false} onApply={onApply} />); mounts.push(m);
    click(m, "neptune.applyTrim");
    act(() => m.root.render(<AudioTrimEditor input="b.wav" disabled={false} onApply={onApply} />));
    await act(async () => resolve("trimmed-a.wav"));
    expect(onApply).not.toHaveBeenCalled();
  });
});
