import { expect, it } from "vitest";
import { enqueueJobIds, MAX_STORE_JOBS } from "./storeJobs";

it("starts immediately when a slot is free", () => {
  const next = enqueueJobIds("a", [], []);
  expect(next.launch).toBe(true);
  expect(next.running).toEqual(["a"]);
  expect(next.queued).toEqual([]);
});

it("queues past the concurrent cap instead of dropping the click", () => {
  const running = Array.from({ length: MAX_STORE_JOBS }, (_, i) => `r${i}`);
  const next = enqueueJobIds("wait", running, []);
  expect(next.launch).toBe(false);
  expect(next.running).toEqual(running);
  expect(next.queued).toEqual(["wait"]);
});

it("does not start the same voice twice", () => {
  expect(enqueueJobIds("a", ["a"], []).launch).toBe(false);
  expect(enqueueJobIds("a", [], ["a"]).launch).toBe(false);
});
