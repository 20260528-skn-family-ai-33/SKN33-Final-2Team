import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { readVersion } from './version.mjs';

test('VERSION 변경값을 읽고 끝 공백을 제거한다', (t) => {
  const dir = mkdtempSync(join(tmpdir(), 'growpath-version-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const path = join(dir, 'VERSION');
  writeFileSync(path, '0.2.0\r\n');
  assert.equal(readVersion(path), '0.2.0');
  writeFileSync(path, '0.2.1\n');
  assert.equal(readVersion(path), '0.2.1');
});

test('누락·잘못된 VERSION은 기본값 없이 실패한다', (t) => {
  const dir = mkdtempSync(join(tmpdir(), 'growpath-version-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const path = join(dir, 'VERSION');
  assert.throws(() => readVersion(path), /VERSION 파일을 읽을 수 없습니다/);
  for (const value of ['', 'v0.2.0', '0.2', '00.2.0', '0.02.0', '0.2.00', '0.2.0-beta.1', '0.2.0\n0.3.0']) {
    writeFileSync(path, value);
    assert.throws(() => readVersion(path), /X.Y.Z 형식/);
  }
});

test('UTF-8 BOM과 Windows 줄바꿈을 허용하고 버전 형식 검사는 유지한다', (t) => {
  const dir = mkdtempSync(join(tmpdir(), 'growpath-version-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const path = join(dir, 'VERSION');
  writeFileSync(path, '\uFEFF0.2.0\r\n');
  assert.equal(readVersion(path), '0.2.0');
  writeFileSync(path, '\uFEFFv0.2.0\r\n');
  assert.throws(() => readVersion(path), /X.Y.Z 형식/);
});
