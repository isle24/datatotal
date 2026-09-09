import test from "node:test";
import assert from "node:assert/strict";
import { createNasTransport } from "../src/api/transport.js";

function harness() {
  const calls = [];
  const invoke = async (command, args) => {
    calls.push({ command, args });
    if (command === "nas_request") {
      args.onPacket.onmessage({ type: "headers", status: 200 });
      args.onPacket.onmessage({
        type: "chunk",
        bytes: [...new TextEncoder().encode('data: {"ok":true}\n\n')],
      });
      args.onPacket.onmessage({ type: "done" });
    }
  };
  const profile = { id: "one", name: "NAS", url: "http://127.0.0.1:8088" };
  return {
    calls,
    transport: createNasTransport({
      profile,
      invoke,
      Channel: class {},
      confirm: async () => true,
      prompt: async () => null,
    }),
  };
}
test("NAS transport preserves stream bytes and profile identity", async () => {
  const { calls, transport } = harness();
  assert.equal(
    await (await transport.fetch("/api/ai/chat?stream=true")).text(),
    'data: {"ok":true}\n\n',
  );
  assert.equal(calls[0].args.request.profileId, "one");
  assert.equal(transport.hostname(), "127.0.0.1");
});
test("disposed NAS transports cannot send requests to another source", async () => {
  const { calls, transport } = harness();
  transport.dispose();
  await assert.rejects(transport.fetch("/api/overview"), {
    name: "AbortError",
  });
  assert.equal(calls.filter((c) => c.command === "nas_request").length, 0);
});
test("aborted requests never enter native transport", async () => {
  const { calls, transport } = harness();
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    transport.fetch("/api/overview", { signal: controller.signal }),
    { name: "AbortError" },
  );
  assert.equal(calls.length, 0);
});
