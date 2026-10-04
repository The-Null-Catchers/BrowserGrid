const {performance} = require('node:perf_hooks');

function safeUrl(value) {
  if (typeof value !== 'string' || value.length > 8192) return '[URL omitted]';
  try {
    const url = new URL(value);
    if (!['http:', 'https:', 'ws:', 'wss:'].includes(url.protocol)) return url.protocol;
    url.username = ''; url.password = ''; url.search = ''; url.hash = '';
    return url.toString().slice(0, 2000);
  } catch { return '[invalid URL]'; }
}

function capturePage(page, {limit = 1000, drainMs = 2000} = {}) {
  const consoleEvents = [], networkEvents = [], active = new Map(), pending = new Map();
  let closed = false, finishing;
  const text = (value, length) => typeof value === 'string' ? value.slice(0, length) : '';
  const record = (request, started) => ({
    method: text(request.method(), 20), url: safeUrl(request.url()),
    resource_type: text(request.resourceType(), 40), timestamp: started.timestamp,
    duration_ms: Math.max(0, Math.round(performance.now() - started.clock)),
  });
  const append = row => { if (!closed && networkEvents.length < limit) networkEvents.push(row); };
  const handlers = {
    console: msg => {
      if (consoleEvents.length >= limit) return;
      const source = msg.location();
      consoleEvents.push({
        type: text(msg.type(), 40), message: text(msg.text(), 4000), timestamp: Date.now(),
        source: {
          url: safeUrl(source.url),
          lineNumber: Number.isInteger(source.lineNumber) ? source.lineNumber : null,
          columnNumber: Number.isInteger(source.columnNumber) ? source.columnNumber : null,
        },
      });
    },
    pageerror: error => {
      if (consoleEvents.length < limit) consoleEvents.push({type: 'pageerror', message: text(error.message, 4000), timestamp: Date.now()});
    },
    request: request => {
      if (networkEvents.length + active.size + pending.size < limit && !active.has(request)) {
        active.set(request, {timestamp: Date.now(), clock: performance.now()});
      }
    },
    requestfinished: request => {
      const started = active.get(request);
      if (!started) return;
      active.delete(request);
      const row = record(request, started);
      const task = (async () => {
        try {
          const response = await request.response();
          const status = response?.status();
          row.status = Number.isInteger(status) && status >= 100 && status <= 599 ? status : null;
          const sizes = await request.sizes();
          const safeSizes = {};
          for (const key of ['requestBodySize', 'requestHeadersSize', 'responseBodySize', 'responseHeadersSize']) {
            if (Number.isSafeInteger(sizes[key]) && sizes[key] >= 0) safeSizes[key] = sizes[key];
          }
          append({...row, sizes: safeSizes});
        } catch { append({...row, incomplete: true, capture_error: 'Response metadata unavailable'}); }
      })();
      pending.set(task, row);
      task.then(() => pending.delete(task), () => pending.delete(task));
    },
    requestfailed: request => {
      const started = active.get(request);
      if (!started) return;
      active.delete(request);
      append({...record(request, started), failure: text(request.failure()?.errorText, 1000)});
    },
  };
  for (const [name, handler] of Object.entries(handlers)) page.on(name, handler);

  function finish() {
    if (finishing) return finishing;
    // Stop accepting page events before draining existing asynchronous metadata reads.
    for (const [name, handler] of Object.entries(handlers)) page.off(name, handler);
    finishing = (async () => {
      let timer;
      if (pending.size) {
        try {
          await Promise.race([
            Promise.allSettled([...pending.keys()]),
            new Promise(resolve => { timer = setTimeout(resolve, drainMs); }),
          ]);
        } finally { clearTimeout(timer); }
      }
      for (const row of pending.values()) append({...row, incomplete: true, capture_error: 'Metadata drain deadline exceeded'});
      for (const [request, started] of active) append({...record(request, started), incomplete: true, capture_error: 'Request still active at test end'});
      closed = true;
      active.clear(); pending.clear();
      return {console: [...consoleEvents], network: [...networkEvents]};
    })();
    return finishing;
  }
  return {finish};
}
async function capturedPageFixture(page, use, testInfo) {
  const capture = capturePage(page);
  try { await use(page); }
  finally {
    const events = await capture.finish();
    const fs = require('node:fs');
    const path = require('node:path');
    for (const [name, content] of [['console.json', events.console], ['network.json', events.network]]) {
      const file = testInfo.outputPath(name);
      fs.mkdirSync(path.dirname(file), {recursive: true});
      fs.writeFileSync(file, JSON.stringify(content));
      await testInfo.attach(name, {path: file, contentType: 'application/json'});
    }
  }
}
module.exports = {capturePage, safeUrl, capturedPageFixture};
