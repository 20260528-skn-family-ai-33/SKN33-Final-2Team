import type { Cert, ResourceMap } from '@/api/types/catalog';
import type { Activity, PlanContent } from '@/api/types/plan';
import type { ReviewMaterials } from '@/features/draft/review/ReviewSkillBlocks';

export function commentSkillNames(plan: PlanContent): string[] {
  const report = plan.def.learningReport as ReviewMaterials | undefined;
  const choices = report?.choices || {};
  const names = Object.keys(choices);
  if (names.length) {
    return [...new Set([...(report?.skillOrder || []), ...names])]
      .filter(name => Object.hasOwn(choices, name) && choices[name].enabled !== false);
  }
  return [...new Set([
    ...(plan.def.learningSkills || []).map(skill => skill.name),
    ...plan.acts.flatMap(activity => [activity.skill, ...(activity.skills || [])]),
  ].filter((name): name is string => !!name && !/[\r\n]/.test(name)))];
}

/** 스킬을 알 수 없는 활동을 모으는 묶음 이름 */
export const OTHER_LEARNING = '기타 학습';

export function groupLearningActivities(plan: PlanContent, resources: ResourceMap) {
  const report = plan.def.learningReport as { skillOrder?: string[] } | undefined;
  const preferred = [...new Set([...(report?.skillOrder || []), ...(plan.def.learningSkills || []).map(skill => skill.name)])];
  const groups = new Map<string, Activity[]>();
  for (const activity of plan.acts) {
    const tags = activity.skills || (activity.res ? resources[activity.res]?.skills : []) || [];
    const name = activity.skill || tags.find(tag => preferred.includes(tag)) || tags[0] || OTHER_LEARNING;
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

export function activitiesOutsideSkillCards(plan: PlanContent): Activity[] {
  const report = plan.def.learningReport as ReviewMaterials | undefined;
  const skills = report?.recommendations?.skills || [];
  const shown = new Set<string>();
  for (const name of report?.skillOrder || skills.map(skill => skill.name)) {
    const skill = skills.find(item => item.name === name);
    const choice = report?.choices[name];
    if (!skill || choice?.enabled === false) continue;
    const resources = [
      ...skill.courses.filter(item => item.id === choice?.course || choice?.courses?.includes(item.id)),
      ...skill.books.filter(item => choice?.books.includes(item.id)),
    ];
    for (const resource of resources) {
      const activity = plan.acts.find(item => item.skill === name && item.res === resource.id);
      if (activity) shown.add(activity.id);
    }
    const task = plan.acts.find(item => item.skill === name && !item.res);
    if (task) shown.add(task.id);
  }
  return plan.acts.filter(activity => !shown.has(activity.id));
}
