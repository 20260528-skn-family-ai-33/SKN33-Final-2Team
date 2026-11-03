import { blockedTo } from './model';
import type { OptionDef } from '@/api/types/draft';
import { describe, expect, it } from 'vitest';
import { freshWs } from '@/shared/state/workspace';
import { inputSignature, invalidateDraft, invalidateMaterialChoices } from './invalidation';
import { takeDraftInto } from './draftSync';
import { answerMemoryKey, pendingAnswers, rememberAnswers } from './quiz/assessment/answerMemory';

describe('앞단계 수정 후 초기화', () => {
  it('수정한 목표·학습 여건과 확정 로드맵을 보존하고 하위 결과를 제거한다', () => {
    const state = freshWs('u');
    state.draft.goal = '수정된 목표'; state.draft.prefs.hours = 4;
    state.draft.v2Assessment = { generationId: 'g', completed: true, materialsReady: true, activitiesReady: true };
    const plans = state.plans;
    invalidateDraft(state);
    expect(state.draft.goal).toBe('수정된 목표'); expect(state.draft.prefs.hours).toBe(4);
    expect(state.draft.v2Assessment).toBeUndefined(); expect(state.draft.gen).toBeNull(); expect(state.draftPlan).toBeNull();
    expect(state.plans).toBe(plans);
  });
  it('응답 변경은 문항을 유지하고 완료 상태와 그 뒤 계획을 무효화한다', () => {
    const state = freshWs('u'); state.draft.v2Assessment = { generationId: 'g', completed: true };
    invalidateDraft(state, 'answers');
    expect(state.draft.v2Assessment).toMatchObject({ generationId: 'g', completed: false, materialsReady: false, activitiesReady: false });
  });
  it('수정 전 입력에 대한 늦은 저장 응답이 완료된 점검을 되살리지 않는다', () => {
    const state = freshWs('u'); state.draftId = 'd'; state.draft.goal = '새 목표';
    const old = { ...state.draft, goal: '이전 목표', v2Assessment: { generationId: 'old', completed: true } };
    takeDraftInto(state, { draftId: 'd', draft: old }, true);
    expect(state.draft.goal).toBe('새 목표'); expect(state.draft.v2Assessment).toBeUndefined();
  });
});
describe('늦게 도착한 응답 저장 상태', () => {
  it('같은 입력이어도 수정 중인 응답을 예전 완료 상태로 되돌리지 않는다', () => {
    const state = freshWs('u'); state.draftId = 'd'; state.draft.goal = '목표';
    state.draft.v2Assessment = { generationId: 'g', completed: false };
    const previous = { ...state.draft, v2Assessment: { generationId: 'g', completed: true } };
    takeDraftInto(state, { draftId: 'd', draft: previous }, true);
    expect(state.draft.v2Assessment?.completed).toBe(false);
    takeDraftInto(state, { draftId: 'd', draft: previous });
    expect(state.draft.v2Assessment?.completed).toBe(true);
  });
});
describe('역량 테스트 선택 복원', () => {
  it('같은 직원·초안·문항·입력에서만 복원하며 퀴즈 0번 응답도 보존한다', () => {
    const key = answerMemoryKey('u', 'd', 'g', 'inputs');
    rememberAnswers(key, { s: 5, q: 0 }, 'quizzes');
    expect(pendingAnswers(key)).toEqual({ answers: { s: 5, q: 0 }, phase: 'quizzes' });
    expect(pendingAnswers(answerMemoryKey('u', 'd', 'new-generation', 'inputs'))).toBeUndefined();
    expect(pendingAnswers(answerMemoryKey('u', 'd', 'g', 'changed-inputs'))).toBeUndefined();
    expect(pendingAnswers(answerMemoryKey('other', 'd', 'g', 'inputs'))).toBeUndefined();
    pendingAnswers(key)!.answers.q = 4; expect(pendingAnswers(key)!.answers.q).toBe(0);
  });
});


