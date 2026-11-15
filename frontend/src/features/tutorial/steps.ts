/* 새 로드맵 작성 튜토리얼의 단계 정의 (#277) — 순서·화면·대상·문구를 이 파일 한 곳에 둔다.
   로그인 화면에 넣을 작성 흐름 촬영도 이 순서를 그대로 쓴다(화면 코드를 가져오지 않는 순수 자료).
   대상은 화면 요소에 붙인 data-tour 이름이다. 진행 위치는 지금 주소로 정하므로 새로 고쳐도 그 화면의 첫 단계부터 이어진다 */
import { paths } from '@/app/paths';

export interface TourStep {
  id: string;
  /** 단계가 속한 화면 주소. null 은 작성 흐름 밖의 모든 화면(시작 단계) */
  path: string | null;
  /** 화면 이름(촬영 자막·읽기 프로그램용) */
  screen: string;
  /** data-tour 이름. 앞에서부터 화면에 보이는 첫 요소를 비춘다 */
  targets: string[];
  text: string;
  /** click: 비춘 요소를 눌러 다음 화면으로 간다 · next: 안내의 '다음' · auto: 화면 안에서 할 일을 마치면 넘어간다 */
  advance: 'click' | 'next' | 'auto';
  /** next 단계에서, 이 data-tour 요소를 누를 수 있게 된 뒤에 '다음'을 켠다 */
  gate?: string;
  /** 화면에 이 선택자에 맞는 요소가 생긴 뒤에 안내한다(AI 가 내용을 만드는 동안에는 wait 를 보여 준다) */
  when?: string;
  /** 대상 전체가 아니라 그 안의 이 요소만 비춘다. 여러 개가 맞으면 모두를 한 덩어리로 비춘다 */
  focus?: string;
  /** 아직 안내할 수 없을 때(AI 가 만드는 중 · 버튼이 꺼져 있음) 대신 비출 곳과 기다리라는 문구.
      busy 가 있으면 그 선택자에 맞는 요소(만드는 중 표시)가 있을 때만 기다리라고 한다 — 실패해서 멈춘 화면을 '만드는 중'이라 하지 않게.
      also 에 맞는 요소들은 비추는 자리에 함께 넣는다 */
  wait?: { targets: string[]; text: string; busy?: string; also?: string };
  /** 대상 안에서 이 선택자에 맞는 것을 누르면 '다음'을 누른 것과 같다 */
  pick?: string;
  /** 안내 글을 비춘 자리의 오른쪽 끝에 맞춘다(왼쪽 아래에 가리면 안 되는 내용이 있을 때) */
  alignEnd?: boolean;
  /** 이 선택자에 맞는 요소가 있으면 이미 지난 단계다 */
  done?: string;
}

const ON = (name: string): string => `[data-tour="${name}"]:not(:disabled)`;
/* 버튼은 저장하는 잠깐 동안에도 꺼진다. 그때를 'AI 가 만드는 중'으로 안내하지 않도록, 기다리라는 안내는 화면의 만드는 중 표시가 있을 때만 한다 */
const SKILLS_BUSY = '[data-tour="skills-box"] :is(.input-skills-initial, .loading, .input-skills-spinner)';

