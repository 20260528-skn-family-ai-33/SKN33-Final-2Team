/* AI 생성을 기다리는 동안 보이는 '걸리는 시간' 안내 — 튜토리얼과 화면이 같은 문구를 쓴다.
   보통 시간(1~2분쯤 · 30초에서 1분쯤)은 OpenAI API 기준이다. RunPod-Ollama(로컬 sLLM)는 훨씬 오래 걸려
   모델 호출 제한(.env.example OLLAMA_TIMEOUT=600초)에 맞춰 최대 10분으로 안내한다(#302).
   화면 코드를 가져오지 않는 순수 자료라 튜토리얼 단계 정의에서도 쓴다 */

/** RunPod-Ollama 의 걸리는 시간 문구(마침표 없음) */
export const SLOW_WAIT = '최대 10분까지 걸릴 수 있어요';

/** 걸리는 시간 문구. slow 는 AI 모드가 RunPod-Ollama 일 때 — usual 대신 SLOW_WAIT 를 쓴다 */
export const waitTime = (usual: string, slow: boolean): string => (slow ? SLOW_WAIT : usual);
