const assert = require('node:assert/strict');
const { test } = require('node:test');
const { startBackend, isAppUrl, isExternalUrl } = require('../backend.cjs');

function launch(source, options = {}) {
  return startBackend({ command: process.execPath, args: ['-e', source], timeout: 1000, ...options });
}

test('accepts split readiness messages and shuts down the child', async () => {
  const backend = launch(`
    process.stdout.write('{"event":"ready",');
    setTimeout(() => process.stdout.write('"url":"http://127.0.0.1:45678"}\\n'), 10);
    process.stdin.on('data', () => process.exit(0));
  `);
  assert.equal(await backend.ready, 'http://127.0.0.1:45678');
  await backend.stop();
  assert.equal(backend.child.exitCode, 0);
});

test('rejects a child that exits before startup and includes diagnostic output', async () => {
  const backend = launch("process.stderr.write('missing media tool'); process.exit(2)");
  await assert.rejects(backend.ready, /missing media tool/);
  await backend.stop();
});

test('rejects readiness for non-loopback addresses', async () => {
  const backend = launch(`console.log(JSON.stringify({event:'ready', url:'https://example.com'})); setInterval(() => {}, 1000)`, { shutdownTimeout: 100 });
  await assert.rejects(backend.ready, /Invalid backend address/);
  await backend.stop();
});

test('startup timeout terminates an unresponsive child', async () => {
  const backend = launch('setInterval(() => {}, 1000)', { timeout: 100, shutdownTimeout: 100 });
  await assert.rejects(backend.ready, /timed out/);
  await backend.stop();
  assert.ok(backend.child.exitCode !== null || backend.child.signalCode !== null);
});

test('reports spawn failures without an unhandled child error', async () => {
  const backend = startBackend({command: '/missing/flight-sync-backend', args: [], timeout: 500});
  await assert.rejects(backend.ready, /ENOENT/);
  await backend.stop();
});

test('navigation permits only the exact backend origin or approved HTTPS links', () => {
  const origin = 'http://127.0.0.1:45678';
  assert.equal(isAppUrl(origin + '/api/exports', origin), true);
  for (const url of ['http://127.0.0.1:1/', 'http://127.0.0.1.evil.test:45678/', 'file:///etc/passwd', 'bad url']) {
    assert.equal(isAppUrl(url, origin), false);
  }
  assert.equal(isExternalUrl('https://www.propnutz.co.uk/'), true);
  assert.equal(isExternalUrl('https://github.com/S33G/propnutz-flight-sync/releases'), true);
  for (const url of ['https://evil.test/', 'http://www.propnutz.co.uk/', 'https://user:password@www.propnutz.co.uk/', 'file:///tmp/test']) {
    assert.equal(isExternalUrl(url), false);
  }
});
