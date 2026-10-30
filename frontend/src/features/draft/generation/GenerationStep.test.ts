import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import type { Handoff } from '@/api/types/draft';
import { HandoffView } from './GenerationStep';

it('shows work and personal project history separately from the uploaded proposal', () => {
  const h: Handoff = {
    key:'fixture', goal:'학습 목표', domain:'SQL', gaps:[], focus:[], known:[], outcome:'',
    userNotes:[], agentNotes:[], startStage:1, startSuggested:1, startReason:'응답 근거', userEdited:[],
    resourceHints:[], projectFile:null, projectSummary:'새 기획서 요약',
    profile:{ workDescription:'현재 업무 설명', projectExperience:['이전 프로젝트 경험'] },
    prefs:{ format:'알아서', formatKey:'auto', certRes:null, certPlan:'없음', budgetWon:0, budgetAuto:true,
      budgetLimit:null, weeklyHours:null, hoursAuto:true, deadlineWeeks:null },
  };
  const html = renderToStaticMarkup(createElement(HandoffView, { h }));
  for (const value of ['본인 업무 설명', '현재 업무 설명', '본인 프로젝트 경험', '이전 프로젝트 경험', '기획서 요약', '새 기획서 요약']) {
    expect(html).toContain(value);
  }
});
