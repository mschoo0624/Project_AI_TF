const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.pdf': 'application/pdf', '.woff2': 'font/woff2' };

function createGateway(root, backendPort) {
  return http.createServer((req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    const isApi = ['/api', '/classifier-api', '/rag-api'].some(p => url.pathname === p || url.pathname.startsWith(p + '/'));
    if (isApi) {
      const target = url.pathname.replace(/^\/api(?=\/|$)/, '') || '/';
      const upstream = http.request({ hostname: '127.0.0.1', port: backendPort, path: target + url.search,
        method: req.method, headers: { ...req.headers, host: `127.0.0.1:${backendPort}` } }, response => {
        res.writeHead(response.statusCode, response.headers); response.pipe(res);
      });
      upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end('Backend unavailable'); });
      res.on('close', () => upstream.destroy());
      req.pipe(upstream); return;
    }
    try {
      if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405); res.end(); return; }
      const name = decodeURIComponent(url.pathname);
      const file = path.resolve(root, '.' + name);
      if (!file.startsWith(path.resolve(root) + path.sep) && file !== path.resolve(root)) {
        res.writeHead(403); res.end(); return;
      }
      const selected = name === '/' ? path.join(root, 'index.html') : file;
      if (!fs.existsSync(selected) || !fs.statSync(selected).isFile()) { res.writeHead(404); res.end(); return; }
      const size = fs.statSync(selected).size;
      let start = 0, end = size - 1, status = 200;
      if (req.headers.range) {
        const match = /^bytes=(\d+)-(\d*)$/.exec(req.headers.range);
        if (!match) { res.writeHead(416, { 'Content-Range': `bytes */${size}` }); res.end(); return; }
        start = Number(match[1]); end = match[2] ? Math.min(Number(match[2]), end) : end; status = 206;
        if (start > end) { res.writeHead(416, { 'Content-Range': `bytes */${size}` }); res.end(); return; }
      }
      const headers = { 'Content-Type': mime[path.extname(selected)] || 'application/octet-stream',
        'Content-Length': Math.max(0, end - start + 1), 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store' };
      if (status === 206) headers['Content-Range'] = `bytes ${start}-${end}/${size}`;
      res.writeHead(status, headers);
      if (req.method === 'HEAD' || size === 0) res.end();
      else fs.createReadStream(selected, { start, end }).pipe(res);
    } catch { res.writeHead(400); res.end(); }
  });
}
module.exports = { createGateway };
