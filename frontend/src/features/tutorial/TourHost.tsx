/* 새 로드맵 작성 튜토리얼 (#277) — 화면을 어둡게 덮고 지금 볼 곳만 비운 뒤, 덮은 자리에 큰 글자와 화살표로 안내한다.
   AI 가 만드는 동안에는 만들어지는 자리를 비추고 기다리라고 알린다. 대상이 화면 밖으로 나가도 덮은 채로 그쪽을 가리킨다.
   자리는 대상 덩어리의 나타나기(skins/reveal)가 끝난 뒤에 잡고, 그 뒤로는 화면이 그려질 때마다 대상을 따라간다.
   '잠깐 숨기기'는 이 화면에서만 안내를 치우고(다음 화면에서 다시 이음), '튜토리얼 끝내기'는 튜토리얼을 끝낸다.
   확정까지 따라오면 확정 화면 위에 튜토리얼이 끝났다는 안내를 띄운다 */
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { paths } from '@/app/paths';
import { ai } from '@/shared/state/ai';
import { meOf, useSession } from '@/shared/state/session';
import { useUi } from '@/shared/state/ui';
import { Icon } from '@/shared/ui/Icon';
import { draftActive, recs, useWs, ws } from '@/shared/state/workspace';
import { afterReveal } from '@/skins/afterReveal';
import { cutOf, holeOf, placeAway, placeNote, type Box, type NotePlace } from './spot';
import { isTourEnd, pickReady, screenCount, screenNo, stepForPath, waitText, TOUR_STEPS, type TourStep } from './steps';
import { answerIntro, closeHere, finishTour, nextStep, resetTour, startTour, stopTour, tourInProgress, useTour } from './tourStore';
import './tour.css';

const NOTE_W = 340;
const REVEAL_EDGE = 80; // 나타나기가 시작되는 선(화면 아래 끝에서 60px)보다 조금 넉넉하게
const MOVE_MS = 450; // tour.css 의 옮겨 가는 시간보다 조금 길게

