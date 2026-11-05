import type { BookDiagnostic, CourseDiagnostic } from '@/api/types/draft';

type Props = { hasOptions: boolean; fallback: string } & (
  { kind: '강좌'; diagnostic?: CourseDiagnostic } |
  { kind: '도서'; diagnostic?: BookDiagnostic }
);

const candidateToken = /(?<![A-Za-z0-9_])(?:S[0-9]+-C[0-9]+|B[0-9]+)(?![A-Za-z0-9_])/g;

export function MaterialReason({ kind, diagnostic, hasOptions, fallback }: Props) {
  const candidates = hasOptions ? `일부 ${kind} 후보` : `${kind} 후보`;
  let summary: string | undefined;
  switch (diagnostic?.reason) {
    case 'no_candidates':
      if (!hasOptions) summary = `추천에 사용할 ${kind} 후보가 없어요.`;
      break;
    case 'insufficient_evidence':
      summary = `${candidates}의 학습 내용을 확인할 근거가 부족해요.`;
      break;
    case 'stack_mismatch':
      summary = `${candidates}가 다루는 기술이 프로젝트에서 쓰는 기술과 달라요.`;
      break;
    case 'scope_gap':
      summary = `${candidates}가 필요한 학습 범위를 충분히 다루지 않아요.`;
      break;
    case 'longer_for_coverage':
      if (hasOptions) summary = '필요한 학습 범위를 채우기 위해 더 긴 강좌를 추천했어요.';
      break;
  }
  const displayDetail = typeof diagnostic?.displayDetail === 'string' ? diagnostic.displayDetail.trim() : '';
  const detail = displayDetail || (typeof diagnostic?.detail === 'string'
    ? diagnostic.detail.trim().replace(candidateToken, '비교 후보') : '');
  if (summary && detail) return <p className="material-reason small muted"><strong>{summary}</strong> {detail}</p>;
  return hasOptions ? null : <p className="small muted">{fallback}</p>;
}
