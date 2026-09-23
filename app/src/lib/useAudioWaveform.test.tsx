// @vitest-environment happy-dom
import { act } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { mount, tick, type Mounted } from "../test/dom";

const shell = vi.hoisted(() => ({ invoke: vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: shell.invoke }));

import { useAudioWaveform } from "./useAudioWaveform";

const mounts: Mounted[] = [];
afterEach(() => {
  while (mounts.length) mounts.pop()?.unmount();
  shell.invoke.mockReset();
});

it("切换文件后不会显示旧波形或接受过期结果", async () => {
  const resolve: Record<string, (value: unknown) => void> = {};
  shell.invoke.mockImplementation((cmd, args) => {
    if (cmd === "audio_waveform_cancel") return Promise.resolve(true);
    const input = (args as { input: string }).input;
    return new Promise((done) => { resolve[input] = done; });
  });
  function Probe({ input }: { input: string }) {
    const waveform = useAudioWaveform(input);
    return <span>{waveform.duration || "loading"}</span>;
  }
  const mounted = mount(<Probe input="first.wav" />);
  mounts.push(mounted);
  act(() => mounted.root.render(<Probe input="second.wav" />));
  expect(mounted.container.textContent).toBe("loading");
  resolve["first.wav"]({ duration: 100, peaks: [255] });
  await tick();
  expect(mounted.container.textContent).toBe("loading");
  resolve["second.wav"]({ duration: 7, peaks: [128] });
  await tick();
  expect(mounted.container.textContent).toBe("7");
  expect(shell.invoke.mock.calls.some(([cmd]) => cmd === "audio_waveform_cancel")).toBe(true);
});