const find = (name: string): HTMLElement | null => {
  for (const el of document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`)) {
    if (el.getClientRects().length) return el;
  }
  return null;
};
const first = (names: string[]): HTMLElement | null => names.map(find).find(Boolean) || null;
const canPress = (el: Element): boolean => !el.matches(':disabled, [aria-disabled="true"]');

/** 지금 비출 요소: 안내할 수 있으면 단계의 대상, 아직이면(만드는 중·버튼이 꺼짐) 기다리는 자리 */
function resolve(step: TourStep): { el: HTMLElement; els: HTMLElement[]; waiting: boolean } | null {
  const whole = first(step.targets);
  const ready = whole && (!step.when || document.querySelector(step.when)) ? whole : null;
  const els = !ready ? [] : step.focus ? [...ready.querySelectorAll<HTMLElement>(step.focus)].filter((x) => x.getClientRects().length) : [ready];
  if (els.length && (step.advance !== 'click' || canPress(els[0]))) return { el: els[0], els, waiting: false };
  const wait = step.wait && (!step.wait.busy || document.querySelector(step.wait.busy)) ? first(step.wait.targets) : null;
  if (!wait) return null;
  const also = step.wait?.also ? [...document.querySelectorAll<HTMLElement>(step.wait.also)].filter((x) => x.getClientRects().length) : [];
  return { el: wait, els: [wait, ...also], waiting: true };
}

/** 화면 위쪽에 붙어 있는 띠·상단 메뉴 아래 첫 자리(테마 변수에서 읽는다).
    상단 메뉴가 없는 좌측 메뉴 모드에서도 오른쪽 위 '튜토리얼 끝내기' 단추(띠 아래 14px, 높이 36px)와 겹치지 않을 만큼은 띄운다 */
const headTop = (): number => {
  const css = getComputedStyle(document.documentElement);
  return (parseFloat(css.getPropertyValue('--rib-h')) || 0) + Math.max((parseFloat(css.getPropertyValue('--nav-h')) || 0) + 20, 70);
};

/** 스크롤해도 화면 위에 붙어 있는 띠·상단 메뉴의 아래 끝(실제 자리에서 잰다). 비춘 자리는 이 아래에서만 연다.
    좌측 메뉴 모드의 메뉴처럼 화면 높이를 다 쓰는 것은 위에 붙은 띠가 아니므로 빼고,
    대상이 그 띠 안에 있으면(상단 메뉴의 '새 로드맵 작성') 그 띠는 자르는 기준에서 뺀다 */
const coverTop = (target: Element, vh: number): number => {
  let bottom = 0;
  for (const el of document.querySelectorAll('.ribbon, .side')) {
    if (el.contains(target)) continue;
    const pos = getComputedStyle(el).position;
    if (pos !== 'sticky' && pos !== 'fixed') continue;
    const r = el.getBoundingClientRect();
    if (r.height && r.height < vh / 3 && r.top <= bottom + 1) bottom = Math.max(bottom, r.bottom);
  }
  return Math.round(bottom);
};

/** 화면 아래에 붙어 있는 요약 줄(.step-bar)이 있으면 그 위까지가 보이는 자리다(대상이 그 줄 안에 있으면 화면 끝까지) */
const floorOf = (el: Element, vh: number): number => {
  const bar = document.querySelector('.step-bar');
  if (!bar || bar.contains(el)) return vh;
  const r = bar.getBoundingClientRect();
  return r.bottom > vh - 40 && r.top < vh ? r.top : vh;
};

interface Spot {
  /** 단계와 상태(기다리는 중인지)가 바뀌면 달라진다 */
  key: string;
  index: number;
  text: string;
  waiting: boolean;
  /** '다음' 단추를 두는 단계인지, 지금 누를 수 있는지 */
  next: boolean;
  open: boolean;
  /** 대상이 화면 밖으로 나가면 null(덮은 채로 그쪽을 가리킨다) */
  hole: Box | null;
  /** 상단 메뉴·아래 요약 줄에 걸려 잘린 쪽('top'·'bottom') */
  cut: string;
  note: NotePlace;
}

/** 지금 단계의 대상을 화면이 그려질 때마다 따라가며 비출 자리를 돌려준다. 비출 것이 없으면 null */
function useSpot(step: TourStep, index: number, noteRef: React.RefObject<HTMLElement | null>): Spot | null {
  const [spot, setSpot] = useState<Spot | null>(null);
  useEffect(() => {
    let raf = 0;
    let target: HTMLElement | null = null;
    let settled = false;
    let brought = false;
    let fitted = false;
    let waiting = false;
    let stopWaiting = (): void => {};
    let last = '';
    const show = (next: Spot | null): void => {
      const sig = JSON.stringify(next);
      if (sig === last) return;
      last = sig;
      setSpot(next);
    };
    const measure = (): Spot | null => {
      if (step.done && document.querySelector(step.done)) {
        nextStep();
        return null;
      }
      const found = resolve(step);
      const el = found?.el || null;
      if (el !== target) {
        stopWaiting();
        target = el;
        settled = false;
        brought = false;
        fitted = false;
        if (el) stopWaiting = afterReveal(el, () => void (settled = true));
      }
      if (!el || !found) return null;
      // 만드는 중이던 자리가 채워지면 크기가 달라지므로 자리를 다시 맞춘다
      if (found.waiting !== waiting) {
        waiting = found.waiting;
        fitted = false;
      }
      const vw = document.documentElement.clientWidth;
      const vh = window.innerHeight;
      const noteW = Math.min(NOTE_W, vw - 32);
      const noteH = noteRef.current?.offsetHeight || 170;
      // 여러 요소를 한 덩어리로 비출 때는 모두를 감싸는 자리
      const rectOf = (): { top: number; bottom: number; left: number; right: number; height: number } => {
        const rs = found.els.map((x) => x.getBoundingClientRect());
        const top = Math.min(...rs.map((x) => x.top));
        const bottom = Math.max(...rs.map((x) => x.bottom));
        return { top, bottom, left: Math.min(...rs.map((x) => x.left)), right: Math.max(...rs.map((x) => x.right)), height: bottom - top };
      };
      // 비춘 자리는 위에 붙은 띠·상단 메뉴와 아래 요약 줄 사이에서만 연다(스크롤로 그 밑에 들어간 부분은 덮어 둔다)
      const top = coverTop(el, vh);
      const floor = floorOf(el, vh);
      const boxOf = (): Box | null => {
        const r = rectOf();
        return holeOf({ x: r.left, y: r.top, w: r.right - r.left, h: r.height }, vw, floor, top);
      };
      // 대상을 한 번씩만 옮긴다: 작은 대상은 가운데로, 큰 영역은 상단 메뉴 바로 아래로.
      const bring = (): void => {
        const r = rectOf();
        window.scrollBy(0, r.height < 200 ? r.top - (vh - r.height) / 2 : r.top - headTop());
      };
      const r = rectOf();
      if (!settled) {
        // 나타나기는 화면 아래 끝에서 60px 넘게 들어와야 시작한다(skins/reveal). 그 선에 못 미치면 기다리기 전에 데려온다
        if (!brought && (r.bottom < headTop() || r.top > vh - REVEAL_EDGE)) bring();
        brought = true;
        return null;
      }
      if (!fitted) {
        // 나타나기가 끝난 자리에서: 잘려 있거나 안내 글 놓을 자리가 없으면 맞춘다
        fitted = true;
        const box = boxOf();
        if (r.top < headTop() || r.bottom > floor || !box || placeNote(box, vw, vh, noteW, noteH, false, headTop()).side === 'dock') bring();
      }
      const hole = boxOf();
      const whole = rectOf();
      const gate = step.gate ? find(step.gate) : null;
      return {
        key: `${step.id}:${found.waiting ? 'wait' : 'go'}`,
        index,
        text: found.waiting ? waitText(step, ai.mode() === 'ollama') : step.text,
        waiting: found.waiting,
        next: !found.waiting && step.advance === 'next',
        open: !step.gate || (!!gate && canPress(gate)),
        hole,
        cut: hole ? cutOf({ x: whole.left, y: whole.top, w: whole.right - whole.left, h: whole.height }, hole) : '',
        // 사용자가 스크롤해 대상이 화면 밖(상단 메뉴 밑 포함)으로 나가면 덮은 채로 그쪽을 가리킨다
        note: hole ? placeNote(hole, vw, vh, noteW, noteH, step.alignEnd, headTop()) : placeAway(whole.bottom <= vh / 2, vw, vh, noteW, noteH),
      };
    };
    const tick = (): void => {
      show(measure());
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      stopWaiting();
    };
  }, [step, index, noteRef]);
  return spot;
}

/** 대상 안에서 고르면(목표 후보·첫 문항의 답) '다음'을 누른 것처럼 넘어간다 */
function usePick(step: TourStep): void {
  useEffect(() => {
    const pick = step.pick;
    if (!pick) return;
    const within = step.targets.map((n) => `[data-tour="${n}"]`).join(',');
    let used = false;
    const onClick = (e: MouseEvent): void => {
      const t = e.target instanceof Element ? e.target.closest(pick) : null;
      if (used || !t || !t.closest(within) || !pickReady(step, (q) => !!document.querySelector(q))) return;
      used = true;
      // 화면이 그 누름을 먼저 처리한 뒤에 넘어간다
      window.setTimeout(() => {
        if (TOUR_STEPS[useTour.getState().index] === step) nextStep();
      }, 0);
    };
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [step]);
}

function Intro() {
  return (
    <div className="ov tour-intro">
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="tourIntroTitle">
        <div className="sheet-h">
          <div>
            <b id="tourIntroTitle">새 로드맵 만드는 법을 따라가 볼까요?</b>
            <small>건너뛰어도 내 정보에서 다시 볼 수 있어요.</small>
          </div>
        </div>
        <div className="sheet-f">
          <button className="btn pri" autoFocus onClick={() => answerIntro(true)}>
            따라가기
          </button>
          <button className="btn line" onClick={() => answerIntro(false)}>
            건너뛰기
          </button>
        </div>
      </div>
    </div>
  );
}

/** 끝까지 따라왔을 때: 화면을 덮은 채 가운데에 끝났다는 것을 크게 알리고, 닫으면 확정 화면을 쓰게 한다 */
function Finish() {
  const close = (): void => useTour.setState({ finished: false });
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);
  return (
    <div className="tour tour-finish">
      <div className="tour-block" style={{ inset: 0 }} onClick={close} />
      <section className="tour-done" role="dialog" aria-modal="true" aria-labelledby="tourDoneTitle">
        <svg className="tour-done-mark" viewBox="0 0 64 64" aria-hidden="true">
          <circle cx="32" cy="32" r="29" />
          <path d="M19 33l9 9 17-19" />
        </svg>
        <p className="tour-count">
          <b>{screenCount}</b> / {screenCount}
        </p>
        <h2 id="tourDoneTitle" className="tour-done-title">
          튜토리얼을 마쳤어요
        </h2>
        <p className="tour-done-sub">내 정보에서 다시 볼 수 있어요.</p>
        <button type="button" className="btn pri" autoFocus onClick={close}>
          확인
        </button>
      </section>
    </div>
  );
}

function Overlay({ spot, noteRef, pathname }: { spot: Spot; noteRef: React.RefObject<HTMLElement | null>; pathname: string }) {
  const vw = document.documentElement.clientWidth;
  const vh = window.innerHeight;
  // 처음 나타날 때는 화면 전체에서 대상으로 좁혀 들어오고, 단계가 바뀌면 다음 대상으로 옮겨 간다. 그 밖에는(스크롤 등) 바로 따라간다
  const [entered, setEntered] = useState(false);
  const [movedKey, setMovedKey] = useState('');
  useEffect(() => {
    const raf = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(raf);
  }, []);
  useEffect(() => {
    const t = window.setTimeout(() => setMovedKey(spot.key), MOVE_MS);
    return () => window.clearTimeout(t);
  }, [spot.key]);
  const moving = movedKey !== spot.key;

  const { hole, note } = spot;
  const away: Box = { x: Math.round(vw / 2), y: note.side === 'up' ? -40 : vh + 40, w: 0, h: 0 };
  const lit = entered ? hole || away : { x: 0, y: 0, w: vw, h: vh };
  return (
    <div className={`tour${moving ? ' is-moving' : ''}${spot.waiting ? ' is-waiting' : ''}`} data-side={note.side} data-end={note.end ? '' : undefined}>
      {/* 바깥 누름 막기: 구멍 둘레 네 면(구멍 안은 그대로 누를 수 있다). 대상이 화면 밖이면 전체를 막는다 */}
      {hole ? (
        <>
          <div className="tour-block" style={{ left: 0, top: 0, right: 0, height: hole.y }} />
          <div className="tour-block" style={{ left: 0, top: hole.y + hole.h, right: 0, bottom: 0 }} />
          <div className="tour-block" style={{ left: 0, top: hole.y, width: hole.x, height: hole.h }} />
          <div className="tour-block" style={{ left: hole.x + hole.w, top: hole.y, right: 0, height: hole.h }} />
        </>
      ) : (
        <div className="tour-block" style={{ inset: 0 }} />
      )}
      {/* 비춘 자리: 테두리와, 바깥을 덮는 어두운 그림자 */}
      <div className="tour-hole" data-cut={entered && hole && spot.cut ? spot.cut : undefined} style={{ left: lit.x, top: lit.y, width: lit.w, height: lit.h }} />
      <aside ref={noteRef} className="tour-note" role="dialog" aria-label="새 로드맵 작성 안내" aria-live="polite" style={{ left: note.x, top: note.y }}>
        <svg className="tour-arrow" viewBox="0 0 56 56" aria-hidden="true" key={`${spot.key}:${note.side}`}>
          <path d="M28 54V7" />
          <path d="M17 20 28 6l11 14" />
        </svg>
        <p className="tour-count">
          <b>{screenNo(spot.index)}</b> / {screenCount}
        </p>
        <p className="tour-text" key={spot.key}>
          {spot.waiting ? <span className="sp" aria-hidden="true" /> : null}
          {spot.text}
        </p>
        <div className="tour-acts">
          {spot.next ? (
            <button type="button" className="btn pri sm" disabled={!spot.open} onClick={nextStep}>
              다음
            </button>
          ) : null}
          <button type="button" className="tour-link" title="이 화면을 직접 써 보고, 다음 화면에서 안내를 이어 가요" onClick={() => closeHere(pathname)}>
            잠깐 숨기기
          </button>
        </div>
      </aside>
      {/* 끝내기는 잘못 누르지 않게 안내 글과 떨어뜨려 화면 구석에 둔다 */}
      <button type="button" className="tour-quit" onClick={stopTour}>
        <Icon name="x" />
        튜토리얼 끝내기
      </button>
    </div>
  );
}

function Guide({ step, index, pathname }: { step: TourStep; index: number; pathname: string }) {
  const noteRef = useRef<HTMLElement>(null);
  const spot = useSpot(step, index, noteRef);
  usePick(step);
  return spot ? <Overlay spot={spot} noteRef={noteRef} pathname={pathname} /> : null;
}

export function TourHost() {
  const user = useSession((s) => meOf(s.account));
  const answered = useSession((s) => (s.account?.accountType === 'employee' ? s.account.tutorialAnswered : true));
  const { pathname } = useLocation();
  const sheetOpen = useUi((s) => !!s.sheet);
  const { intro, active, index, closedAt, finished } = useTour();
  const owner = useWs((s) => s.owner);
  const uid = user?.id;

  // 로그인할 때 한 번: 하던 튜토리얼이 있으면 잇고, 아직 답하지 않았고 로드맵·초안이 없는 계정이면 따라갈지 묻는다.
  // 로그인 직후에는 계정이 먼저 정해지고 작업 공간은 조금 뒤에 온다. 빈 작업 공간을 보고 기존 사용자에게 묻지 않도록,
  // 이 계정의 작업 공간을 받은 뒤(owner 가 이 계정)에 판정한다
  const loaded = uid != null && owner === uid;
  useEffect(() => {
    if (!loaded || uid == null) return;
    if (tourInProgress(uid)) startTour();
    else if (answered === false && !recs(ws()).length && !draftActive(ws())) useTour.setState({ intro: true });
    // 답한 뒤에는 다시 판정하지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid, loaded]);
  useEffect(() => resetTour, [uid]);

  // 화면이 바뀌면 그 화면의 단계로 맞추고, 닫아 둔 안내를 다시 잇는다
  useEffect(() => {
    if (!active) return;
    if (isTourEnd(pathname)) finishTour();
    else useTour.setState((s) => ({ index: stepForPath(s.index, pathname), closedAt: s.closedAt === pathname ? s.closedAt : null }));
  }, [active, pathname]);

  if (sheetOpen) return null;
  if (intro) return pathname === paths.home ? <Intro /> : null;
  if (finished) return <Finish />;
  const step = active && closedAt !== pathname && stepForPath(index, pathname) === index ? TOUR_STEPS[index] : null;
  // 화면마다 새로 비춘다: 여러 화면에 걸친 시작 단계가 앞 화면에서 잡은 자리·나타나기 상태를 다음 화면으로 끌고 가지 않게
  return step ? <Guide key={pathname} step={step} index={index} pathname={pathname} /> : null;
}
