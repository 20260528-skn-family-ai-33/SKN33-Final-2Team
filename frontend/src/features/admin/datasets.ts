/* 관리자 화면 고정 값 (5차 gp-admin.js 의 DS·ACT·UP_ST) */
import type { DatasetId, RowAction, UploadStatus } from '@/api/types/admin';

export const DS: Record<DatasetId, { title: string; icon: string; lead: string; sheets: string[] }> = {
  hr: { title: '인적 데이터', icon: 'users', lead: '부서·직원·근무성적평정. 인사이동은 직원의 ‘부서 코드’를, 부서장 권한은 ‘부서장’을 고쳐요. 직원은 지우지 않고 퇴직 처리해요.', sheets: ['직원', '부서', '평정'] },
  education:{ title: '교육 데이터', icon: 'book', lead: '로드맵 추천에 쓰는 강좌·도서·자격증. 학습 형식·시간·단계·비용은 팀 DB에 없어 규칙으로 채운 ‘추정’ 값이 있고, 고치면 추정 표시가 빠져요.', sheets: ['강좌', '도서', '자격증'] },
};
export const isDataset = (x: string | undefined): x is DatasetId => !!x && x in DS;

/** 규정 데이터: 표로 고치지 않고 원문 PDF 만 올리고 내려받는다(2026-10-26 · 벡터 DB 갱신은 시스템 관리자가 함) */
export const REG = {
  title: '규정 데이터',
  icon: 'scale',
  lead: '사내 생활 도우미와 지원 조건 확인이 근거로 쓰는 규정이에요. 규정은 이 화면에서 고치지 않아요. 새 규정이나 개정된 규정은 원문 PDF로 올리면 서비스 운영팀이 받아 도우미 검색에 반영해요.',
} as const;
/** 변경 이력의 데이터 이름(예전 규정 엑셀 기록 포함) */
export const datasetTitle = (ds: string): string => (isDataset(ds) ? DS[ds].title : ds === 'regulations' ? REG.title : ds);

export const ACT: Record<RowAction, [string, string]> = { add: ['추가', 'acc'], update: ['변경', 'line'], delete: ['삭제', 'warn'], error: ['오류', 'fail'], skip: ['건너뜀', 'line'], same: ['그대로', 'line'] };
export const UP_ST: Record<UploadStatus, [string, string]> = { previewed: ['미리보기', 'line'], applied: ['반영함', 'ok'], rejected: ['취소함', 'line'], expired: ['시간 지남', 'line'] };
/** 한 쪽에 보이는 행 수 */
export const PAGE = 50;
/** 여러 줄로 적는 칸(줄 수) */
export const LONG: Record<string, number> = { text: 8, summary: 4, description: 4, task: 3, subjects: 2 };
export const DEL_ASK: Record<string, string> = { '퇴직 처리': '퇴직 처리할까요?', 삭제: '삭제할까요?' };
export const EDU_KIND = { course: '강좌', book: '도서', cert: '자격증' } as const;
