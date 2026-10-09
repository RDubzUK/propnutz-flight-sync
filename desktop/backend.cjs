const { spawn } = require('node:child_process');

function isAppUrl(value, origin) {
  try {
    const url = new URL(value);
    return url.origin === origin && !url.username && !url.password;
  } catch { return false; }
}

function isExternalUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password &&
      ['propnutz.co.uk', 'www.propnutz.co.uk', 'github.com'].includes(url.hostname);
  } catch { return false; }
}

function validBackendUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' && url.hostname === '127.0.0.1' &&
      Boolean(url.port) && value === url.origin;
  } catch { return false; }
}

function killTree(child) {
  if (!child.pid) return;
  if (process.platform === 'win32') {
    const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
    killer.on('error', () => child.kill());
  } else {
    try { process.kill(-child.pid, 'SIGKILL'); } catch (error) {
      if (error.code !== 'ESRCH') child.kill('SIGKILL');
    }
  }
}

function startBackend({ command, args, env = process.env, cwd, timeout = 60000,
  shutdownTimeout = 8000, onLog = () => {}, onExit = () => {} }) {
  const child = spawn(command, args, {
    env, cwd, windowsHide: true, detached: process.platform !== 'win32',
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  let pending = '';
  let diagnostics = '';
  let started = false;
  let settled = false;
  let stopping;
  let closed = false;
  let resolveReady, rejectReady;
  const ready = new Promise((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
  const fail = error => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    rejectReady(error);
  };
  const timer = setTimeout(() => {
    fail(new Error(`Backend startup timed out.\n${diagnostics}`));
    void stop();
  }, timeout);
  const exited = new Promise(resolve => {
    child.once('close', (code, signal) => {
      closed = true;
      clearTimeout(timer);
      fail(new Error(`Backend exited (${signal || code}) before startup.\n${diagnostics}`));
      resolve();
      if (started && !stopping) onExit(code, signal, diagnostics);
    });
  });
  child.on('error', error => fail(error));
  child.stdin.on('error', () => {}); // Child can close its pipe before shutdown is requested.
  child.stderr.setEncoding('utf8');
  child.stdout.setEncoding('utf8');
  child.stderr.on('data', text => {
    diagnostics = (diagnostics + text).slice(-16000);
    onLog(text);
  });
  child.stdout.on('data', text => {
    pending += text;
    if (pending.length > 65536) {
      fail(new Error('Backend sent an oversized startup message.'));
      void stop();
      return;
    }
    let newline;
    while ((newline = pending.indexOf('\n')) !== -1) {
      const line = pending.slice(0, newline);
      pending = pending.slice(newline + 1);
      let message;
      try { message = JSON.parse(line); } catch { onLog(line + '\n'); continue; }
      if (message.event !== 'ready' || settled) continue;
      if (!validBackendUrl(message.url)) {
        fail(new Error('Invalid backend address.'));
        void stop();
        return;
      }
      clearTimeout(timer);
      settled = true;
      started = true;
      resolveReady(message.url);
    }
  });

  function stop() {
    if (stopping) return stopping;
    // Defer until stopping is assigned, including when the process already exited.
    stopping = Promise.resolve().then(async () => {
      if (!closed && child.pid) {
        child.stdin.end('shutdown\n');
        const force = setTimeout(() => killTree(child), shutdownTimeout);
        await exited;
        clearTimeout(force);
      }
      // POSIX children share the detached process group, including FFmpeg workers.
      if (process.platform !== 'win32') killTree(child);
    });
    return stopping;
  }

  return { child, ready, stop };
}

module.exports = { startBackend, isAppUrl, isExternalUrl };
