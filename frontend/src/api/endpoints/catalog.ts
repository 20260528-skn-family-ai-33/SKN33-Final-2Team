/* 학습 자료·자격증·규정·스킬 지도 (API-22, 53, 54 · 스킬 지도는 설계서 밖 추가 10/23) */
import { enc, http } from '../client';
import type { CertGroup, RegBundle, RegSets, Resource, ResourceMap, ResourceSearch, SkillMapData } from '../types/catalog';

export interface ResourceQuery {
  kind?: string;
  q?: string;
  stage?: number | string;
  exclude?: string;
  limit?: number;
  offset?: number;
  certs?: number;
}

export const catalogApi = {
  certifications: () => http.get<CertGroup[]>('/certifications'),
  resources: (q: ResourceQuery) =>
    http.get<ResourceSearch>('/resources?' + new URLSearchParams(Object.entries(q).map(([k, v]) => [k, String(v ?? '')])).toString()),
  resource: (id: string) => http.get<Resource>(`/resources/${enc(id)}`),
  lookup: (ids: string[]) => http.post<ResourceMap>('/resources/lookup', { ids }),
  regSets: () => http.get<RegSets>('/regulations/sets'),
  regLookup: (ids: string[]) => http.post<RegBundle>('/regulations/lookup', { ids }),
  skillMap: () => http.get<SkillMapData>('/skills/map'),
};
