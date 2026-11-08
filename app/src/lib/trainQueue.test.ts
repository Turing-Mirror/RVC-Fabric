// @vitest-environment happy-dom
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { activeJob, latestExperimentJob, trainPercent, useTrainingQueue, type TrainJob } from "./trainQueue";

const bridge = vi.hoisted(() => ({ invoke: vi.fn(), listen: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: bridge.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: bridge.listen }));
const job = (id: string, state: TrainJob["state"]): TrainJob => ({ id, state,
  req: { exp: `voice${id}`, sample_rate: "48k", dataset: "dataset", total_epoch: 200, batch_size: 4 },
  progress: { stage: "train", done: 100, total: 200 }, error: "" });
let root: Root;
let host: HTMLDivElement;
let current: ReturnType<typeof useTrainingQueue>;
let event: (event: { payload: { jobs: TrainJob[] } }) => void;
let unlisten: ReturnType<typeof vi.fn>;
function Harness() { current = useTrainingQueue(); return null; }
async function mount() {
  await act(async () => { root.render(createElement(Harness)); });
}
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  Object.assign(window, { __TAURI_INTERNALS__: {} });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  unlisten = vi.fn();
  bridge.invoke.mockReset().mockResolvedValue({ jobs: [] });
  bridge.listen.mockReset().mockImplementation(async (_name, callback) => { event = callback; return unlisten; });
});
afterEach(async () => { await act(async () => root.unmount()); host.remove(); });

describe("training queue reconnect", () => {
  it("distinguishes a cold pending queue read from an empty queue", async () => {
    let resolve!: (value: { jobs: TrainJob[] }) => void;
    bridge.invoke.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    await mount();
    expect(current.loaded).toBe(false);
    await act(async () => resolve({ jobs: [] }));
    expect(current.loaded).toBe(true);
    expect(current.jobs).toEqual([]);
  });
  it("restores current progress and observes jobs added while another is running", async () => {
    bridge.invoke.mockResolvedValue({ jobs: [job("1", "running")] });
    await mount();
    expect(activeJob(current.jobs)?.id).toBe("1");
    expect(trainPercent(activeJob(current.jobs))).toBe(70);
    await act(async () => event({ payload: { jobs: [job("1", "running"), job("2", "queued")] } }));
    expect(current.jobs.map(j => j.state)).toEqual(["running", "queued"]);
    await act(async () => root.unmount());
    root = createRoot(host);
    bridge.invoke.mockResolvedValue({ jobs: [job("1", "completed"), job("2", "running")] });
    await mount();
    expect(activeJob(current.jobs)?.id).toBe("2");
    expect(unlisten).toHaveBeenCalledOnce();
  });
  it("restores jobs and waiting state synchronously while the remount read is pending", async () => {
    bridge.invoke.mockResolvedValue({ jobs: [job("cached", "queued")], waiting_for_realtime: true });
    await mount();
    await act(async () => root.unmount());
    root = createRoot(host);
    bridge.invoke.mockImplementation(() => new Promise(() => {}));
    act(() => root.render(createElement(Harness)));
    expect(current.jobs[0].id).toBe("cached");
    expect(current.waitingForRealtime).toBe(true);
    expect(current.loaded).toBe(true);
  });
  it("does not let an unmounted reader replace the new cached snapshot", async () => {
    let resolve!: (value: { jobs: TrainJob[] }) => void;
    bridge.invoke.mockImplementationOnce(() => new Promise(r => { resolve = r; }));
    await mount();
    await act(async () => root.unmount());
    root = createRoot(host);
    await mount();
    await act(async () => event({ payload: { jobs: [job("new", "running")] } }));
    await act(async () => resolve({ jobs: [job("old", "running")] }));
    await act(async () => root.unmount());
    root = createRoot(host);
    bridge.invoke.mockImplementation(() => new Promise(() => {}));
    act(() => root.render(createElement(Harness)));
    expect(current.jobs[0].id).toBe("new");
  });
  it("does not replace a new progress event with an older pending snapshot", async () => {
    await mount();
    let resolve!: (value: { jobs: TrainJob[] }) => void;
    bridge.invoke.mockImplementationOnce(() => new Promise(r => { resolve = r; }));
    let pending!: Promise<void>;
    await act(async () => { pending = current.refresh(); });
    await act(async () => event({ payload: { jobs: [job("2", "running")] } }));
    await act(async () => { resolve({ jobs: [job("1", "running")] }); await pending; });
    expect(activeJob(current.jobs)?.id).toBe("2");
  });
  it("targets cancellation by job id and retains jobs if the action fails", async () => {
    bridge.invoke.mockResolvedValue({ jobs: [job("1", "running"), job("2", "queued")] });
    await mount();
    bridge.invoke.mockRejectedValueOnce(new Error("cannot save"));
    await act(async () => current.action("2", "remove"));
    expect(bridge.invoke).toHaveBeenCalledWith("train_queue_action", { id: "2", action: "remove" });
    expect(current.jobs).toHaveLength(2);
    expect(current.error).toContain("cannot save");
  });
  it("bounds progress and does not invent progress before the worker starts", () => {
    expect(trainPercent()).toBe(0);
    const running = job("1", "running");
    running.progress = null;
    expect(trainPercent(running)).toBe(0);
    expect(trainPercent(job("1", "completed"))).toBe(100);
  });
  it("marks completion only for the current experiment's latest task", () => {
    const completed = job("1", "completed");
    const unrelated = job("2", "completed");
    expect(latestExperimentJob([completed, unrelated], "new voice")).toBeUndefined();
    expect(latestExperimentJob([completed, unrelated], "")).toBeUndefined();
    expect(latestExperimentJob([completed, unrelated], " voice1 ")?.state).toBe("completed");
    const retry = { ...job("3", "running"), req: { ...completed.req } };
    expect(latestExperimentJob([completed, unrelated, retry], "voice1")?.state).toBe("running");
    retry.state = "failed";
    expect(latestExperimentJob([completed, unrelated, retry], "voice1")?.state).toBe("failed");
    expect(latestExperimentJob([completed, unrelated, retry], "voice2")?.state).toBe("completed");
  });

});
