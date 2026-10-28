import type { Resource } from '@/api/types/catalog';

/** Platform first; institution/teacher is a separate source detail. */
export function resourceSource(r: Resource | null | undefined): string {
  if (!r) return '';
  if (r.type !== 'course' && r.kind !== '강좌') return r.provider || '';
  const names: Record<string,string> = { Inflearn:'인프런', 'MS Learn':'Microsoft Learn', 'K-MOOC':'K-MOOC', KOCW:'KOCW', STEP:'STEP', 생활코딩:'생활코딩' };
  const platform = r.platform ? names[r.platform] || r.platform : '';
  const provider = r.provider || '';
  return platform && provider && !provider.toLocaleLowerCase().includes(platform.toLocaleLowerCase()) ? `${platform} · ${provider}` : provider || platform || r.source || '출처 미확인';
}
