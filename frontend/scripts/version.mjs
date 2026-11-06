import { readFileSync } from 'node:fs';

export function readVersion(path = new URL('../../VERSION', import.meta.url)) {
  let version;
  try {
    version = readFileSync(path, 'utf8').trim();
  } catch (error) {
    throw new Error(`프로젝트 VERSION 파일을 읽을 수 없습니다: ${path}`, { cause: error });
  }
  if (!/^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/.test(version)) {
    throw new Error(`프로젝트 VERSION은 앞자리 0이 없는 X.Y.Z 형식이어야 합니다: ${path}`);
  }
  return version;
}
