import type { Resource } from '@/api/types/catalog';

const platformNames: Record<string,string> = { Inflearn:'인프런', 'MS Learn':'Microsoft Learn' };
export const platformLabel = (platform: string) => platformNames[platform] ?? platform;

/** Platform first; institution/teacher is a separate source detail. */
export function resourceSource(r: Resource | null | undefined): string {
  if (!r) return '';
  if (r.type !== 'course' && r.kind !== '강좌') return r.provider || '';
  const platform = platformLabel(r.platform || '');
  const provider = r.provider || '';
  return platform && provider && !provider.toLocaleLowerCase().includes(platform.toLocaleLowerCase()) ? `${platform} · ${provider}` : provider || platform || r.source || '출처 미확인';
}
