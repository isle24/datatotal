import test from "node:test";
import assert from "node:assert/strict";
import { createLatestRequest, createPollLoop } from "../src/utils/requests.js";

test("late history responses cannot overwrite the selected period", async () => {
  const gate = createLatestRequest();
  let finishOld;
  const rendered = [];
  const old = gate.run(() => new Promise((resolve) => { finishOld = resolve; }), (value) => rendered.push(value));
  await gate.run(async () => "month", (value) => rendered.push(value));
  finishOld("day");
  await old;
  assert.deepEqual(rendered, ["month"]);
});

test("leaving a page cancels its outstanding request", async () => {
  const gate = createLatestRequest();
  let signal;
  let finish;
  let rendered = false;
  const request = gate.run((value) => { signal = value; return new Promise((resolve) => { finish = resolve; }); }, () => { rendered = true; });
  gate.cancel();
  assert.equal(signal.aborted, true);
  finish("old");
  await request;
  assert.equal(rendered, false);
  assert.equal(gate.busy, false);
});

test("polling is sequential, skips hidden pages, and cannot restart after stop", async () => {
  const jobs = [];
  let visible = false;
  let count = 0;
  let finish;
  const poller = createPollLoop(() => { count++; return new Promise((resolve) => { finish = resolve; }); }, 100, {
    shouldRun: () => visible, setTimer: (fn) => { jobs.push(fn); return 1; }, clearTimer: () => {},
  });
  poller.start();
  await jobs.shift()();
  assert.equal(count, 0);
  visible = true;
  const pending = jobs.shift()();
  assert.equal(count, 1);
  assert.equal(jobs.length, 0);
  poller.stop();
  finish();
  await pending;
  assert.equal(jobs.length, 0);
});
