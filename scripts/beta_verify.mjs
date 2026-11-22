import fs from 'node:fs';
import path from 'node:path';
import { verifySetupSignature } from './verify_setup_signature.mjs';

// Keep the stable signing verifier and stable public key unchanged.
const [installer, channelsPath] = process.argv.slice(2);
try {
  if (!/^RVC-Fabric-Setup-\d+\.\d+\.\d+-beta\.[1-9]\d*\.exe$/.test(path.basename(installer ?? ''))) {
    throw new Error('Use a versioned Beta installer');
  }
  const channels = JSON.parse(fs.readFileSync(channelsPath ?? new URL('../app/src-tauri/update-channels.json', import.meta.url), 'utf8'));
  const verified = verifySetupSignature(installer, channels.beta.pubkey);
  console.log(JSON.stringify(verified));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
