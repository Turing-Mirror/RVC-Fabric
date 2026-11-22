import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const verifier = fileURLToPath(new URL('../scripts/beta_verify.mjs', import.meta.url));

function fixture(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'rvc-beta-key-'));
  t.after(() => fs.rmSync(directory, { recursive: true }));
  const installer = path.join(directory, 'RVC-Fabric-Setup-1.8.2-beta.12.exe');
  const bytes = Buffer.from('Beta installer fixture');
  fs.writeFileSync(installer, bytes);
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
  const rawKey = publicKey.export({ format: 'der', type: 'spki' }).subarray(-32);
  const id = crypto.randomBytes(8);
  const keyPacket = Buffer.concat([Buffer.from('Ed'), id, rawKey]);
  const pubkey = Buffer.from(`untrusted comment: Beta test key\n${keyPacket.toString('base64')}\n`).toString('base64');
  const signature = crypto.sign(null, crypto.createHash('blake2b512').update(bytes).digest(), privateKey);
  const packet = Buffer.concat([Buffer.from('ED'), id, signature]);
  const comment = 'timestamp:1795305600\tfile:beta-setup.exe';
  const global = crypto.sign(null, Buffer.concat([signature, Buffer.from(comment)]), privateKey);
  const text = `untrusted comment: Beta test signature\n${packet.toString('base64')}\ntrusted comment: ${comment}\n${global.toString('base64')}\n`;
  fs.writeFileSync(installer + '.sig', Buffer.from(text).toString('base64'));
  const channels = path.join(directory, 'update-channels.json');
  fs.writeFileSync(channels, JSON.stringify({ beta: { pubkey } }));
  return { installer, channels };
}

function verify(installer, channels) {
  return spawnSync(process.execPath, [verifier, installer, channels], { encoding: 'utf8' });
}

test('Beta verification uses its independent channel public key', (t) => {
  const f = fixture(t);
  const result = verify(f.installer, f.channels);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout).signature_verified, true);
});

test('Beta verification rejects a different channel key and altered bytes', (t) => {
  const f = fixture(t);
  const other = fixture(t);
  assert.notEqual(verify(f.installer, other.channels).status, 0);
  fs.appendFileSync(f.installer, 'changed');
  assert.notEqual(verify(f.installer, f.channels).status, 0);
});

test('Beta verification cannot accept a stable installer name', (t) => {
  const f = fixture(t);
  const stable = path.join(path.dirname(f.installer), 'RVC-Fabric-Setup-1.8.1.exe');
  fs.copyFileSync(f.installer, stable);
  fs.copyFileSync(f.installer + '.sig', stable + '.sig');
  const result = verify(stable, f.channels);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Beta installer/);
});