describe('선택 단계부터 검토까지의 이동 호환성', () => {
  it('자료를 수정하면 문항·계획 선택은 유지하고 검토 진입을 막는다', () => {
    const state=freshWs('u');state.draft.goal='검색 구현';state.draft.detailsOk=true;
    state.draft.v2Assessment={generationId:'g',completed:true,materialsReady:true,materialsKey:'old',activitiesReady:true};
    const option:OptionDef={id:'A1',name:'Free',short:'기초',tagline:'목표',pros:[],cons:[],acts:[]};
    state.draft.gen={key:'h',options:{A1:option},missing:[]};state.draft.chosen='A1';
    invalidateDraft(state,'materials');
    expect(state.draft.v2Assessment?.completed).toBe(true);
    expect(blockedTo(state,'materials')).toBeNull();
    expect(blockedTo(state,'review')).toBe('/new/options');
    expect(state.draft.v2Assessment?.materialsKey).toBeUndefined();
    state.draft.v2Assessment!.materialsReady=true;
    expect(blockedTo(state,'review')).toBe('/new/options');
    state.pendingFlow=undefined; // A successful explicit material save clears the dirty marker.
    expect(blockedTo(state,'review')).toBeNull();
    invalidateDraft(state);
    expect(blockedTo(state,'review')).toBe('/new/details');
  });
});


describe('저장 전 하위 결과 복원 방지', () => {
  it('자료를 수정한 상태에서 이전 서버 응답이 와도 검토 완료를 되살리지 않는다', () => {
    const state=freshWs('u');state.draftId='d';state.draft.goal='검색 구현';
    state.draft.v2Assessment={generationId:'g',completed:true,materialsReady:true,materialsKey:'old',activitiesReady:true};
    const old=structuredClone(state.draft);
    invalidateDraft(state,'materials');
    takeDraftInto(state,{draftId:'d',draft:old},true);
    expect(state.draft.v2Assessment?.materialsReady).toBe(false);
    expect(state.draft.v2Assessment?.activitiesReady).toBe(false);
    expect(state.draftPlan).toBeNull();
    takeDraftInto(state,{draftId:'d',draft:old});
    expect(state.pendingFlow).toBeUndefined();
    expect(state.draft.v2Assessment?.materialsReady).toBe(true);
  });
});


describe('DB JSON 항목 순서 호환성', () => {
  it('서버가 학습 여건의 항목 순서를 바꿔 돌려줘도 입력 변경으로 판정하지 않는다', () => {
    const state=freshWs('u');state.draftId='d';state.draft.goal='검색 구현';
    state.draft.prefs={format:'',cert:'',hours:4,weeks:8,budget:'',etc:''};
    const server={...state.draft,prefs:{etc:'',budget:'',weeks:8,hours:4,cert:'',format:''},v2Assessment:{generationId:'g',completed:true}};
    expect(inputSignature(state.draft)).toBe(inputSignature(server));
    takeDraftInto(state,{draftId:'d',draft:server},true);
    expect(state.draft.v2Assessment?.completed).toBe(true);
    expect(state.pendingFlow).toBeUndefined();
  });
});

describe('코스별 자료 수정과 검토 이동',()=>{
  function ready(){const s=freshWs('u');s.draftId='d';s.draft.chosen='A1';s.draft.v2Assessment={generationId:'g',completed:true,materialsReady:true,activitiesReady:true,materialsKey:'old'};return s;}
  it('선택한 코스의 자료 수정은 검토 단계 바로가기를 막는다',()=>{
    const s=ready();invalidateMaterialChoices(s,'A1');
    expect(blockedTo(s,'review')).toBe('/new/options');expect(s.pendingFlow).toBe('materials');expect(s.draft.v2Assessment?.completed).toBe(true);
    const server={draftId:'d',draft:{...s.draft,v2Assessment:{generationId:'g',completed:true,materialsReady:true,activitiesReady:true,materialsKey:'old'}}};
    takeDraftInto(s,server,true);expect(blockedTo(s,'review')).toBe('/new/options');
  });
  it('다른 코스의 자료 수정은 현재 선택 코스의 검토를 초기화하지 않는다',()=>{
    const s=ready();const before=structuredClone(s);invalidateMaterialChoices(s,'A3');expect(s).toEqual(before);
  });
  it('늦은 응답의 준비 플래그가 남아도 미저장 표시는 검토 진입을 차단한다',()=>{
    const s=ready();s.pendingFlow='materials';expect(blockedTo(s,'review')).toBe('/new/options');
  });
});
