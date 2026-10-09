'use strict';

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const media = path.join(root, 'build', 'media');
const supported = new Set(['linux-x64', 'win32-x64', 'darwin-x64', 'darwin-arm64']);
const target = `${process.platform}-${process.arch}`;

function requireFile(file) {
  if (!fs.existsSync(file) || !fs.statSync(file).isFile() || fs.statSync(file).size === 0) {
    throw new Error(`Required build input is missing or empty: ${file}. Reinstall dependencies with npm ci.`);
  }
  return file;
}

function capture(executable, args) {
  const result = spawnSync(executable, args, {
    cwd: root, encoding: 'utf8', timeout: 30000, windowsHide: true, maxBuffer: 8 * 1024 * 1024,
  });
  if (result.error || result.status !== 0) {
    throw new Error(`Cannot run ${executable} ${args.join(' ')}: ${result.error?.message || result.stderr || result.status}`);
  }
  return result.stdout;
}

function verifyArchitecture(file) {
  const descriptor = fs.openSync(file, 'r');
  const read = (position, size) => {
    const buffer = Buffer.alloc(size);
    if (fs.readSync(descriptor, buffer, 0, size, position) !== size) {
      throw new Error(`Truncated native executable: ${file}`);
    }
    return buffer;
  };
  try {
    const header = read(0, 64);
    const magic = header.readUInt32BE(0);
    let platform;
    let architectures = [];
    if (magic === 0x7f454c46) {
      platform = 'linux';
      const machine = header[5] === 1 ? header.readUInt16LE(18) : header.readUInt16BE(18);
      architectures = [{ 62: 'x64', 183: 'arm64' }[machine]];
    } else if (header.toString('ascii', 0, 2) === 'MZ') {
      platform = 'win32';
      const pe = read(header.readUInt32LE(60), 6);
      if (pe.readUInt32LE(0) !== 0x4550) throw new Error(`Invalid PE executable: ${file}`);
      architectures = [{ 0x8664: 'x64', 0xaa64: 'arm64' }[pe.readUInt16LE(4)]];
    } else if ([0xfeedfacf, 0xcffaedfe].includes(magic)) {
      platform = 'darwin';
      const cpu = magic === 0xcffaedfe ? header.readUInt32LE(4) : header.readUInt32BE(4);
      architectures = [{ 0x01000007: 'x64', 0x0100000c: 'arm64' }[cpu]];
    } else if ([0xcafebabe, 0xcafebabf, 0xbebafeca, 0xbfbafeca].includes(magic)) {
      platform = 'darwin';
      const littleEndian = [0xbebafeca, 0xbfbafeca].includes(magic);
      const uint32 = (buffer, offset) => littleEndian ? buffer.readUInt32LE(offset) : buffer.readUInt32BE(offset);
      const count = uint32(header, 4);
      if (count > 20) throw new Error(`Invalid universal executable: ${file}`);
      const stride = [0xcafebabf, 0xbfbafeca].includes(magic) ? 32 : 20;
      for (let index = 0; index < count; index += 1) {
        architectures.push({ 0x01000007: 'x64', 0x0100000c: 'arm64' }[uint32(read(8 + index * stride, 4), 0)]);
      }
    }
    if (platform !== process.platform || !architectures.includes(process.arch)) {
      throw new Error(`Native binary ${file} does not match ${target}. Run npm ci on the target OS and architecture.`);
    }
  } finally {
    fs.closeSync(descriptor);
  }
}

function toolInput(packageName, name) {
  const packageFile = require.resolve(`${packageName}/package.json`);
  const packageRoot = path.dirname(packageFile);
  const metadata = require(packageFile);
  const suffix = process.platform === 'win32' ? '.exe' : '';
  const executable = require(packageName);
  const expected = path.join(packageRoot, name + suffix);
  if (typeof executable !== 'string' || path.resolve(executable) !== expected) {
    throw new Error(`${packageName} did not supply its native bundled executable. Remove binary-path overrides and run npm ci.`);
  }
  for (const file of [executable, `${executable}.README`, `${executable}.LICENSE`,
    path.join(packageRoot, 'LICENSE'), path.join(packageRoot, 'README.md')]) requireFile(file);
  verifyArchitecture(executable);
  const version = capture(executable, ['-version']);
  if (!version.startsWith(`${name} version `)) throw new Error(`Unexpected ${name} version output`);
  return { packageName, packageRoot, metadata, name, executable, version };
}

function main() {
  if (!supported.has(target)) throw new Error(`Desktop builds are not configured for ${target}.`);
  for (const [key, expected] of [['npm_config_platform', process.platform], ['npm_config_arch', process.arch]]) {
    if (process.env[key] && process.env[key] !== expected) {
      throw new Error(`${key} must match this build host (${expected}); cross-compiling the Python backend is unsupported.`);
    }
  }
  const tools = [toolInput('ffmpeg-static', 'ffmpeg'), toolInput('@derhuerst/ffprobe-static', 'ffprobe')];
  const encoders = capture(tools[0].executable, ['-hide_banner', '-encoders']);
  for (const codec of ['libx264', 'aac', 'dnxhd']) {
    if (!new RegExp(`^\\s*[VAS][A-Z.]{5}\\s+${codec}\\s`, 'm').test(encoders)) {
      throw new Error(`The bundled FFmpeg does not provide the required ${codec} encoder.`);
    }
  }
  // Clear only the generated media directory, after all source inputs validate.
  fs.rmSync(media, { recursive: true, force: true });
  fs.mkdirSync(media, { recursive: true });
  const manifest = { platform: process.platform, arch: process.arch, tools: {} };
  for (const tool of tools) {
    const destination = path.join(media, path.basename(tool.executable));
    fs.copyFileSync(tool.executable, destination);
    if (process.platform !== 'win32') fs.chmodSync(destination, 0o755);
    for (const extension of ['README', 'LICENSE']) {
      fs.copyFileSync(`${tool.executable}.${extension}`, `${destination}.${extension}`);
    }
    const notices = path.join(media, `${tool.name}-package`);
    fs.mkdirSync(notices);
    for (const name of ['README.md', 'LICENSE', 'package.json']) {
      fs.copyFileSync(path.join(tool.packageRoot, name), path.join(notices, name));
    }
    fs.writeFileSync(`${destination}.version.txt`, tool.version);
    manifest.tools[tool.name] = {
      package: tool.packageName, packageVersion: tool.metadata.version,
      version: tool.version.split(/\r?\n/, 1)[0],
      binaryRelease: tool.metadata[tool.packageName]['binary-release-tag'],
    };
  }
  fs.writeFileSync(path.join(media, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  fs.copyFileSync(path.join(root, 'desktop', 'THIRD_PARTY.md'), path.join(media, 'THIRD_PARTY.md'));
  const result = spawnSync('uv', ['run', '--frozen', '--group', 'desktop', 'pyinstaller',
    '--noconfirm', '--clean', '--distpath', 'build/backend', '--workpath', 'build/pyinstaller',
    'desktop/backend.spec'], { cwd: root, stdio: 'inherit', windowsHide: true });
  if (result.error || result.status !== 0) {
    throw new Error(`Backend build failed: ${result.error?.message || `exit ${result.status}`}`);
  }
  console.log(`Desktop backend and media tools built for ${target}. Run npm run smoke:backend before packaging.`);
}

try { main(); } catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
