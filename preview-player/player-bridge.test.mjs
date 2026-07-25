import assert from "node:assert/strict";
import test from "node:test";
import {
  createReadinessGate,
  createRequestGate,
  isTrustedLoadMessage,
} from "./player-bridge.js";


test("readiness waits for both Unity instance and receiver callback", () => {
  const ready = [];
  const instance = { SendMessage() {} };
  const first = createReadinessGate((value) => ready.push(value));

  first.markReceiverReady();
  assert.equal(ready.length, 0);
  first.setInstance(instance);
  assert.deepEqual(ready, [instance]);
  first.markReceiverReady();
  first.setInstance(instance);
  assert.equal(ready.length, 1);

  const reverseReady = [];
  const reverse = createReadinessGate((value) => reverseReady.push(value));
  reverse.setInstance(instance);
  assert.equal(reverseReady.length, 0);
  reverse.markReceiverReady();
  assert.deepEqual(reverseReady, [instance]);
});


test("request gate ignores duplicate ids and invalidates older work", () => {
  const gate = createRequestGate();
  const first = gate.claim("request-1");
  assert.equal(typeof first, "number");
  assert.equal(gate.claim("request-1"), null);
  assert.equal(gate.isCurrent(first), true);

  const second = gate.claim("request-2");
  assert.equal(gate.isCurrent(first), false);
  assert.equal(gate.isCurrent(second), true);
  gate.cancel();
  assert.equal(gate.isCurrent(second), false);
});


test("load messages require matching parent, origin, protocol, and session", () => {
  const parent = {};
  const base = {
    origin: "https://przppz.club",
    source: parent,
    data: {
      type: "zppz.preview.load",
      version: 2,
      session_id: "session-1",
    },
  };

  assert.equal(isTrustedLoadMessage(base, parent, base.origin, "session-1"), true);
  assert.equal(isTrustedLoadMessage({ ...base, origin: "https://evil.example" }, parent, base.origin, "session-1"), false);
  assert.equal(isTrustedLoadMessage({ ...base, source: {} }, parent, base.origin, "session-1"), false);
  assert.equal(isTrustedLoadMessage({ ...base, data: { ...base.data, version: 1 } }, parent, base.origin, "session-1"), false);
  assert.equal(isTrustedLoadMessage(base, parent, base.origin, "session-2"), false);
});
