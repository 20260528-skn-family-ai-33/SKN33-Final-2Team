/* 마지막으로 로그인에 성공한 사번(또는 관리자 아이디)을 이 브라우저에 기억해 다음 로그인 화면에 채운다.
   비밀번호는 저장하지 않는다. 저장소를 못 쓰는 브라우저(사생활 보호 모드 등)에서는 기억만 건너뛴다 */
const KEY = 'growpath.login.last-id';
/* 로그인 화면 아이디 칸의 maxLength 와 같다 */
const MAX_LENGTH = 40;

export function loadLastLoginId(): string {
  try {
    const v = localStorage.getItem(KEY)?.trim() ?? '';
    return v.length <= MAX_LENGTH ? v : '';
  } catch {
    return '';
  }
}

export function saveLastLoginId(code: string): void {
  try {
    localStorage.setItem(KEY, code);
  } catch {
    /* 위 설명대로 기억만 건너뜀 */
  }
}
