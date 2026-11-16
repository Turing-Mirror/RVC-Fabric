import fs from 'node:fs';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

// Tauri updater signatures are base64-encoded minisign packets.
export function verifySetupSignature(file, encodedPublicKey) {
  const publicLines = Buffer.from(encodedPublicKey, 'base64').toString('utf8').trim().split(/\r?\n/);
  const publicPacket = Buffer.from(publicLines[1] ?? '', 'base64');
  const signature = fs.readFileSync(`${file}.sig`, 'utf8').trim();
  const lines = Buffer.from(signature, 'base64').toString('utf8').trim().split(/\r?\n/);
  const packet = Buffer.from(lines[1] ?? '', 'base64');
  if (publicPacket.length !== 42 || packet.length !== 74 ||
      !packet.subarray(2, 10).equals(publicPacket.subarray(2, 10))) {
    throw new Error('Updater signature key does not match this product');
  }
  const algorithm = packet.subarray(0, 2).toString('ascii');
  if (!['ED', 'Ed'].includes(algorithm) || !lines[2]?.startsWith('trusted comment: ')) {
    throw new Error('Invalid updater signature format');
  }
  const publicKey = crypto.createPublicKey({
    key: Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), publicPacket.subarray(10)]),
    format: 'der', type: 'spki',
  });
  const bytes = fs.readFileSync(file);
  const payload = algorithm === 'ED' ? crypto.createHash('blake2b512').update(bytes).digest() : bytes;
  const trustedComment = lines[2].slice('trusted comment: '.length);
  if (!crypto.verify(null, payload, publicKey, packet.subarray(10)) ||
      !crypto.verify(null, Buffer.concat([packet.subarray(10), Buffer.from(trustedComment, 'utf8')]),
        publicKey, Buffer.from(lines[3] ?? '', 'base64'))) {
    throw new Error('Installer or trusted comment signature verification failed');
  }
  const timestamp = /(?:^|\s)timestamp:(\d+)(?:\s|$)/.exec(trustedComment);
  if (!timestamp) throw new Error('Signature timestamp missing');
  return {
    size_bytes: bytes.length,
    sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
    signature,
    pub_date: new Date(Number(timestamp[1]) * 1000).toISOString().replace('.000Z', 'Z'),
    signature_verified: true,
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const config = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    console.log(JSON.stringify(verifySetupSignature(process.argv[2], config.plugins.updater.pubkey)));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
