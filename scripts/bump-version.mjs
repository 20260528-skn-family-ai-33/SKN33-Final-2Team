import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseVersion, readVersion } from '../frontend/scripts/version.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const path = new URL('../VERSION', import.meta.url);
const ref = 'origin/main:VERSION';
const base = parseVersion(execFileSync('git', ['show', ref], { cwd: root, encoding: 'utf8' }).trim(), ref);
const current = readVersion(path);
const [major, minor, patch] = base.split('.').map(BigInt);
const next = [major, minor, patch + 1n];
const currentParts = current.split('.').map(BigInt);
const firstDifference = next.findIndex((part, i) => currentParts[i] !== part);

if (firstDifference >= 0 && currentParts[firstDifference] < next[firstDifference]) {
  writeFileSync(path, next.join('.') + '\n');
  console.log(`VERSION ${current} → ${next.join('.')}`);
} else {
  console.log(`VERSION ${current} 유지 (main ${base})`);
}
