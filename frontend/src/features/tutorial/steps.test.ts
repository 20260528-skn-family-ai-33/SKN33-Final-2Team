import { describe, expect, it } from 'vitest';
import { paths } from '@/app/paths';
import { STEPS } from '@/features/draft/model';
import { holeOf, placeAway, placeNote } from './spot';
import { firstStepFor, isTourEnd, screenCount, screenNo, stepForPath, TOUR_STEPS } from './steps';

const at = (id: string): number => TOUR_STEPS.findIndex((s) => s.id === id);

describe('튜토리얼 단계 정의', () => {
  it('단계 이름이 겹치지 않고 화면 순서가 작성 흐름 순서와 같다', () => {
    expect(new Set(TOUR_STEPS.map((s) => s.id)).size).toBe(TOUR_STEPS.length);
    const order = [paths.newGoal, paths.newDetails, paths.newDetailsCheck, paths.newQuiz, paths.newResult, paths.newGen, paths.newOptions, paths.newReview];
    const seen = [...new Set(TOUR_STEPS.map((s) => s.path).filter((p): p is string => !!p))];
    expect(seen).toEqual(order);
  });

  it('작성 흐름의 모든 단계 화면에 안내가 하나 이상 있다', () => {
    for (const [, , path] of STEPS) expect(TOUR_STEPS.some((s) => s.path === path)).toBe(true);
  });

  it('보이는 진행 숫자는 화면 단위다: 같은 화면의 안내는 같은 번호, 화면이 바뀌면 1씩 늘어 끝 번호로 끝난다', () => {
    expect(screenCount).toBe(new Set(TOUR_STEPS.map((s) => s.screen)).size);
    expect(screenCount).toBeLessThan(TOUR_STEPS.length);
    expect(screenNo(0)).toBe(1);
    expect(screenNo(TOUR_STEPS.length - 1)).toBe(screenCount);
    TOUR_STEPS.forEach((s, i) => {
      if (!i) return;
      const same = TOUR_STEPS[i - 1].screen === s.screen;
      expect(screenNo(i) - screenNo(i - 1)).toBe(same ? 0 : 1);
    });
  });

  it("말풍선의 '다음'을 여는 대상은 같은 화면의 단계 대상이다", () => {
    for (const s of TOUR_STEPS.filter((x) => x.gate)) {
      expect(TOUR_STEPS.some((x) => x.path === s.path && x.targets.includes(s.gate as string))).toBe(true);
    }
  });
});

describe('주소로 단계 정하기', () => {
  it('작성 흐름 밖에서는 시작 단계, 흐름 안에서는 그 화면의 첫 단계', () => {
    expect(firstStepFor(paths.home)).toBe(0);
    expect(firstStepFor(paths.roadmaps)).toBe(0);
    expect(firstStepFor(paths.newGoal)).toBe(at('goal'));
    expect(firstStepFor(paths.newOptions)).toBe(at('courses'));
    expect(firstStepFor(paths.newReview)).toBe(at('summary'));
  });

  it('같은 화면 안에서 나아간 단계는 유지하고, 화면이 바뀌면 그 화면의 첫 단계로 간다', () => {
    expect(stepForPath(at('goal-next'), paths.newGoal)).toBe(at('goal-next'));
    expect(stepForPath(at('goal-next'), paths.newDetails)).toBe(at('conditions'));
    expect(stepForPath(at('confirm'), paths.newOptions)).toBe(at('courses'));
    expect(stepForPath(at('skills'), paths.home)).toBe(0);
  });

  it('안내할 것이 없는 하위 화면에서는 쉬고, 돌아오면 다시 잇는다', () => {
    expect(at('result')).toBeLessThan(at('answers'));
    expect(at('answers')).toBeLessThan(at('result-next'));
    expect(stepForPath(at('result-next'), paths.newResultEdit)).toBe(-1);
    expect(stepForPath(-1, paths.newResult)).toBe(at('result'));
  });

  it('확정 직후 화면에서만 끝낸다', () => {
    expect(isTourEnd(paths.confirmed('p1'))).toBe(true);
    expect(isTourEnd(paths.roadmap('p1'))).toBe(false);
    expect(isTourEnd(paths.newReview)).toBe(false);
  });
});

