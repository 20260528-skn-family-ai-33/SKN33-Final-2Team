/* 로드맵 계산: 주당 시간으로 주차를 나누는 규칙(서버도 같은 규칙으로 저장한다)과 비용 합계 */
import { beforeAll, describe, expect, it } from 'vitest';
import type { OptionDef } from '@/api/types/draft';
import { mergeRes } from '@/shared/state/catalog';
import { buildPlan, count, nextAct, range } from './plan';

const def: OptionDef = {
  id: 'A1',
  name: '기초부터',
  short: '기초',
  tagline: '',
  pros: [],
  cons: [],
  acts: [
    { id: 'a1', stage: 1, title: '입문 강좌', res: 'r-course' },
    { id: 'a2', stage: 2, title: '실습 과제', res: null, hours: 3, skills: ['RAG'] },
    { id: 'a3', stage: 3, title: '도서 읽기', res: 'r-book' },
  ],
};

beforeAll(() => {
  mergeRes({
    'r-course': { id: 'r-course', title: '입문', provider: 'K-MOOC', kind: '강좌', hours: 6, cost: 0 },
    // 시간·비용을 모르는 자료: 시간은 2시간으로 보고 비용은 '확인 필요'
    'r-book': { id: 'r-book', title: '책', provider: '출판사', kind: '도서', hours: null, cost: null },
  });
});

describe('buildPlan', () => {
  it('누적 시간을 주당 시간으로 나눠 활동마다 시작·끝 주차를 정한다', () => {
    const pl = buildPlan(def, { hours: 4 }, '목표');
    expect(pl.acts.map((a) => [a.id, a.hours, a.wFrom, a.wTo])).toEqual([
      ['a1', 6, 1, 2],
      ['a2', 3, 2, 3],
      ['a3', 2, 3, 3],
    ]);
    expect(pl.totalH).toBe(11);
    expect(pl.weeks).toBe(3);
  });

  it('시작 단계보다 앞 단계 활동은 빼고 계산한다', () => {
    const pl = buildPlan(def, { hours: 4, start: 2 }, '목표');
    expect(pl.acts.map((a) => a.id)).toEqual(['a2', 'a3']);
    expect(pl.acts[0].wFrom).toBe(1);
  });

  it('비용은 아는 값만 더하고, 모르는 자료가 있으면 확인 필요로 표시한다', () => {
    const pl = buildPlan(def, { hours: 4 }, '목표');
    expect(pl.cost).toBe(0);
    expect(pl.costUnknown).toBe(true);
  });

  it('과제는 자료가 없으므로 과제 표시와 에이전트가 고른 스킬을 남긴다', () => {
    const a2 = buildPlan(def, {}, '').acts.find((a) => a.id === 'a2')!;
    expect(a2.task).toBe(true);
    expect(a2.skills).toEqual(['RAG']);
  });

  it('활동별 고친 값(patch)은 주차 계산 전에 반영된다', () => {
    const pl = buildPlan(def, { hours: 4, patch: { a1: { hours: 1 } } }, '');
    expect(pl.acts[0].wTo).toBe(1);
    expect(pl.totalH).toBe(6);
  });
});

describe('진행 계산', () => {
  it('완료한 활동 수와 다음 활동을 센다', () => {
    const pl = buildPlan(def, { hours: 4 }, '');
    const progress = { a1: { status: 'done' } } as never;
    expect(count(pl, progress)).toMatchObject({ t: 2, done: 1 });
    expect(nextAct(pl, progress)?.id).toBe('a2');
  });

  it('도서는 완료 기록이 있어도 진척률에 넣지 않고 다음 활동으로도 고르지 않는다', () => {
    const pl = buildPlan(def, { hours: 4 }, '');
    expect(count(pl, { a3: { status: 'done' } } as never)).toMatchObject({ t: 2, done: 0 });
    const others = { a1: { status: 'done' }, a2: { status: 'done' } } as never;
    expect(count(pl, others)).toMatchObject({ t: 2, done: 2 });
    expect(nextAct(pl, others)).toBeUndefined();
  });

  it('주차 범위를 처음~끝으로 쓴다(한 주면 그 주만)', () => {
    const pl = buildPlan(def, { hours: 4 }, '');
    expect(range(pl.acts)).toBe('1~3주차');
    expect(range(pl.acts.slice(2))).toBe('3주차');
  });
});


