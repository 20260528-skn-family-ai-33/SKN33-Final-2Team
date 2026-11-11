import { describe, expect, it } from 'vitest';
import type { Cert, ResourceMap } from '@/api/types/catalog';
import type { Activity, PlanContent } from '@/api/types/plan';
import { activitiesOutsideSkillCards, groupLearningActivities, matchingCertificates } from './roadmapLearningData';

describe('skill activity groups', () => {
  it('keeps selected skill order, original activities and week/completion identifiers', () => {
    const activities = [{ id: 'task', skill: 'SQL', res: null, wFrom: 3, wTo: 3 },
      { id: 'course', skill: 'Python', res: 'c', wFrom: 1, wTo: 2 },
      { id: 'book', skill: 'SQL', res: 'b', wFrom: 3, wTo: 3 }] as Activity[];
    const plan = { def: { learningReport: { skillOrder: ['Python', 'SQL'] } }, acts: activities } as unknown as PlanContent;
    const groups = groupLearningActivities(plan, {});
    expect(groups.map(group => group.name)).toEqual(['Python', 'SQL']);
    expect(groups[1].materials.map(a => a.id)).toEqual(['book']);
    expect(groups[1].tasks[0]).toBe(activities[0]);
    expect(groups[1].tasks[0].wFrom).toBe(3);
    expect(activities.map(a => a.id)).toEqual(['task', 'course', 'book']);
  });
  it('uses an existing skill tag for legacy records and preserves unclassified tasks', () => {
    const plan = { def: { learningSkills: [{ name: 'Python' }] }, acts: [
      { id: 'legacy', res: 'c' }, { id: 'untagged', res: null },
    ] } as unknown as PlanContent;
    const resources = { c: { skills: ['SQL', 'Python'] } } as unknown as ResourceMap;
    expect(groupLearningActivities(plan, resources).map(group => group.name)).toEqual(['Python', '기타 학습']);
  });
});

const cert = (id: string, skills: string[], name = id) => ({ id, res: `cert_${id}`, name, short: id, skills } as Cert);
describe('matching certificate recommendations', () => {
  it('requires exact selected skill linkage, excludes owned certificates and deduplicates', () => {
    const certificates = [cert('SQLD', ['SQL'], 'SQL 개발자'), cert('other', ['SQL 기초']),
      cert('eligible', ['SQL']), cert('eligible', ['SQL']), cert('unknown', [])];
    expect(matchingCertificates(certificates, ['SQL'], ['SQLD (2020 취득)']).map(c => c.id)).toEqual(['eligible']);
  });
  it('prioritizes coverage and limits to five without inventing missing entries', () => {
    const certificates = Array.from({ length: 8 }, (_, i) => cert(`c${i}`, ['SQL']));
    certificates.push(cert('shared', ['SQL', 'Python']));
    const result = matchingCertificates(certificates, ['SQL', 'Python']);
    expect(result).toHaveLength(5);
    expect(result[0].id).toBe('shared');
    expect(matchingCertificates([], ['SQL'])).toEqual([]);
  });
});


it.each([0, 1, 3])('excludes all %i tasks rendered by the selected skill card', count => {
  const visibleTasks = Array.from({ length: count }, (_, i) => ({ id: `sql-${i}`, skill: 'SQL' }));
  const otherTasks = [{ id: 'other', skill: 'Python' }, { id: 'untagged' }];
  const plan = {
    acts: [...visibleTasks, ...otherTasks],
    def: { learningReport: {
      recommendations: { skills: [{ name: 'SQL', courses: [], books: [] }, { name: 'Python', courses: [], books: [] }] },
      choices: { SQL: { books: [] }, Python: { enabled: false, books: [] } },
      skillOrder: ['SQL', 'Python'],
    } },
  } as unknown as PlanContent;
  expect(activitiesOutsideSkillCards(plan)).toEqual(otherTasks);
});
