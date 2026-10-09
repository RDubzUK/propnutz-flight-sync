'use strict';

// Exercise the frozen distribution, including its bundled assets and media tools.
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const readline = require('node:readline');

const root = path.resolve(__dirname, '..');
const suffix = process.platform === 'win32' ? '.exe' : '';
const executable = path.join(root, 'build', 'backend', 'flight-sync-backend', `flight-sync-backend${suffix}`);
const media = path.join(root, 'build', 'media');

function within(promise, milliseconds, description) {
  let timer;
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Timed out waiting for ${description}`)), milliseconds);
    }),
  ]).finally(() => clearTimeout(timer));
}

function request(url, token) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, {
      headers: token ? { 'X-Flight-Sync-Token': token } : {},
      timeout: 15000,
    }, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => { body += chunk; });
      response.on('end', () => resolve({ status: response.statusCode, body }));
      response.on('error', reject);
    });
    req.on('timeout', () => req.destroy(new Error(`HTTP request timed out: ${url}`)));
    req.on('error', reject);
  });
}

async function main() {
  assert.ok(fs.statSync(executable).isFile(), 'Build the frozen backend before running its smoke test');
  for (const name of ['ffmpeg', 'ffprobe']) {
    assert.ok(fs.statSync(path.join(media, `${name}${suffix}`)).isFile(), `Missing bundled ${name}`);
  }
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'flight-sync-smoke-'));
  const data = path.join(temporary, 'desktop data');
  const token = randomBytes(32).toString('hex');
  const env = { ...process.env, FPV_DESKTOP_TOKEN: token, FPV_AUDIO_DATA_DIR: data,
    OPENBLAS_NUM_THREADS: '1', OMP_NUM_THREADS: '1' };
  // Windows treats environment variable names case-insensitively.
  for (const key of Object.keys(env)) {
    if (key.toLowerCase() === 'path') delete env[key];
  }
  // No host ffmpeg or Python on PATH: the packaged distribution must stand alone.
  env.PATH = media;
  const child = spawn(executable, ['--data-dir', data, '--port', '0'], {
    cwd: temporary, env, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
  });
  // A crash during shutdown can close the pipe before the write completes;
  // report the process exit below and still run the temporary-folder cleanup.
  child.stdin.on('error', () => {});
  let stderr = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => { stderr = (stderr + chunk).slice(-32000); });
  const closed = new Promise((resolve) => {
    child.once('close', (code, signal) => resolve({ code, signal }));
  });
  const lines = readline.createInterface({ input: child.stdout });
  try {
    const announcement = await within(new Promise((resolve, reject) => {
      child.once('error', reject);
      child.once('close', (code) => reject(new Error(`Backend exited before ready (${code}): ${stderr}`)));
      lines.once('line', (line) => {
        try { resolve(JSON.parse(line)); } catch (error) { reject(error); }
      });
    }), 45000, 'backend readiness');
    assert.equal(announcement.event, 'ready');
    assert.match(announcement.url, /^http:\/\/127\.0\.0\.1:[1-9][0-9]*$/);
    const base = announcement.url;
    for (const route of ['/', '/static/bootstrap.js', '/api/system']) {
      assert.equal((await request(base + route)).status, 401, `${route} must require authentication`);
    }
    const page = await request(base + '/', token);
    assert.equal(page.status, 200);
    assert.match(page.body, /<html[\s>]/i);
    const script = await request(base + '/static/bootstrap.js', token);
    assert.equal(script.status, 200);
    assert.ok(script.body.trim().length > 0, 'Bundled JavaScript must not be empty');
    const systemResponse = await request(base + '/api/system', token);
    assert.equal(systemResponse.status, 200);
    const system = JSON.parse(systemResponse.body);
    assert.equal(system.name, 'PropNutz Flight Sync');
    assert.equal(system.version, require('../package.json').version);
    assert.equal(fs.realpathSync(system.data), fs.realpathSync(data));
    assert.equal(system.ffmpeg, true);
    assert.equal(system.ffprobe, true);
    const diagnosticsResponse = await request(base + '/api/diagnostics?include_paths=true', token);
    assert.equal(diagnosticsResponse.status, 200);
    const diagnostics = JSON.parse(diagnosticsResponse.body);
    assert.equal(diagnostics.app_version, system.version);
    assert.equal(diagnostics.instance_lock, true);
    assert.equal(diagnostics.data_folder.available, true);
    for (const name of ['ffmpeg', 'ffprobe']) {
      assert.equal(diagnostics.tools[name].available, true, `${name} must be available`);
      assert.equal(diagnostics.tools[name].working, true, `${name} must run`);
      assert.equal(fs.realpathSync(diagnostics.tools[name].path),
        fs.realpathSync(path.join(media, `${name}${suffix}`)));
    }
    child.stdin.end('shutdown\n');
    const result = await within(closed, 15000, 'graceful backend shutdown');
    assert.equal(result.code, 0, `Backend shutdown failed: ${stderr}`);
    assert.equal(result.signal, null);
    assert.ok(!stderr.includes(token), 'Backend must not log the authentication token');
    console.log(`Frozen backend smoke test passed (${process.platform}/${process.arch}, v${system.version}).`);
  } catch (error) {
    if (stderr) console.error(stderr.replaceAll(token, '[redacted]'));
    throw error;
  } finally {
    lines.close();
    child.stdin.destroy();
    if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
    // Never remove the data directory while its backend still has it open.
    await within(closed, 10000, 'backend process cleanup');
    fs.rmSync(temporary, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
