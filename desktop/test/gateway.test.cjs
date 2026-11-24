const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const { createGateway } = require('../gateway.cjs');

test('desktop serves assets/PDF ranges and preserves API prefixes, query, upload body', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'onbitnuri-gateway-'));
  fs.writeFileSync(path.join(root, 'index.html'), '<h1>demo</h1>');
  fs.writeFileSync(path.join(root, 'test.pdf'), '0123456789');
  const upstream = http.createServer((req, res) => {
    let body = ''; req.on('data', chunk => { body += chunk; });
    req.on('end', () => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ url: req.url, method: req.method, body })); });
  });
  await new Promise(resolve => upstream.listen(0, '127.0.0.1', resolve));
  const gateway = createGateway(root, upstream.address().port);
  await new Promise(resolve => gateway.listen(0, '127.0.0.1', resolve));
  t.after(() => { gateway.closeAllConnections(); upstream.closeAllConnections(); gateway.close(); upstream.close(); fs.rmSync(root, { recursive: true }); });
  const base = `http://127.0.0.1:${gateway.address().port}`;
  assert.match(await (await fetch(base)).text(), /demo/);
  const range = await fetch(base + '/test.pdf', { headers: { Range: 'bytes=2-5' } });
  assert.equal(range.status, 206); assert.equal(await range.text(), '2345');
  for (const prefix of ['/api', '/classifier-api', '/rag-api']) {
    const response = await fetch(base + prefix + '/test?q=1', { method: 'POST', body: 'pdf-upload-body' });
    assert.deepEqual(await response.json(), { url: (prefix === '/api' ? '' : prefix) + '/test?q=1', method: 'POST', body: 'pdf-upload-body' });
  }
  assert.equal((await fetch(base + '/not-present.png')).status, 404);
  assert.equal((await fetch(base + '/%2e%2e%5csecret.txt')).status, 403);
});