describe('기다리는 안내', () => {
  it('AI 가 만드는 구간에는 기다리라는 문구와 비출 곳이 있다', () => {
    for (const id of ['skills', 'quiz', 'gen', 'materials', 'summary']) {
      const s = TOUR_STEPS[at(id)];
      expect(s.wait?.targets.length).toBeGreaterThan(0);
      expect(s.wait?.text).toMatch(/AI가/);
    }
  });

  it('고르면 넘어가는 단계에도 직접 넘어갈 단추가 있다', () => {
    for (const s of TOUR_STEPS.filter((x) => x.pick)) expect(s.advance).toBe('next');
  });

  it('만들다 실패할 수 있는 구간은 만드는 중 표시가 있을 때만 기다리라고 한다(실패 화면의 오류·다시 시도를 가리지 않음)', () => {
    for (const id of ['skills', 'materials', 'summary']) expect(TOUR_STEPS[at(id)].wait?.busy).toBeTruthy();
  });

  it('버튼 단계의 기다리는 안내는 만드는 중 표시가 있을 때만 뜬다(저장하는 잠깐 동안에는 뜨지 않음)', () => {
    for (const s of TOUR_STEPS.filter((x) => x.advance === 'click' && x.wait && x.id !== 'gen')) expect(s.wait?.busy).toBeTruthy();
  });
});

describe('비출 자리와 안내 글 자리', () => {
  const VW = 1280;
  const VH = 800;

  it('대상 둘레에 여백을 두고 화면 안으로 자른다', () => {
    expect(holeOf({ x: 100, y: 200, w: 300, h: 40 }, VW, VH)).toEqual({ x: 92, y: 192, w: 316, h: 56 });
    expect(holeOf({ x: -50, y: -400, w: 2000, h: 3000 }, VW, VH)).toEqual({ x: 0, y: 0, w: VW, h: VH });
  });

  it('화면 밖 대상은 비추지 않는다', () => {
    expect(holeOf({ x: 100, y: 900, w: 300, h: 40 }, VW, VH)).toBeNull();
    expect(holeOf({ x: 100, y: -200, w: 300, h: 40 }, VW, VH)).toBeNull();
  });

  it('아래 → 위 → 옆 순으로 놓고 화면 밖으로 나가지 않는다', () => {
    expect(placeNote({ x: 100, y: 100, w: 200, h: 40 }, VW, VH, 300, 150)).toEqual({ side: 'below', end: false, x: 100, y: 200 });
    expect(placeNote({ x: 1200, y: 700, w: 70, h: 60 }, VW, VH, 300, 150)).toEqual({ side: 'above', end: false, x: 964, y: 490 });
    expect(placeNote({ x: 40, y: 20, w: 500, h: 770 }, VW, VH, 300, 150).side).toBe('right');
    expect(placeNote({ x: 700, y: 20, w: 570, h: 770 }, VW, VH, 300, 150).side).toBe('left');
  });

  it('오른쪽 끝에 맞추면 비춘 자리의 오른쪽 아래에 놓인다', () => {
    expect(placeNote({ x: 100, y: 100, w: 900, h: 120 }, VW, VH, 300, 150, true)).toEqual({ side: 'below', end: true, x: 700, y: 280 });
  });

  it('화살표 놓을 틈이 없으면 바로 아래·위에 붙여 쓴다', () => {
    expect(placeNote({ x: 80, y: 120, w: 1100, h: 480 }, VW, VH, 300, 150)).toEqual({ side: 'under', x: 80, y: 616 });
    expect(placeNote({ x: 80, y: 190, w: 1100, h: 600 }, VW, VH, 300, 150)).toEqual({ side: 'over', x: 80, y: 24 });
  });

  it('대상이 화면을 채우면 아래 가운데에 붙인다', () => {
    expect(placeNote({ x: 0, y: 0, w: VW, h: VH }, VW, VH, 300, 150)).toEqual({ side: 'dock', x: 490, y: 634 });
  });

  it('대상이 화면 밖으로 나가면 가운데에서 그쪽을 가리킨다', () => {
    expect(placeAway(true, VW, VH, 300, 150)).toEqual({ side: 'up', x: 490, y: 325 });
    expect(placeAway(false, VW, VH, 300, 150).side).toBe('down');
  });
});
