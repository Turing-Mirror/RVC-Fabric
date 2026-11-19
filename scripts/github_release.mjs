import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { verifySetupSignature } from './verify_setup_signature.mjs';

const [version, directory] = process.argv.slice(2);
const config = JSON.parse(readFileSync(new URL('../app/src-tauri/tauri.conf.json', import.meta.url)));
if (version !== config.version || !/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error('Use the release version in tauri.conf.json.');
}

const name = 'RVC-Fabric-Setup-' + version + '.exe';
const installer = join(directory, name);
const verified = verifySetupSignature(installer, config.plugins.updater.pubkey);
const checksum = readFileSync(installer + '.sha256', 'utf8').trim();
if (checksum !== verified.sha256 + '  ' + name) throw new Error('Setup checksum mismatch.');
const notes = readFileSync(new URL('../docs/releases/' + version + '.md', import.meta.url), 'utf8').trim();
if (!notes) throw new Error('Add release notes before preparing the release.');

const url = 'https://github.com/Turing-Mirror/RVC-Fabric/releases/download/v' + version + '/' + name;
const updater = {
  version,
  notes,
  pub_date: verified.pub_date,
  platforms: { 'windows-x86_64': { url, signature: verified.signature } },
};
writeFileSync(join(directory, 'updater.json'), JSON.stringify(updater, null, 2) + '\n');
console.log('Verified ' + name + ' (' + verified.size_bytes + ' bytes).');
