/* 스킬 지도 계산 (5차 gp-skillmap.js 를 옮김 · 화면과 분리한 순수 계산)
   - 점 = 팀 DB 스킬 태그 하나, 점 크기 = 그 스킬이 붙은 강좌·도서·자격 수, 이름 아래 = 분야
   - 화살표 = 선수 관계(먼저 배울 스킬 → 다음 스킬). 아직 팀 DB 에 없어 서버가 초안 파일을 읽어 준다(GET /skills/map · 설계서 밖)
   - 이 로드맵이 다루는 스킬: 자료 활동은 자료에 붙은 팀 DB 스킬, 직접 수행 과제는 로드맵 에이전트가 고른 스킬(a.skills).
     과제에 스킬이 없으면 같은 단계(없으면 앞 단계, 그래도 없으면 뒤 단계) 자료의 스킬을 따른다
   - 배치는 이어진 스킬끼리 모이는 힘 배치. 시작 자리를 정해 두어 매번 같은 모양이 나온다 */
import type { SkillMapData } from '@/api/types/catalog';
import type { Activity, PlanContent } from '@/api/types/plan';
import type { Resource } from '@/api/types/catalog';

/** 글자 폭 재기(SVG 는 자동 줄바꿈이 없음). 시험에서는 바꿔 끼울 수 있다 */
export type Measure = (t: string, size: number, weight?: number) => number;

export function canvasMeasure(): Measure {
  const cv = document.createElement('canvas').getContext('2d') as CanvasRenderingContext2D;
  const font = getComputedStyle(document.body).fontFamily;
  return (t, size, weight) => {
    cv.font = `${weight || 400} ${size}px ${font}`;
    return cv.measureText(t).width;
  };
}

export function wrap(text: string, maxW: number, size: number, weight: number, maxLines: number, tw: Measure): string[] {
  const lines: string[] = [];
  let cur = '';
  String(text)
    .split(' ')
    .forEach((w) => {
      const t = cur ? `${cur} ${w}` : w;
      if (!cur || tw(t, size, weight) <= maxW) cur = t;
      else {
        lines.push(cur);
        cur = w;
      }
    });
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    lines.length = maxLines;
    let last = lines[maxLines - 1];
    while (last && tw(last + '…', size, weight) > maxW) last = last.slice(0, -1);
    lines[maxLines - 1] = last + '…';
  }
  return lines;
}

export interface Rel {
  parents: Record<number, number[]>;
  kids: Record<number, number[]>;
}
export function relOf(data: SkillMapData): Rel {
  const parents: Record<number, number[]> = {};
  const kids: Record<number, number[]> = {};
  data.prerequisites.forEach(([a, b]) => {
    (parents[b] = parents[b] || []).push(a);
    (kids[a] = kids[a] || []).push(b);
  });
  return { parents, kids };
}

export type Cover = Map<number, { a: Activity }[]>;

export function coverOf(data: SkillMapData, pl: PlanContent, resOf: (id: string | null | undefined) => Resource | null): Cover {
  const byName = Object.fromEntries(data.skills.map((s) => [s.name, s.id]));
  const resSkills = (a: Activity) => ((resOf(a.res) || ({} as Resource)).skills || []).map((n) => byName[n]).filter(Boolean) as number[];
  const ofStage = (n: number) => [...new Set(pl.acts.filter((a) => a.stage === n && a.res).flatMap(resSkills))];
  const inherit = (n: number) => {
    for (const s of [n, n - 1, n - 2, n - 3, n + 1, n + 2, n + 3]) {
      if (s < 1 || s > 4) continue;
      const k = ofStage(s);
      if (k.length) return k;
    }
    return [];
  };
  const taskSkills = (a: Activity) => {
    const ids = [...new Set((a.skills || []).map((n) => byName[n]).filter(Boolean))] as number[];
    return ids.length ? ids : inherit(a.stage);
  };
  const cov: Cover = new Map();
  pl.acts.forEach((a) =>
    (a.res ? resSkills(a) : taskSkills(a)).forEach((id) => {
      if (!cov.has(id)) cov.set(id, []);
      cov.get(id)!.push({ a });
    }),
  );
  return cov;
}

export const actWeek = (a: Activity) => (a.wFrom === a.wTo ? `${a.wFrom}주차` : `${a.wFrom}~${a.wTo}주차`);

/** 주차 꼬리표: 그 스킬을 다루는 활동들의 주차를 이어 붙인다(1,2,3,5,6 → '1~3·5~6주차'). 세 덩어리 이상이면 처음~끝.
    계획에 주차가 없으면(옛 기록) 단계로 대신한다 */
export function weeksOf(list: { a: Activity }[]): string {
  if (list.some((x) => x.a.wFrom == null || x.a.wTo == null))
    return `${[...new Set(list.map((x) => x.a.stage))].sort().join('·')}단계`;
  const ws = [...new Set(list.flatMap((x) => Array.from({ length: x.a.wTo - x.a.wFrom + 1 }, (_, i) => x.a.wFrom + i)))].sort((p, q) => p - q);
  const runs: [number, number][] = [];
  ws.forEach((w) => {
    const r = runs[runs.length - 1];
    if (r && w === r[1] + 1) r[1] = w;
    else runs.push([w, w]);
  });
  const fmt = ([a, b]: [number, number]) => (a === b ? `${a}` : `${a}~${b}`);
  return `${runs.length > 2 ? fmt([runs[0][0], runs[runs.length - 1][1]]) : runs.map(fmt).join('·')}주차`;
}

