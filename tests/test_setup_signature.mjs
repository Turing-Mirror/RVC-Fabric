import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { verifySetupSignature } from '../scripts/verify_setup_signature.mjs';

function fixture(t, algorithm = 'ED') {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'rvc-release-signature-'));
  t.after(() => fs.rmSync(directory, { recursive: true }));
  const file = path.join(directory, 'setup.exe');
  const bytes = Buffer.from('installer fixture');
  fs.writeFileSync(file, bytes);
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
  const rawPublicKey = publicKey.export({ format: 'der', type: 'spki' }).subarray(-32);
  const id = crypto.randomBytes(8);
  const publicPacket = Buffer.concat([Buffer.from('Ed'), id, rawPublicKey]);
  const publicText = `untrusted comment: test public key\n${publicPacket.toString('base64')}\n`;
  const payload = algorithm === 'ED' ? crypto.createHash('blake2b512').update(bytes).digest() : bytes;
  const signature = crypto.sign(null, payload, privateKey);
  const packet = Buffer.concat([Buffer.from(algorithm), id, signature]);
  const comment = 'timestamp:1794441600\tfile:setup.exe';
  const globalSignature = crypto.sign(null, Buffer.concat([signature, Buffer.from(comment)]), privateKey);
  const signatureText = `untrusted comment: test signature\n${packet.toString('base64')}\ntrusted comment: ${comment}\n${globalSignature.toString('base64')}\n`;
  fs.writeFileSync(`${file}.sig`, Buffer.from(signatureText).toString('base64'));
  return { file, publicKey: Buffer.from(publicText).toString('base64'), signatureText };
}

for (const algorithm of ['ED', 'Ed']) {
  test(`accepts valid ${algorithm} signature and authenticated timestamp`, (t) => {
    const f = fixture(t, algorithm);
    const result = verifySetupSignature(f.file, f.publicKey);
    assert.equal(result.signature_verified, true);
    assert.equal(Date.parse(result.pub_date), 1794441600000);
    assert.equal(result.sha256, crypto.createHash('sha256').update('installer fixture').digest('hex'));
  });
}

test('rejects altered installer bytes', (t) => {
  const f = fixture(t);
  fs.appendFileSync(f.file, 'tampered');
  assert.throws(() => verifySetupSignature(f.file, f.publicKey), /verification failed/);
});

test('rejects wrong product key', (t) => {
  const first = fixture(t);
  const second = fixture(t);
  assert.throws(() => verifySetupSignature(first.file, second.publicKey), /key does not match/);
});

test('rejects modified trusted signing timestamp', (t) => {
  const f = fixture(t);
  fs.writeFileSync(`${f.file}.sig`, Buffer.from(f.signatureText.replace('timestamp:1794441600', 'timestamp:1794441601')).toString('base64'));
  assert.throws(() => verifySetupSignature(f.file, f.publicKey), /verification failed/);
});
