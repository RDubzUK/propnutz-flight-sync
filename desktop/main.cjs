const { app, BrowserWindow, dialog, Menu, session, shell } = require('electron');
const { randomBytes } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { startBackend, isAppUrl, isExternalUrl } = require('./backend.cjs');

app.setName('PropNutz Flight Sync');
let backend;
let window;
let quitting = false;
let shutdownComplete = false;

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (window) {
      if (window.isMinimized()) window.restore();
      window.show();
      window.focus();
    }
  });
  app.on('before-quit', event => {
    if (shutdownComplete || !backend) return;
    event.preventDefault();
    if (quitting) return;
    quitting = true;
    backend.stop().finally(() => { shutdownComplete = true; app.quit(); });
  });
  app.on('window-all-closed', () => app.quit());
  app.whenReady().then(start).catch(error => {
    if (quitting) return;
    dialog.showErrorBox('Flight Sync could not start', `${error.message}\n\nReinstall the app if its bundled files are missing.`);
    app.quit();
  });
}

async function start() {
  const userData = app.getPath('userData');
  const dataDir = path.resolve(process.env.FPV_AUDIO_DATA_DIR || path.join(userData, 'data'));
  fs.mkdirSync(dataDir, { recursive: true });
  fs.mkdirSync(userData, { recursive: true });
  const logs = path.join(userData, 'logs');
  fs.mkdirSync(logs, { recursive: true });
  const logPath = path.join(logs, 'backend.log');
  // Bound log size across launches; errors are also retained in the startup dialog.
  if (fs.existsSync(logPath) && fs.statSync(logPath).size > 1024 * 1024) fs.renameSync(logPath, logPath + '.old');
  let logBytes = fs.existsSync(logPath) ? fs.statSync(logPath).size : 0;
  const onLog = text => {
    if (logBytes >= 1024 * 1024) return;
    try { fs.appendFileSync(logPath, text); logBytes += Buffer.byteLength(text); } catch { /* startup dialog still has stderr */ }
  };
  const root = app.isPackaged ? process.resourcesPath : path.join(app.getAppPath(), 'build');
  const executable = path.join(root, 'backend', ...(app.isPackaged ? [] : ['flight-sync-backend']),
    `flight-sync-backend${process.platform === 'win32' ? '.exe' : ''}`);
  const media = path.join(root, 'media');
  if (!fs.existsSync(executable)) throw new Error(`Bundled backend is missing. ${app.isPackaged ? '' : 'Run npm run build:desktop first.'}`);
  for (const name of ['ffmpeg', 'ffprobe']) {
    if (!fs.existsSync(path.join(media, name + (process.platform === 'win32' ? '.exe' : '')))) {
      throw new Error(`Bundled ${name} is missing.`);
    }
  }

  const token = randomBytes(32).toString('hex');
  const env = { ...process.env, FPV_DESKTOP_TOKEN: token, FPV_AUDIO_DATA_DIR: dataDir,
    PYTHONUNBUFFERED: '1', OPENBLAS_NUM_THREADS: '1', OMP_NUM_THREADS: '1' };
  // Windows environment names are case insensitive; avoid duplicate Path/PATH keys.
  const oldPath = Object.keys(env).find(key => key.toLowerCase() === 'path');
  const systemPath = oldPath ? env[oldPath] : '';
  for (const key of Object.keys(env)) if (key.toLowerCase() === 'path') delete env[key];
  env.PATH = media + path.delimiter + systemPath;

  // Keep the origin stable across launches so browser preferences remain available.
  const portFile = path.join(userData, 'desktop-port.json');
  let port = 0;
  try {
    const saved = JSON.parse(fs.readFileSync(portFile, 'utf8'));
    if (Number.isInteger(saved.port) && saved.port > 0 && saved.port <= 65535) port = saved.port;
  } catch { /* first launch */ }
  backend = startBackend({ command: executable, args: ['--data-dir', dataDir, '--port', String(port)], env,
    cwd: userData, onLog, onExit: (code, signal, detail) => {
      if (quitting) return;
      dialog.showErrorBox('Flight Sync backend stopped', `The processing service stopped (${signal || code}). Restart the app to recover saved work.\n\n${detail}`);
      app.quit();
    } });
  const origin = await backend.ready;
  if (quitting) return;
  fs.writeFileSync(portFile, JSON.stringify({ port: Number(new URL(origin).port) }));

  const browserSession = session.fromPartition('persist:flight-sync');
  browserSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  browserSession.setPermissionCheckHandler(() => false);
  browserSession.webRequest.onBeforeSendHeaders({ urls: [origin + '/*'] }, (details, callback) => {
    callback({ requestHeaders: { ...details.requestHeaders, 'X-Flight-Sync-Token': token } });
  });
  browserSession.webRequest.onHeadersReceived({ urls: [origin + '/*'] }, (details, callback) => {
    callback({ responseHeaders: { ...details.responseHeaders,
      'Content-Security-Policy': ["default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"],
    } });
  });
  window = new BrowserWindow({ width: 1440, height: 1000, minWidth: 840, minHeight: 600,
    title: 'PropNutz Flight Sync', backgroundColor: '#171717', show: false,
    webPreferences: { session: browserSession, nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true },
  });
  const openExternal = value => {
    if (isExternalUrl(value)) shell.openExternal(value).catch(error => onLog(error.message + '\n'));
  };
  window.webContents.setWindowOpenHandler(({ url }) => { openExternal(url); return { action: 'deny' }; });
  window.webContents.on('will-navigate', (event, url) => {
    if (!isAppUrl(url, origin)) { event.preventDefault(); openExternal(url); }
  });
  window.webContents.on('will-redirect', (event, url) => {
    if (!isAppUrl(url, origin)) event.preventDefault();
  });
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.once('ready-to-show', () => window.show());
  window.on('closed', () => { window = null; });
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    ...(process.platform === 'darwin' ? [{ role: 'appMenu' }] : []),
    { label: 'File', submenu: [
      { label: 'Open app data folder', click: () => shell.openPath(dataDir) },
      { label: 'Open logs folder', click: () => shell.openPath(logs) },
      { type: 'separator' }, { role: 'quit' },
    ] },
    { role: 'editMenu' }, { role: 'viewMenu' },
    { label: 'Help', submenu: [{ label: 'PropNutz website', click: () => openExternal('https://www.propnutz.co.uk/') }] },
  ]));
  await window.loadURL(origin);
}
