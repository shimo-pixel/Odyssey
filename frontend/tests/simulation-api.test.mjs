import test from 'node:test';
import assert from 'node:assert/strict';
import { setImmediate } from 'node:timers/promises';
import { API, buildPayload } from '../js/api.js';

const flush = () => setImmediate();
function clock(t) {
  const pending = new Map();
  let id = 0;
  t.mock.method(globalThis, 'setTimeout', (fn, ms) => { pending.set(++id, { fn, ms }); return id; });
  t.mock.method(globalThis, 'clearTimeout', timer => pending.delete(timer));
  return {
    pending,
    next() {
      const [key, timer] = pending.entries().next().value;
      pending.delete(key); timer.fn(); return timer.ms;
    },
  };
}
function gate() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }

test('creation payload includes the selected catalog model', () => {
  assert.equal(buildPayload({ goal: 'Goal', modelId: 'chosen-b' }).config.model_id, 'chosen-b');
});

test('polling awaits both network and asynchronous UI updates', async t => {
  const scheduler = clock(t), network = gate(), render = gate();
  let calls = 0;
  t.mock.method(API, 'getStatus', async () => { calls++; return network.promise; });
  const stop = API.pollStatus('id', async () => render.promise);
  await flush();
  assert.equal(calls, 1); assert.equal(scheduler.pending.size, 0);
  network.resolve({ status: 'running' }); await flush();
  assert.equal(scheduler.pending.size, 0);
  render.resolve(); await flush();
  assert.equal([...scheduler.pending.values()][0].ms, 1500);
  stop(); assert.equal(scheduler.pending.size, 0);
});

test('failures back off, stop after five failures, and reconnect manually', async t => {
  const scheduler = clock(t), states = [];
  let online = false;
  t.mock.method(API, 'getStatus', async () => { if (online) return { status: 'completed' }; throw new Error('offline'); });
  const stop = API.pollStatus('id', () => {}, { onConnection: s => states.push(s) });
  await flush();
  for (const delay of [3000, 6000, 12000, 24000]) {
    assert.equal(scheduler.next(), delay); await flush();
  }
  assert.equal(states.at(-1).state, 'disconnected');
  assert.equal(scheduler.pending.size, 0);
  online = true;
  stop.reconnect(); await flush();
  assert.equal(states.at(-1).state, 'connected');
  assert.equal(scheduler.pending.size, 0);
  stop();
});

test('missing records stop without treating the task as failed', async t => {
  const scheduler = clock(t), states = [];
  t.mock.method(API, 'getStatus', async () => { throw Object.assign(new Error('missing'), { status: 404 }); });
  const stop = API.pollStatus('missing', () => assert.fail('unexpected state update'), { onConnection: s => states.push(s) });
  await flush();
  assert.equal(states[0].state, 'missing'); assert.equal(scheduler.pending.size, 0);
  stop();
});

test('unmount aborts requests and ignores late responses', async t => {
  const scheduler = clock(t), network = gate();
  let signal, updates = 0;
  t.mock.method(API, 'getStatus', async (id, options) => { signal = options.signal; return network.promise; });
  const stop = API.pollStatus('old', () => updates++);
  stop(); assert.equal(signal.aborted, true);
  network.resolve({ status: 'running' }); await flush();
  assert.equal(updates, 0); assert.equal(scheduler.pending.size, 0);
});

for (const status of ['completed', 'failed', 'cancelled', 'interrupted']) {
  test(`terminal state ${status} ends polling`, async t => {
    const scheduler = clock(t);
    t.mock.method(API, 'getStatus', async () => ({ status }));
    const stop = API.pollStatus('id', () => {});
    await flush(); assert.equal(scheduler.pending.size, 0); stop();
  });
}

test('status requests timeout after ten seconds', async t => {
  const scheduler = clock(t);
  t.mock.method(globalThis, 'fetch', async (url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
  }));
  const response = API.getStatus('slow');
  assert.equal(scheduler.next(), 10000);
  await assert.rejects(response, /超时|timeout|timed out/i);
});
