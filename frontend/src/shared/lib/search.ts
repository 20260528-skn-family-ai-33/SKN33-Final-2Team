/* 입력하는 대로 찾기 (#102): 학습 자료 목록·자료 고르기가 같은 기준으로 검색어를 확정한다.
   기다림 없이 글자마다 찾되, 검색어가 실제로 달라질 때만 요청한다 */

/* 한글 호환 낱자(ㄱ~ㅎ, ㅏ~ㅣ). 조합 중인 마지막 음절은 '도ㅋ'처럼 낱자로 남는다 */
const TRAILING_JAMO = /[ㄱ-ㆎ]+$/u;

/** 서버에 보낼 검색어: 앞뒤 공백을 빼고, 한글 조합 중 끝에 남은 낱자는 뺀다.
 *  조합이 끝나지 않은 음절로 찾으면 대부분 결과가 없고 요청만 늘기 때문이다 */
export function searchTerm(text: string): string {
  return text.trim().replace(TRAILING_JAMO, '').trimEnd();
}
