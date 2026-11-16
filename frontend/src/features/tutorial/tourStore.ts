/* 튜토리얼 진행 상태. 팝업에 답한 기록은 서버(계정별), 진행 중이라는 표시는 이 브라우저에만 둔다(새로 고쳐도 이어 가기 위한 것) */
import { create } from 'zustand';
import { accountApi } from '@/api/endpoints/account';
import { me, setTutorialAnswered } from '@/shared/state/session';
import { store } from '@/shared/state/workspace';
import { TOUR_STEPS } from './steps';

interface TourState {
  /** 따라갈지 묻는 팝업 */
  intro: boolean;
  active: boolean;
  /** TOUR_STEPS 의 번호. 안내할 것이 없는 화면에서는 -1 */
  index: number;
  /** '잠깐 숨기기'를 누른 화면 주소: 그 화면에서는 안내를 그리지 않고, 다른 화면으로 가면 다시 잇는다 */
  closedAt: string | null;
  /** 마지막 단계(확정)까지 따라와 끝난 직후: 끝났다는 안내를 닫을 때까지 보여 준다 */
  finished: boolean;
}

const IDLE: TourState = { intro: false, active: false, index: 0, closedAt: null, finished: false };
export const useTour = create<TourState>(() => IDLE);

const KEY = (id: string | number) => 'growpath.tour.' + id;
const remember = (on: boolean): void => {
  const m = me();
  if (!m) return;
  if (on) return store.set(KEY(m.id), '1');
  try {
    localStorage.removeItem(KEY(m.id));
  } catch {
    /* 저장 불가 환경 */
  }
};
export const tourInProgress = (id: string | number): boolean => store.get(KEY(id)) === '1';

export function startTour(): void {
  remember(true);
  useTour.setState({ ...IDLE, active: true });
}

/** 튜토리얼 끝내기: 튜토리얼을 끝낸다(내 정보의 '다시 보기'로만 다시 시작) */
export function stopTour(): void {
  remember(false);
  useTour.setState(IDLE);
}

/** 끝까지 따라왔을 때: 튜토리얼을 끝내고(새로 고쳐도 다시 잇지 않음) 끝났다는 안내를 띄운다 */
export function finishTour(): void {
  remember(false);
  useTour.setState({ ...IDLE, finished: true });
}

/** 화면만 내려놓기(로그아웃 등): 진행 중 표시는 남겨 다음 로그인에서 잇는다 */
export const resetTour = (): void => useTour.setState(IDLE);

/** 잠깐 숨기기: 이 화면에서만 안내를 치우고 자유롭게 쓰게 한다. 다음 화면으로 넘어가면 그 화면의 안내부터 잇는다 */
export const closeHere = (pathname: string): void => useTour.setState({ closedAt: pathname });

export function nextStep(): void {
  const { index } = useTour.getState();
  if (index + 1 >= TOUR_STEPS.length) stopTour();
  else useTour.setState({ index: index + 1 });
}

/** 팝업에 답함(따라가기·건너뛰기 모두). 기록에 실패해도 화면은 그대로 진행하고, 다음 로그인 때 다시 묻는다 */
export function answerIntro(follow: boolean): void {
  setTutorialAnswered();
  if (follow) startTour();
  else useTour.setState({ intro: false });
  accountApi.tutorialAnswered().catch((e: unknown) => console.warn('튜토리얼 응답을 저장하지 못했어요', e));
}
