/* 세부 사항 문구 (5차 gp-ai.js AI.prefText 등 · 자격증은 서버 자격 목록) */
import type { Prefs } from '@/api/types/draft';
import { D } from '@/shared/constants/data';
import { useCatalog } from '@/shared/state/catalog';
import { blank, won } from './format';

export const certOf = (p: Partial<Prefs> | null | undefined) => (p && p.cert ? useCatalog.getState().certById[p.cert] || null : null);
export const certNameOf = (p: Partial<Prefs> | null | undefined): string => certOf(p)?.name || '';

export const prefAuto = (k: keyof Prefs, p: Prefs): boolean =>
  k === 'budget' ? blank(p.budget) : k === 'etc' ? !String(p.etc || '').trim() : k === 'hours' || k === 'weeks' ? !(+p[k] > 0) : k === 'cert' ? !certOf(p) : !p[k];

export function prefText(k: keyof Prefs, p: Prefs): string {
  const v = p[k];
  if (k === 'format') return D.formatOpts.find((o) => o[0] === v)?.[1] || '알아서';
  if (k === 'cert') {
    const c = certOf(p);
    return c ? `${c.name} · 4단계에 준비 활동을 넣어요` : '계획 없음';
  }
  if (k === 'hours') return +v > 0 ? `주 ${v}시간` : '알아서 (로드맵 계획 에이전트가 정해요)';
  if (k === 'weeks') return +v > 0 ? `${v}주 안에` : '알아서 (정해진 기간 없음)';
  if (k === 'budget') return blank(v) ? '알아서' : +v > 0 ? won(+v) : '0원 (무료 자료만)';
  if (k === 'etc') return String(v || '').trim() || '없음';
  return '';
}

export const fieldLabel = (k: string): string => D.detailFields.find((f) => f[0] === k)?.[1] || '';

export const ansLabel = (o: string | number | null | undefined): string => {
  const x = D.answerOpts.find((y) => y[0] === String(o));
  return x ? `${x[0]} ${x[1]}` : '미응답';
};

export const rose = (pre: string | number, post: string | number): boolean => +post > +pre;