describe('자료 기준 기간', () => {
  it('스킬별 자료 5주·8주는 과제 시간이 커져도 합계 13주를 유지한다', () => {
    const option: OptionDef = { ...def, materialSchedule: [{ skill: 'S', weeks: 5 }, { skill: 'T', weeks: 8 }], acts: [
      { id: 'task-s', skill: 'S', stage: 3, title: '과제 S', hours: 100 },
      { id: 'task-t', skill: 'T', stage: 3, title: '과제 T', hours: 100 },
    ] };
    const plan = buildPlan(option, { hours: 4 }, '목표');
    expect(plan.weeks).toBe(13);
    expect(plan.acts.map(act => [act.skill, act.wFrom, act.wTo])).toEqual([['S', 1, 5], ['T', 6, 13]]);
  });
});

function sharedOption(): OptionDef {
  const rows = [['RAG', 'shared', 6.9], ['ETL', 'etl', 8.7], ['Web', 'shared', 6.9], ['MLOps', 'mlops', 8.7]] as const;
  return {...def, materialSchedule: [], acts: rows.map(([skill, res], i) => ({id: `material-${i}`, skill, res, stage: 2, title: res})),
    learningReport: {
      recommendations: {id: 'rec', skills: rows.map(([name, id, hours]) => ({name, courses: [{id, title: id, hours}], books: [{id: 'book', title: 'book', hours: 12}]}))},
      choices: Object.fromEntries(rows.map(([name, course]) => [name, {course, books: []}])),
      skillOrder: rows.map(([name]) => name),
    }};
}