export const TOUR_STEPS: TourStep[] = [
  { id: 'start', path: null, screen: '홈', targets: ['start', 'start-nav'], text: '여기서 시작해요.', advance: 'click' },

  { id: 'goal', path: paths.newGoal, screen: '목표·기획서', targets: ['goal-input'], text: '키우고 싶은 역량을 적거나 후보를 골라요.', advance: 'next', gate: 'goal-next', pick: '.gs-it' },
  { id: 'doc', path: paths.newGoal, screen: '목표·기획서', targets: ['doc'], text: '기획서가 있으면 올려요. 선택 사항이라 건너뛰어도 돼요.', advance: 'next' },
  {
    id: 'goal-next', path: paths.newGoal, screen: '목표·기획서', targets: ['goal-next'], text: '다 됐으면 넘어가요.', advance: 'click',
    wait: { targets: ['doc'], text: 'AI가 기획서를 읽고 있어요. 다 읽으면 넘어갈 수 있어요.', busy: '[data-tour="doc"] .agents' },
  },

  { id: 'conditions', path: paths.newDetails, screen: '세부 사항·스킬', targets: ['conditions'], text: '학습 여건은 비워 두면 AI가 정해요.', advance: 'next' },
  {
    id: 'skills', path: paths.newDetails, screen: '세부 사항·스킬', targets: ['skills-box'], text: 'AI가 고른 스킬이에요. 순서를 바꾸거나 뺄 수 있어요.', advance: 'next',
    when: '[data-tour="skills"]', wait: { targets: ['skills-box'], text: 'AI가 목표에 맞는 스킬을 고르고 있어요. 잠시만 기다려 주세요.', busy: SKILLS_BUSY },
  },
  {
    id: 'details-next', path: paths.newDetails, screen: '세부 사항·스킬', targets: ['details-next'], text: '스킬을 정했으면 넘어가요.', advance: 'click',
    wait: { targets: ['skills-box'], text: 'AI가 스킬을 다시 고르고 있어요. 잠시만 기다려 주세요.', busy: SKILLS_BUSY },
  },

  { id: 'check-goal', path: paths.newDetailsCheck, screen: '입력 내용 확인', targets: ['check'], text: '입력한 목표와 프로젝트 요약이에요.', advance: 'next', focus: '.check-goal' },
  { id: 'check-skills', path: paths.newDetailsCheck, screen: '입력 내용 확인', targets: ['check'], text: '학습 여건과 고른 스킬이에요.', advance: 'next', focus: ':scope > :not(.check-goal)' },
  { id: 'check-next', path: paths.newDetailsCheck, screen: '입력 내용 확인', targets: ['check-next'], text: '맞으면 역량 테스트로 가요.', advance: 'click' },

  {
    id: 'quiz', path: paths.newQuiz, screen: '역량 테스트', targets: ['quiz-first'], text: '문항마다 하나씩 골라요. 설문 다음에 퀴즈가 이어져요.', advance: 'next', pick: 'input[type="radio"]',
    wait: { targets: ['quiz-wait'], text: 'AI가 내 목표에 맞는 문항을 만들고 있어요. 잠시만 기다려 주세요.' },
  },

  { id: 'result', path: paths.newResult, screen: '테스트 결과', targets: ['result-summary'], text: '역량 테스트 결과예요.', advance: 'next' },
  { id: 'answers', path: paths.newResult, screen: '테스트 결과', targets: ['result-review'], text: '문항마다 내 답과 정답, 해설을 비교해 볼 수 있어요.', advance: 'next' },
  { id: 'result-next', path: paths.newResult, screen: '테스트 결과', targets: ['result-next'], text: '다음을 누르면 로드맵 3안을 만들어요.', advance: 'click' },

  {
    // 기다리는 동안에는 진행 막대와 그 아래 코스별 작성 상황까지 함께 비춘다
    id: 'gen', path: paths.newGen, screen: '로드맵 3안 작성', targets: ['gen-next'], text: '3안이 준비됐어요.', advance: 'click', alignEnd: true,
    wait: { targets: ['gen-wait'], text: 'AI가 방식이 다른 로드맵 3안을 만들고 있어요. 1~2분쯤 걸려요.', also: '[data-tour="gen-rows"] > .agent' },
  },

  { id: 'courses', path: paths.newOptions, screen: '로드맵·자료 선택', targets: ['courses'], text: '코스 하나를 골라요.', advance: 'auto', done: '[data-tour="courses"] .opt-course.is-on' },
  {
    id: 'materials', path: paths.newOptions, screen: '로드맵·자료 선택', targets: ['materials'], text: '고른 코스의 강좌와 도서예요. 바꿀 수 있어요.', advance: 'next',
    when: ON('options-next'), wait: { targets: ['materials'], text: 'AI가 고른 코스에 맞는 강좌와 도서를 찾고 있어요. 1~2분쯤 걸릴 수 있어요.', busy: '.step-bar-wait' },
  },
  {
    id: 'options-next', path: paths.newOptions, screen: '로드맵·자료 선택', targets: ['options-next'], text: '자료를 정했으면 검토로 넘어가요.', advance: 'click',
    wait: { targets: ['materials'], text: 'AI가 자료를 다시 준비하고 있어요. 잠시만 기다려 주세요.', busy: '.step-bar-wait' },
  },

  {
    id: 'summary', path: paths.newReview, screen: '검토·확정', targets: ['summary'], text: '전체 기간과 학습 시간이에요.', advance: 'next',
    when: ON('confirm'), wait: { targets: ['summary'], text: 'AI가 고른 자료로 일정과 과제를 만들고 있어요. 30초에서 1분쯤 걸려요.' },
  },
  { id: 'schedule', path: paths.newReview, screen: '검토·확정', targets: ['schedule'], text: '주차마다 할 일이에요.', advance: 'next', when: ON('confirm') },
  { id: 'tasks', path: paths.newReview, screen: '검토·확정', targets: ['tasks'], text: '스킬마다 해 볼 과제예요. 다른 과제로 바꿀 수 있어요.', advance: 'next', when: ON('confirm'), focus: '.rv-skill' },
  {
    id: 'confirm', path: paths.newReview, screen: '검토·확정', targets: ['confirm'], text: '확정하면 로드맵이 시작돼요.', advance: 'click',
    wait: { targets: ['tasks'], text: 'AI가 과제를 다시 만들고 있어요. 잠시만 기다려 주세요.', busy: '.rv-status' },
  },
];

/** 작성 흐름의 주소지만 따로 안내할 단계가 없는 화면(하위 화면). 여기서는 아무것도 비추지 않는다 */
const QUIET_PATHS: string[] = [paths.newResultEdit, paths.newMaterials];

/** 그 주소에서 시작할 단계 번호. 안내할 것이 없는 화면이면 -1 */
export function firstStepFor(pathname: string): number {
  const i = TOUR_STEPS.findIndex((s) => s.path === pathname);
  if (i >= 0) return i;
  return QUIET_PATHS.includes(pathname) ? -1 : 0;
}

/** 주소가 바뀌었을 때의 단계 번호: 지금 단계가 그 화면의 것이면 그대로, 아니면 그 화면의 첫 단계 */
export function stepForPath(index: number, pathname: string): number {
  const first = firstStepFor(pathname);
  if (first < 0) return -1;
  const cur = TOUR_STEPS[index];
  return cur && cur.path === TOUR_STEPS[first].path ? index : first;
}

/** 로드맵을 확정한 직후의 화면이면 튜토리얼을 끝낸다 */
export const isTourEnd = (pathname: string): boolean => /^\/roadmaps\/[^/]+\/confirmed$/.test(pathname);
