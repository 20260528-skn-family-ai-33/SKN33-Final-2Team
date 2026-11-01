import type { Cert, ResourceMap } from '@/api/types/catalog';
import type { Activity, PlanContent } from '@/api/types/plan';

export function groupLearningActivities(plan: PlanContent, resources: ResourceMap) {
  const report = plan.def.learningReport as { skillOrder?: string[] } | undefined;
  const preferred = [...new Set([...(report?.skillOrder || []), ...(plan.def.learningSkills || []).map(skill => skill.name)])];
  const groups = new Map<string, Activity[]>();
  for (const activity of plan.acts) {
    const tags = activity.skills || (activity.res ? resources[activity.res]?.skills : []) || [];
    const name = activity.skill || tags.find(tag => preferred.includes(tag)) || tags[0] || '기타 학습';
    groups.set(name, [...(groups.get(name) || []), activity]);
  }
  const names = [...preferred.filter(name => groups.has(name)), ...[...groups.keys()].filter(name => !preferred.includes(name))];
  return names.map(name => {
    const activities = groups.get(name)!;
    return { name, activities, materials: activities.filter(activity => !!activity.res), tasks: activities.filter(activity => !activity.res) };
  });
}

const normal = (value: string) => value.replace(/\([^)]*\)/g, '').toLocaleLowerCase().replace(/[^a-z0-9가-힣]/g, '');
export function matchingCertificates(certs: Cert[], skills: string[], owned: string[] = []) {
  const known = new Set(owned.map(normal));
  const seen = new Set<string>();
  return certs.filter(cert => {
    if (seen.has(cert.res) || !cert.skills?.some(skill => skills.includes(skill))) return false;
    if ([cert.name, cert.short, cert.id].some(value => known.has(normal(value)))) return false;
    seen.add(cert.res);
    return true;
  }).sort((a, b) => {
    const overlap = (cert: Cert) => cert.skills?.filter(skill => skills.includes(skill)).length || 0;
    return overlap(b) - overlap(a) || a.name.localeCompare(b.name, 'ko');
  }).slice(0, 5);
}

export const activityAnchor = (id: string) => `learning-activity-${id}`;
