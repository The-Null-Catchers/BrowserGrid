const test = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {capturePage, safeUrl, capturedPageFixture} = require('../../packages/browser-sdk/capture.cjs');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

function deferred() {
  let resolve;
  const promise = new Promise(done => {resolve = done;});
  return {promise, resolve};
}
function request(overrides = {}) {
  return {
    url: () => 'https://user:password@example.test/data?token=secret#private',
    method: () => 'GET', resourceType: () => 'fetch',
    response: async () => ({status: () => 200}),
    sizes: async () => ({requestHeadersSize: 20, responseBodySize: 30}),
    failure: () => ({errorText: 'net::ERR_FAILED'}), ...overrides,
  };
}

test('URLs omit credentials queries fragments and opaque URL payloads', () => {
  assert.equal(safeUrl('https://alice:password@example.test/api?token=secret#private'), 'https://example.test/api');
  assert.equal(safeUrl('wss://user:pass@example.test/socket?auth=secret'), 'wss://example.test/socket');
  assert.equal(safeUrl('data:text/plain,secret'), 'data:');
  assert.equal(safeUrl('file:///private/secret.txt'), 'file:');
  assert.equal(safeUrl('blob:https://example.test/private-secret'), 'blob:');
  assert.equal(safeUrl('invalid-secret-value'), '[invalid URL]');
  assert.equal(safeUrl('x'.repeat(8193)), '[URL omitted]');
});

test('teardown drains delayed network metadata before returning a snapshot', async () => {
  const page = new EventEmitter(), size = deferred();
  const capture = capturePage(page);
  const req = request({sizes: () => size.promise});
  page.emit('request', req); page.emit('requestfinished', req);
  const finish = capture.finish();
  size.resolve({responseBodySize: 45, privateHeader: 'secret', requestBodySize: -1});
  const events = await finish;
  assert.equal(events.network.length, 1);
  assert.equal(events.network[0].status, 200);
  assert.equal(events.network[0].url, 'https://example.test/data');
  assert.deepEqual(events.network[0].sizes, {responseBodySize: 45});
  assert.ok(events.network[0].duration_ms >= 0);
});

test('hung metadata has bounded teardown and late completion cannot change results', async () => {
  const page = new EventEmitter(), response = deferred();
  const capture = capturePage(page, {drainMs: 20});
  const req = request({response: () => response.promise});
  page.emit('request', req); page.emit('requestfinished', req);
  const events = await capture.finish();
  assert.equal(events.network[0].incomplete, true);
  assert.match(events.network[0].capture_error, /deadline/);
  const snapshot = JSON.stringify(events);
  response.resolve({status: () => 200});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(JSON.stringify(events), snapshot);
  assert.equal(page.eventNames().length, 0);
});

test('failed requests share the same safe URL representation', async () => {
  const page = new EventEmitter(), capture = capturePage(page), req = request();
  page.emit('request', req); page.emit('requestfailed', req);
  const row = (await capture.finish()).network[0];
  assert.equal(row.url, 'https://example.test/data');
  assert.equal(row.failure, 'net::ERR_FAILED');
  assert.ok(Number.isInteger(row.timestamp));
});

test('metadata errors preserve the observed HTTP status', async () => {
  const page = new EventEmitter(), capture = capturePage(page);
  const req = request({response: async () => ({status: () => 503}), sizes: async () => {throw Error('sensitive transport details');}});
  page.emit('request', req); page.emit('requestfinished', req);
  const row = (await capture.finish()).network[0];
  assert.equal(row.status, 503);
  assert.equal(row.incomplete, true);
  assert.equal(row.capture_error, 'Response metadata unavailable');
  assert.ok(!JSON.stringify(row).includes('sensitive'));
});

test('console source URLs use the same credential stripping', async () => {
  const page = new EventEmitter(), capture = capturePage(page);
  page.emit('console', {type: () => 'warn', text: () => 'x'.repeat(5000), location: () => ({url: 'https://u:p@example.test/a.js?secret=1', lineNumber: 5, columnNumber: 2})});
  const row = (await capture.finish()).console[0];
  assert.equal(row.message.length, 4000);
  assert.equal(row.source.url, 'https://example.test/a.js');
  assert.equal(row.source.lineNumber, 5);
});

test('active requests are explicitly reported incomplete at test end', async () => {
  const page = new EventEmitter(), capture = capturePage(page);
  page.emit('request', request());
  const row = (await capture.finish()).network[0];
  assert.equal(row.incomplete, true);
  assert.match(row.capture_error, /still active/);
});

test('pending plus active plus completed requests never exceed the event cap', async () => {
  const page = new EventEmitter(), capture = capturePage(page, {limit: 2}), gate = deferred();
  for (let n = 0; n < 20; n++) {
    const req = request({response: () => gate.promise});
    page.emit('request', req); page.emit('requestfinished', req);
  }
  gate.resolve({status: () => 200});
  assert.equal((await capture.finish()).network.length, 2);
});

test('duplicate finished events do not produce duplicate network rows', async () => {
  const page = new EventEmitter(), capture = capturePage(page), req = request();
  page.emit('request', req); page.emit('requestfinished', req); page.emit('requestfinished', req);
  assert.equal((await capture.finish()).network.length, 1);
});

test('capture detaches only its listeners and finish is idempotent', async () => {
  const page = new EventEmitter();
  const external = () => {};
  page.on('request', external);
  const capture = capturePage(page);
  const first = capture.finish();
  assert.equal(capture.finish(), first);
  await first;
  assert.deepEqual(page.listeners('request'), [external]);
});

test('failing test bodies still write real JSON artifact files', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'bg-capture-'));
  const page = new EventEmitter(), attached = [];
  const info = {outputPath: name => path.join(root, name), attach: async (name, data) => attached.push({name, ...data})};
  try {
    await assert.rejects(capturedPageFixture(page, async () => {
      page.emit('pageerror', Error('fixture failure'));
      throw Error('test failed');
    }, info), /test failed/);
    assert.equal(attached.length, 2);
    assert.equal(JSON.parse(fs.readFileSync(path.join(root, 'console.json')))[0].message, 'fixture failure');
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(root, 'network.json'))), []);
    assert.equal(page.eventNames().length, 0);
  } finally { fs.rmSync(root, {recursive: true, force: true}); }
});