export interface SmNode {
  id: number;
  name: string;
  cat: string;
  n: number;
  r: number;
  lines: string[];
  bw: number;
  bh: number;
  x: number;
  y: number;
  fx: number;
  fy: number;
}

export interface Layout {
  nodes: SmNode[];
  byId: Record<number, SmNode>;
}

/** 배치(자료가 바뀔 때만 다시 계산) */
export function place(data: SkillMapData, tw: Measure): Layout {
  const nodes: SmNode[] = data.skills.map((s) => ({
    id: s.id,
    name: s.name,
    cat: s.category,
    n: s.resources,
    r: 5 + Math.sqrt(s.resources) * 0.6,
    lines: wrap(s.name, 116, 11.5, 650, 2, tw),
    bw: 0,
    bh: 0,
    x: NaN,
    y: NaN,
    fx: 0,
    fy: 0,
  }));
  const byId: Record<number, SmNode> = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const { parents, kids } = relOf(data);
  nodes.forEach((n) => {
    n.bw = Math.max(n.r * 2, ...n.lines.map((l) => tw(l, 11.5, 650)), tw(n.cat, 10.5)) + 6;
    n.bh = n.r * 2 + 6 + n.lines.length * 15 + 13;
  });
  // 처음 자리: 뿌리(선수 없는 스킬)마다 아래 스킬 수만큼 부채꼴을 나누고, 선수 깊이만큼 바깥으로
  const roots = nodes.filter((n) => !parents[n.id]).map((n) => n.id);
  const tkids: Record<number, number[]> = {};
  const seen = new Set(roots);
  const queue = roots.slice();
  while (queue.length) {
    const u = queue.shift() as number;
    (kids[u] || []).forEach((v) => {
      if (!seen.has(v)) {
        seen.add(v);
        (tkids[u] = tkids[u] || []).push(v);
        queue.push(v);
      }
    });
  }
  const leaves = (u: number): number => ((tkids[u] || []).length ? tkids[u].reduce((s, v) => s + leaves(v), 0) : 1);
  const put = (u: number, depth: number, from: number, to: number) => {
    const mid = (from + to) / 2;
    const R = 70 + depth * 115;
    byId[u].x = Math.cos(mid) * R;
    byId[u].y = Math.sin(mid) * R;
    let f = from;
    (tkids[u] || []).forEach((v) => {
      const span = ((to - from) * leaves(v)) / leaves(u);
      put(v, depth + 1, f, f + span);
      f += span;
    });
  };
  roots.sort((a, b) => leaves(b) - leaves(a) || a - b);
  const total = roots.reduce((s, r) => s + leaves(r), 0) || 1;
  let a0 = -Math.PI / 2;
  roots.forEach((r) => {
    const span = (2 * Math.PI * leaves(r)) / total;
    put(r, 0, a0, a0 + span);
    a0 += span;
  });
  nodes.forEach((n, i) => {
    if (Number.isNaN(n.x)) {
      // 선수 관계가 순환이라 뿌리에서 닿지 않는 스킬
      n.x = Math.cos(i) * 300;
      n.y = Math.sin(i) * 300;
    }
  });
  const L = data.prerequisites.map(([a, b]) => ({ a: byId[a], b: byId[b] })).filter((l) => l.a && l.b);
  const N = 500;
  for (let it = 0; it < N; it++) {
    const alpha = 1 - it / N;
    nodes.forEach((n) => {
      n.fx = -n.x * 0.004;
      n.fy = -n.y * 0.004;
    });
    L.forEach(({ a, b }) => {
      const vx = b.x - a.x;
      const vy = b.y - a.y;
      const d = Math.hypot(vx, vy) || 0.01;
      const f = ((d - 105) / d) * 0.05;
      a.fx += vx * f;
      a.fy += vy * f;
      b.fx -= vx * f;
      b.fy -= vy * f;
    });
    for (let i = 0; i < nodes.length; i++)
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const vx = b.x - a.x;
        const vy = b.y - a.y;
        const d2 = Math.max(vx * vx + vy * vy, 400);
        const d = Math.sqrt(d2);
        const f = 4200 / d2;
        a.fx -= (vx / d) * f;
        a.fy -= (vy / d) * f;
        b.fx += (vx / d) * f;
        b.fy += (vy / d) * f;
      }
    const lim = 22 * alpha + 1;
    nodes.forEach((n) => {
      n.x += Math.max(-lim, Math.min(lim, n.fx));
      n.y += Math.max(-lim, Math.min(lim, n.fy));
    });
    // 점 + 아래 글자를 한 상자로 보고 겹치면 바로 떼어 놓는다
    if (it > N * 0.3)
      for (let i = 0; i < nodes.length; i++)
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          const ox = (a.bw + b.bw) / 2 + 10 - Math.abs(a.x - b.x);
          const ay = a.y - a.r + a.bh / 2;
          const by = b.y - b.r + b.bh / 2;
          const oy = (a.bh + b.bh) / 2 + 8 - Math.abs(ay - by);
          if (ox > 0 && oy > 0) {
            if (ox / (a.bw + b.bw) < oy / (a.bh + b.bh)) {
              const s = a.x < b.x ? -1 : 1;
              a.x += (s * ox) / 2;
              b.x -= (s * ox) / 2;
            } else {
              const s = ay < by ? -1 : 1;
              a.y += (s * oy) / 2;
              b.y -= (s * oy) / 2;
            }
          }
        }
  }
  return { nodes, byId };
}
