const { app, BrowserWindow, dialog, session } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const crypto = require('node:crypto');
const { spawn, spawnSync } = require('node:child_process');
const { createGateway } = require('./gateway.cjs');
const bundle = app.isPackaged ? process.resourcesPath : path.join(__dirname, '.stage', 'resources');
const config = JSON.parse(fs.readFileSync(path.join(bundle, 'runtime.json'), 'utf8'));
const runtime = path.join(app.getPath('appData'), 'OnbitnuriDemo');
app.setPath('userData', path.join(runtime, 'browser'));
const children = [];
let closing = false, gateway, win;
const smoke = process.argv.includes('--smoke-test');
function log(message) { fs.appendFileSync(path.join(runtime, 'desktop.log'), `${new Date().toISOString()} ${message}\n`); }
function launch(exe, args, env, cwd) {
  if (closing) throw new Error('Application is closing');
  const child = spawn(exe, args, { env, cwd, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  children.push(child);
  child.stdout.on('data', chunk => log(chunk.toString()));
  child.stderr.on('data', chunk => log(chunk.toString()));
  child.on('error', error => log(error.stack));
  child.on('exit', code => { log(`process ${child.pid} exited ${code}`); });
  child.on('exit', () => {
    if (!closing) {
      if (!smoke) dialog.showErrorBox('로컬 서버 종료', `서버가 예기치 않게 종료되었습니다. 앱을 다시 실행하세요. 로그: ${runtime}`);
      shutdown(); app.exit(1);
    }
  });
  return child;
}
async function port() {
  return new Promise((resolve, reject) => {
    const server = net.createServer(); server.on('error', reject);
    server.listen(0, '127.0.0.1', () => { const value = server.address().port; server.close(() => resolve(value)); });
  });
}
async function ready(url, child, timeout = 180000) {
  const end = Date.now() + timeout;
  while (!closing && Date.now() < end) {
    if (child.exitCode !== null) throw new Error(`서버가 종료되었습니다. 로그: ${runtime}`);
    try { const response = await fetch(url, { signal: AbortSignal.timeout(1000) }); if (response.ok) return await response.json(); } catch {}
    await new Promise(resolve => setTimeout(resolve, 300));
  }
  throw new Error(`서버 준비 시간 초과: ${url}. 로그: ${runtime}`);
}
function shutdown() {
  if (closing) return;
  closing = true;
  gateway?.close();
  for (const child of children.toReversed()) {
    if (child.pid && child.exitCode === null) spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, timeout: 15000 });
  }
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { win?.show(); win?.focus(); });
  app.on('before-quit', shutdown);
  app.on('window-all-closed', () => app.quit());
  process.on('exit', shutdown);
  app.whenReady().then(async () => {
    fs.mkdirSync(runtime, { recursive: true });
    fs.writeFileSync(path.join(runtime, 'desktop.log'), '');
    win = new BrowserWindow({ width: 1600, height: 920, show: !smoke, title: '온빛누리',
      icon: path.join(bundle, 'app.ico'),
      webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, partition: 'demo' } });
    win.removeMenu();
    win.on('page-title-updated', event => event.preventDefault());
    if (!smoke) win.maximize();
    win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    win.webContents.on('will-navigate', (event, url) => {
      if (!url.startsWith('http://127.0.0.1:')) event.preventDefault();
    });
    await win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent('<meta charset="utf-8"><body style="font:18px sans-serif;padding:60px">온빛누리 시연 환경을 준비하고 있습니다.<br><br>초기 데이터를 복원하고 로컬 서버를 실행합니다.</body>'));
    if (!fs.existsSync(config.python) || !fs.existsSync(config.ollama)) throw new Error('runtime.json의 Python/Ollama 실행 파일 경로를 확인하세요.');
    const data = path.join(runtime, 'data');
    // Only this app-owned directory may be replaced; never touch source databases.
    if (path.dirname(path.resolve(data)) !== path.resolve(runtime)) throw new Error('Invalid runtime path');
    fs.rmSync(data, { recursive: true, force: true });
    fs.cpSync(path.join(bundle, 'seed'), data, { recursive: true });
    const digest = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
    const restored = ['business.sqlite3', 'classifier/submissions.sqlite3'].filter(name => fs.existsSync(path.join(bundle, 'seed', name)))
      .every(name => digest(path.join(bundle, 'seed', name)) === digest(path.join(data, name)));
    if (!restored) throw new Error('시연 DB 초기 상태 복원에 실패했습니다.');
    const backendPort = await port();
    let ollamaPort = await port();
    while (ollamaPort === backendPort) ollamaPort = await port();
    const ollamaUrl = `http://127.0.0.1:${ollamaPort}`;
    const backendUrl = `http://127.0.0.1:${backendPort}`;
    const env = { ...process.env, PYTHONUTF8: '1', PYTHONDONTWRITEBYTECODE: '1',
      DB_PATH: path.join(data, 'business.sqlite3'), DATABASE_URL: `sqlite:///${path.join(data, 'business.sqlite3').replaceAll('\\', '/')}`,
      CLASSIFIER_DATA_DIR: path.join(data, 'classifier'), BUSINESS_API_URL: backendUrl,
      VERIFICATION_URL: backendUrl + '/classifier-api', OLLAMA_HOST: ollamaUrl, OLLAMA_URL: ollamaUrl,
      CLASSIFIER_MODEL: config.classifierModel, OPENAI_BASE_URL: ollamaUrl + '/v1', OPENAI_API_KEY: 'ollama',
      OPENAI_MODEL: config.chatModel, COPILOT_MODEL: config.chatModel,
      RAG_EMBEDDING_MODEL: config.embeddingModel || 'BAAI/bge-m3',
      PREDICTION_CACHE_DIR: path.join(data, 'prediction-cache') };
    const ollama = launch(config.ollama, ['serve'], env, bundle);
    const tags = await ready(ollamaUrl + '/api/tags', ollama, 30000);
    const missing = [config.classifierModel, config.chatModel].filter(model => !tags.models.some(item => item.name === model || item.model === model));
    if (missing.includes(config.classifierModel)) throw new Error(`문서 분석 모델을 설치하세요: ollama pull ${config.classifierModel}`);
    if (missing.length) log(`WARNING chatbot model missing: ollama pull ${config.chatModel}`);
    const backend = launch(config.python, ['-m', 'uvicorn', 'user.app.main:app', '--host', '127.0.0.1', '--port', String(backendPort)], env, path.join(bundle, 'backend'));
    await ready(backendUrl + '/health/db', backend);
    if (closing) return;
    gateway = createGateway(path.join(bundle, 'frontend'), backendPort);
    await new Promise(resolve => gateway.listen(0, '127.0.0.1', resolve));
    const origin = `http://127.0.0.1:${gateway.address().port}`;
    await session.fromPartition('demo').clearStorageData();
    await win.loadURL(origin);
    log(`READY ${origin}`);
    if (smoke) {
      await new Promise(resolve => setTimeout(resolve, 2500));
      const ragDeadline = Date.now() + 180000;
      while (true) {
        const status = await (await fetch(origin + '/rag-api/api/status')).json();
        if (status.ready) break;
        if (status.error || Date.now() > ragDeadline) throw new Error(status.error || 'RAG loading timeout');
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      const checks = await win.webContents.executeJavaScript(`(async () => {
        const get = async url => { const response = await fetch(url); if (!response.ok) throw new Error(url + ': ' + response.status); return response; };
        const submissions = await (await get('/classifier-api/submissions')).json();
        const types = await (await get('/classifier-api/application-types')).json();
        let pdf = null;
        if (submissions.length) { const response = await get('/classifier-api/submissions/' + submissions[0].id + '/pdf'); pdf = {type: response.headers.get('content-type'), bytes: (await response.arrayBuffer()).byteLength}; }
        const provision = await (await get('/classifier-api/verification-view/postponement.illness')).json();
        const searchResponse = await fetch('/rag-api/api/search', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question: '예비군 훈련', top_k: 3})});
        if (!searchResponse.ok) throw new Error('RAG search failed');
        const search = await searchResponse.json();
        return {db: await (await get('/api/health/db')).json(), submissions: submissions.length, types: types.length, pdf,
          ragSearch: search,
          provision: !!provision, rag: await (await get('/rag-api/api/status')).json(),
          rendered: document.body.innerText.length > 100, brokenImages: [...document.images].filter(img => !img.complete || !img.naturalWidth).map(img => img.src)};
      })()`);
      if (!checks.rendered || checks.brokenImages.length) throw new Error('화면/이미지 로딩 검사 실패');
      fs.writeFileSync(path.join(runtime, 'smoke.json'), JSON.stringify({ ...checks, restored, backendPid: backend.pid, ollamaPid: ollama.pid }, null, 2));
      fs.writeFileSync(path.join(runtime, 'smoke.png'), (await win.webContents.capturePage()).toPNG());
      app.quit();
    }
  }).catch(error => {
    log(error.stack);
    if (!smoke && !closing) dialog.showErrorBox('온빛누리 실행 오류', error.message);
    shutdown(); app.exit(1);
  });
}
