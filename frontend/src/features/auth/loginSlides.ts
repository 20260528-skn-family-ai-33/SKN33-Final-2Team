/* 로그인 화면 우측 블록에 넘겨 보여 주는 서비스 화면 그림 (#282).
   그림 아래에는 설명 문구 한 줄만 적는다(화면 이름은 적지 않고, 그림을 읽어 주는 말로만 쓴다).
   그림은 slides/<테마>/<그림 이름>.webp 이고 scripts/capture-login-slides.mjs 로 다시 찍는다(그림 이름은 그 스크립트의 SHOTS 와 같아야 한다) */
import { DEFAULT_SKIN } from '@/skins/pick';

export interface LoginSlide {
  id: string;
  /** 그림 대신 읽어 줄 화면 이름(화면에는 적지 않는다) */
  name: string;
  /** 그림 아래에 적는 설명 문구 */
  text: string;
}

export const LOGIN_SLIDES: LoginSlide[] = [
  { id: 'result', name: '테스트 결과', text: '간단한 설문과 퀴즈로 내 지식을 확인해요' },
  { id: 'gen', name: '로드맵 3안 작성', text: '내게 맞는 3가지 로드맵을 만들어요' },
  { id: 'options', name: '로드맵·자료 선택', text: '원하는 코스와 학습 자료를 선택해요' },
  { id: 'review', name: '주차별 일정', text: '선택한 코스의 학습 일정을 확인해요' },
  { id: 'gantt', name: '전체 일정', text: '코스를 따라 학습을 진행해요' },
  { id: 'skillmap', name: '내 스킬 지도', text: '학습한 지식을 눈으로 확인해요' },
  { id: 'report', name: '학습 결과 보고서', text: '학습 전과 후를 비교해요' },
];

/* 주소만 미리 받아 두고(문자열) 그림 파일은 화면에 그릴 때 받는다 */
const FILES = import.meta.glob<string>('./slides/*/*.webp', { eager: true, query: '?url', import: 'default' });

/** 그 테마의 그림 주소. 그 테마 그림이 없으면 기본 테마 그림, 그것도 없으면 빈 값 */
export const slideSrc = (skin: string, id: string): string =>
  FILES[`./slides/${skin}/${id}.webp`] || FILES[`./slides/${DEFAULT_SKIN}/${id}.webp`] || '';