describe('공유 강좌의 실제 일정과 전체 기간', () => {
  it('재현 사례는 공유 강좌 +1주 및 스킬별 순차 배정으로 계산하고 별도 ID를 유지한다', () => {
    const input = sharedOption(), before = structuredClone(input);
    const plan = buildPlan(input, {hours: 6}, 'Goal');
    expect(plan.weeks).toBe(7);
    expect(plan.totalH).toBe(24.3);
    expect(plan.acts.filter(a => a.res === 'shared').map(a => [a.id, a.wFrom, a.wTo])).toEqual([['material-0', 1, 3], ['material-2', 1, 3]]);
    expect(plan.def.learningReport?.durationEstimates?.Web.addedWeeks).toBe(0);
    expect(input).toEqual(before);
  });
  it('과제 시간은 합계 시간에만 남고 자료 주차를 늘리지 않는다', () => {
    const input = sharedOption();
    input.acts.push({id: 'task', skill: 'Web', stage: 3, title: 'Task', hours: 100});
    const plan = buildPlan(input, {hours: 6}, 'Goal');
    expect(plan.weeks).toBe(7); expect(plan.totalH).toBe(124.3);
    expect(plan.durationBasis).toBe('materials-only');
    expect(plan.acts.at(-1)).toMatchObject({id: 'task', wFrom: 1, wTo: 3});
  });
  it('주당시간·순서·제외를 바꾸면 전역 일정을 다시 계산한다', () => {
    const input = sharedOption();
    expect(buildPlan(input, {hours: 12}, '').weeks).toBe(4);
    input.learningReport!.skillOrder = ['ETL', 'Web', 'MLOps', 'RAG'];
    const reordered = buildPlan(input, {hours: 6}, '');
    expect(reordered.def.learningReport!.durationEstimates!.RAG.addedWeeks).toBe(0);
    expect(reordered.acts.find(a => a.skill === 'RAG')?.wFrom).toBe(3);
    input.learningReport!.choices.Web.enabled = false;
    const excluded = buildPlan(input, {hours: 6}, '');
    expect(excluded.acts.some(a => a.skill === 'Web')).toBe(false);
    expect(excluded.def.learningReport!.durationEstimates!.RAG.addedWeeks).toBe(2);
  });
  it('도서는 1주 작업량을 추가하고 공유 강좌만 있는 후속 스킬은 미래 슬롯을 만들지 않는다', () => {
    const input = sharedOption();
    input.learningReport!.choices.RAG.books = ['book'];
    input.acts.push({id: 'book-act', skill: 'RAG', stage: 2, title: 'Book', res: 'book', hours: 12});
    const plan = buildPlan(input, {hours: 6}, '');
    expect(plan.weeks).toBe(8); expect(plan.totalH).toBe(30.3);
    expect(plan.acts.find(a => a.skill === 'Web')).toMatchObject({wFrom: 1, wTo: 3});
    expect(plan.acts.every(a => a.wFrom >= 1 && a.wFrom <= a.wTo && a.wTo <= plan.weeks)).toBe(true);
  });
  it('짧은 독립 강좌도 각 스킬별로 순차 주차를 배정한다', () => {
    const input = sharedOption();
    input.learningReport!.recommendations.skills.forEach((row, i) => {row.courses[0] = {id: String(i), title: 'short', hours: 0.1}; input.learningReport!.choices[row.name].course = String(i); input.acts[i].res = String(i);});
    expect(buildPlan(input, {hours: 0.4}, '').weeks).toBe(4);
  });
  it('비인접 스킬의 같은 도서도 각 스킬 순서에 맞춰 별도 주차로 배정하고 활동 ID는 유지한다', () => {
    const input = sharedOption();
    for (const name of ['RAG', 'Web']) {
      input.learningReport!.choices[name].books = ['book'];
      input.acts.push({id: `book-${name}`, skill: name, stage: 2, title: 'Book', res: 'book', hours: 12});
    }
    const before = structuredClone(input), plan = buildPlan(input, {hours: 6}, '');
    expect(input).toEqual(before);
    expect(plan.weeks).toBe(9); expect(plan.totalH).toBe(30.3);
    expect(plan.acts.filter(a => a.res === 'book').map(a => [a.id, a.wFrom, a.wTo, a.resourceWindow])).toEqual([
      ['book-RAG', 4, 4, {from: 4, to: 4}], ['book-Web', 7, 7, {from: 7, to: 7}],
    ]);
    expect(plan.def.learningReport!.durationEstimates!.Web).toMatchObject({bookWeeks: 1, addedWeeks: 1, totalWeeks: 9});
  });
  it('도서만 선택한 스킬은 각 스킬 순서에 따라 1주씩 순차 배정된다', () => {
    const input = sharedOption(), report = input.learningReport!;
    report.recommendations.skills.forEach(row => { row.courses = []; report.choices[row.name].course = null; });
    input.acts = ['RAG', 'Web'].map(name => ({id: `book-${name}`, skill: name, stage: 2, title: 'Book', res: 'book', hours: 12}));
    for (const name of ['RAG', 'Web']) report.choices[name].books = ['book'];
    expect(buildPlan(input, {hours: 6}, '').weeks).toBe(2);
    report.skillOrder.reverse();
    expect(buildPlan(input, {hours: 6}, '').def.learningReport!.durationEstimates!.RAG.bookWeeks).toBe(1);
    report.choices.Web.enabled = false;
    expect(buildPlan(input, {hours: 6}, '').def.learningReport!.durationEstimates!.RAG.bookWeeks).toBe(1);
    report.choices.RAG.books = [];
    input.acts = [];
    expect(buildPlan(input, {hours: 6}, '').weeks).toBe(0);
    report.choices.RAG.books = ['book'];
    expect(buildPlan(input, {hours: 12}, '').weeks).toBe(1);
  });
  it('제목이 같은 다른 ID의 도서는 각각 1주로 계산한다', () => {
    const input = sharedOption(), report = input.learningReport!;
    report.recommendations.skills.forEach(row => { row.courses = []; report.choices[row.name].course = null; });
    report.recommendations.skills.find(row => row.name === 'Web')!.books.push({id: 'other-book', title: 'book', hours: 12});
    report.choices.RAG.books = ['book']; report.choices.Web.books = ['other-book'];
    input.acts = [];
    expect(buildPlan(input, {hours: 6}, '').weeks).toBe(2);
  });
  it('시간 미확인과 수치 추정을 구분하고 계획 배정 합계에 미확인 1주를 명시한다', () => {
    const input = sharedOption();
    input.learningReport!.recommendations.skills.forEach(row => row.courses[0].id === 'shared' ? row.courses[0].hours = null : row.courses[0].estimated = ['hours']);
    const plan = buildPlan(input, {hours: 6}, '');
    expect(plan.weeks).toBe(6); expect(plan.totalH).toBe(23.4);
    expect(plan.totalHUnknown).toBe(true); expect(plan.totalHEstimated).toBe(true);
    expect(plan.def.learningReport!.durationEstimates!.Web.unknownCourses).toEqual(['shared']);
  });
  it('주당 시간 변경 시 도서 배정만 바꾸고 원본·카탈로그 시간·과제·비용을 보존한다', () => {
    const input = sharedOption();
    input.learningReport!.choices.RAG.books = ['book'];
    input.acts.push({id:'book-act',skill:'RAG',stage:2,title:'Book',res:'book',hours:12});
    input.acts.push({id:'task',skill:'RAG',stage:3,title:'Task',hours:8});
    const before = structuredClone(input);
    const first = buildPlan(input, {hours:6}, ''), changed = buildPlan(input, {hours:12}, '');
    expect(first).toMatchObject({weeks:8, materialHours:30.3, taskHours:8, totalH:38.3});
    expect(changed).toMatchObject({weeks:5, materialHours:36.3, taskHours:8, totalH:44.3});
    expect(first.acts.find(a=>a.res==='book')).toMatchObject({hours:6,catalogHours:12,hoursAllocation:'book-week'});
    expect(changed.acts.find(a=>a.res==='book')).toMatchObject({hours:12,catalogHours:12,hoursAllocation:'book-week'});
    expect(JSON.parse(JSON.stringify(first))).toEqual(first);
    expect(changed.cost).toBe(first.cost); expect(input).toEqual(before);
  });
  it('자료 없는 과제는 자료 0주를 유지하며 임의의 미래 주차를 만들지 않는다', () => {
    const input = sharedOption();
    input.learningReport!.recommendations.skills.forEach(row => {row.courses = []; input.learningReport!.choices[row.name].course = null;});
    input.acts = [{id: 'task', skill: 'Web', stage: 3, title: 'Task', hours: 100}];
    const plan = buildPlan(input, {hours: 6}, '');
    expect(plan.weeks).toBe(0); expect(plan.totalH).toBe(100);
    expect(plan.acts[0]).toMatchObject({wFrom: 1, wTo: 1});
  });
  it('자격 자료는 과제와 구분하고 중복 ID는 기타 자료 합계에 한 번만 더한다', () => {
    const input = sharedOption();
    input.acts.push({id:'task',skill:'RAG',stage:3,title:'Task',hours:8});
    for (const name of ['RAG', 'Web']) input.acts.push({id:`cert-${name}`,skill:name,stage:4,title:'Cert',res:'cert',task:true,hours:10});
    const plan = buildPlan(input, {hours:6}, '');
    expect(plan).toMatchObject({materialHours:24.3,taskHours:8,otherMaterialHours:10,totalH:42.3});
  });
});
