/* 서버에서 받아 모아 두는 참고 자료: 학습 자료(자료 키 → 정보) · 자격증 분야·목록 · 규정 묶음·조항.
   여러 응답(작업 공간·작성 문서·로드맵·자료 검색)에 함께 오는 res·reg 를 여기에 합친다(5차 D.res · AI.mergeReg 와 같은 역할) */
import { create } from 'zustand';
import { catalogApi } from '@/api/endpoints/catalog';
import type { Article, Cert, CertGroup, RegBundle, RegInfo, RegSets, Resource, ResourceMap } from '@/api/types/catalog';

interface CatalogState {
  res: Record<string, Resource>;
  certGroups: CertGroup[];
  certById: Record<string, Cert>;
  regSets: RegSets;
  articles: Record<string, Article>;
  regs: Record<string, RegInfo>;
}

export const useCatalog = create<CatalogState>(() => ({ res: {}, certGroups: [], certById: {}, regSets: {}, articles: {}, regs: {} }));

export function mergeRes(res: ResourceMap | null | undefined): void {
  if (!res || !Object.keys(res).length) return;
  useCatalog.setState((s) => {
    const next = { ...s.res };
    Object.entries(res).forEach(([id, incoming]) => {
      const previous = next[id];
      next[id] = previous?.detailsLoaded && !incoming.detailsLoaded
        ? { ...incoming, content: previous.content, curriculum: previous.curriculum, detailsLoaded: true }
        : incoming;
    });
    return { res: next };
  });
}

export function mergeReg(b: RegBundle | null | undefined): void {
  if (!b) return;
  const arts = b.articles || {};
  const regs = b.regs || {};
  if (!Object.keys(arts).length && !Object.keys(regs).length) return;
  useCatalog.setState((s) => ({ articles: { ...s.articles, ...arts }, regs: { ...s.regs, ...regs } }));
}

export async function loadCerts(): Promise<void> {
  try {
    const groups = await catalogApi.certifications();
    const byId: Record<string, Cert> = {};
    groups.forEach((g) =>
      g.certs.forEach((c) => {
        c.group = g.key;
        c.issuer = c.issuer || g.issuer;
        byId[c.id] = c;
      }),
    );
    useCatalog.setState({ certGroups: groups, certById: byId });
  } catch {
    useCatalog.setState({ certGroups: [], certById: {} });
  }
}

export async function loadRegSets(): Promise<void> {
  try {
    const sets = await catalogApi.regSets();
    const regs: Record<string, RegInfo> = {};
    Object.values(sets).forEach((s) => s.regs.forEach((r) => (regs[r.key] = r)));
    useCatalog.setState((st) => ({ regSets: sets, regs: { ...regs, ...st.regs } }));
  } catch {
    useCatalog.setState({ regSets: {} });
  }
}

export const resOf = (id: string | null | undefined): Resource | null => (id ? useCatalog.getState().res[id] || null : null);
export const useRes = (id: string | null | undefined): Resource | null => useCatalog((s) => (id ? s.res[id] || null : null));
