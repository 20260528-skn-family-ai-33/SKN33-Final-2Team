/* 규정 조항 표시 (5차 gp-ai.js AI.article·artName·missLabel·regSet) — 조항은 응답에 함께 오는 reg 묶음을 모아 둔 것 */
import type { Article } from '@/api/types/catalog';
import { useCatalog } from '@/shared/state/catalog';
import { me } from '@/shared/state/session';

export const article = (id: string): Article | undefined => useCatalog.getState().articles[id];
export const regOf = (key: string) => useCatalog.getState().regs[key] || null;
export const regSet = () => useCatalog.getState().regSets[me()?.empGroup || ''] || null;
export const regApplies = (): boolean => !!regSet();
export const regGroups = (): string[] => Object.keys(useCatalog.getState().regSets);

export const artName = (a: Article): string => {
  const n = regOf(a.reg)?.name || '';
  return a.title ? `「${n}」 ${a.no}(${a.title})` : `「${n}」 ${a.no}`;
};

export const missLabel = (m: string): string => (/[「」]/.test(m) || !/(규정|규칙|세칙|운영기준)$/.test(m) ? String(m) : `「${m}」`);
