import { useState } from 'react';
import { useGo } from '@/shared/hooks/useGo';
import { Link } from 'react-router';
import { trackName } from '@/shared/constants/data';
/* 부서장 코멘트 (10/14 · 5차 scr.comment · P.commentView·cmTag·cmItem·commentReq)
   쌓이고, 상태(새·확인함·vN에 반영)가 직원·부서장 화면에 같이 보인다. 답글은 없다 */
import type { ReactNode } from 'react';
import { plansApi } from '@/api/endpoints/plans';
import type { Comment, PlanRecord } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { D } from '@/shared/constants/data';
import { failToast } from '@/shared/lib/fail';
import { me } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { newComments, updateWs, useWs } from '@/shared/state/workspace';
import { Page } from '@/shared/ui/parts';
import { cmBy } from './parts';
import { busyPlan, confirmReviseComment, freshRev, revise, takePlan } from './planActions';

export function CommentView({ c }: { c: Pick<Comment, 'fit' | 'fitText' | 'level' | 'levelText' | 'free'> }) {
  const fit = D.commentFit.find((x) => x[0] === c.fit)?.[1];
  const lv = D.commentLevel.find((x) => x[0] === c.level)?.[1];
  return (
    <div className="cmt">
      <div className="card">
        <p className="q">업무 적합성 · 담당 업무와 부서 AI 사업에 맞는가</p>
        <p>
          <b>{fit || '의견 없음'}</b>
          {c.fitText ? ` — ${c.fitText}` : ''}
        </p>
      </div>
      <div className="card">
        <p className="q">수준·기간·분량</p>
        <p>
          <b>{lv || '의견 없음'}</b>
          {c.levelText ? ` — ${c.levelText}` : ''}
        </p>
      </div>
      {c.free ? (
        <div className="card">
          <p className="q">자유 의견</p>
          <p>{c.free}</p>
        </div>
      ) : null}
    </div>
  );
}

export const CmTag = ({ c, mgr }: { c: Comment; mgr?: boolean }) =>
  c.status === 'applied' ? (
    <span className="tag ok" title={c.appliedVersion ? `v${c.appliedVersion}에 반영` : undefined}>{mgr ? '수정 완료' : '완료'}</span>
  ) : c.status === 'read' ? (
    <span className="tag line">{mgr ? '완료' : '확인함'}</span>
  ) : (
    <span className="tag acc">{mgr ? '확인 전' : '새 코멘트'}</span>
  );

export const cmMine = (c: Comment): boolean => !!(c.byCode && c.byCode === me()?.code);

export const feedbackReasons: Readonly<Record<string, string>> = {
  '업무 적용': '학습 내용을 실제 업무에 적용할 방법을 살펴보세요.',
  '산출물·검증': '산출물의 제출 내용과 결과를 확인할 기준을 살펴보세요.',
  '강좌·도서': '선택한 자료가 학습 목표에 맞는지 살펴보세요.',
  '난이도·분량': '현재 수준과 학습 시간에 맞는지 살펴보세요.',
  '학습 목표': '이 스킬에서 달성할 목표를 구체적으로 정리해 보세요.',
};

export function selectedFeedbackReasons(value = '') {
  return value.split(' / ').filter(reason => Object.hasOwn(feedbackReasons, reason));
}

export function CmItem({ c, foot, mgr }: { c: Comment; foot?: ReactNode; mgr?: boolean }) {
  const reasons = selectedFeedbackReasons(c.fitText);
  return (
    <div className="cm-item">
      <div className="cm-h">
        <b>{mgr && cmMine(c) ? (c.deleted ? '삭제된 코멘트' : '보낸 코멘트') : cmBy(c)}{c.skill ? ` · ${c.skill}` : ''}</b>
        <span className="small muted">
          {c.at}
          {c.editedAt ? ` · 수정됨 ${c.editedAt}` : ''}
        </span>
        {c.deleted ? <span className="tag line">삭제된 코멘트</span> : <CmTag c={c} mgr={mgr} />}
      </div>
      {!c.deleted && (c.skill && c.level === 'none' && !c.levelText
        && ((c.fit === 'good' && !c.fitText) || (c.fit === 'partial' && reasons.join(' / ') === c.fitText))
        ? <div><span className={c.fit === 'good' ? 'tag ok' : 'tag acc'}>{c.fit === 'good' ? '좋아요' : '보완 필요'}</span>
          {c.fit === 'partial' && <> {reasons.map(reason => <span className="tag line" key={reason}>{reason}</span>)}
            {c.free ? <p>{c.free}</p> : reasons.map(reason => <p key={reason}>{feedbackReasons[reason]}</p>)}</>}
        </div>
        : !c.skill && c.free && c.fit === 'none' && c.level === 'none' && !c.fitText && !c.levelText
          ? <p>{c.free}</p> : <CommentView c={c} />)}
      {!c.deleted && foot}
    </div>
  );
}

/** 코멘트 → 수정 요청 내용 */
export function commentReq(c: Comment): string {
  const lb = (list: [string, string][], v: string) => list.find((x) => x[0] === v)?.[1] || '';
  const fit = c.fit && c.fit !== 'none' ? lb(D.commentFit, c.fit) : '';
  const lv = c.level && c.level !== 'none' ? lb(D.commentLevel, c.level) : '';
  const line = (k: string, pick: string, text: string) => (text ? `${k}${pick ? `(${pick})` : ''}: ${text}` : pick ? `${k}: ${pick}` : '');
  return [line('업무 적합성', fit, c.fitText), line('수준·기간·분량', lv, c.levelText), c.free && `자유 의견: ${c.free}`].filter(Boolean).join('\n');
}

export function prepareCommentRevision(planId: string, comment: Comment): boolean {
  const record = useWs.getState().plans[planId];
  if (record?.status !== 'active' || record.rev?.running || busyPlan(record) || comment.deleted || comment.status === 'applied') return false;
  updateWs(state => {
    const plan = state.plans[planId];
    plan.rev = { ...freshRev(plan, commentReq(comment), comment.id), cmStamp: comment.stamp };
    plan.pending = null;
  });
  return true;
}

export function CommentRevisionButton({ R, c }: { R: PlanRecord; c: Comment }) {
  const go = useGo();
  if (R.status !== 'active' || c.deleted || c.fit !== 'partial' || !c.skill || c.status === 'applied') return null;

  const openExisting = () => {
    const current = useWs.getState().plans[R.id];
    if (current?.rev?.running || busyPlan(current) || current?.pending?.fromComment === c.id) {
      go(paths.revise(R.id));
      return true;
    }
    return false;
  };

  return (
    <button className="btn line sm" onClick={() => {
      if (openExisting()) return;
      confirmReviseComment(R, c.skill, () => {
        if (openExisting() || !prepareCommentRevision(R.id, c)) return;
        go(paths.revise(R.id));
        void revise(R.id);
      });
    }}>이 스킬 보완하기</button>
  );
}

export function ConfirmComments({ R, commentId }: { R: PlanRecord; commentId?: string }) {
  const [reading, setReading] = useState(false);
  const unread = newComments(R).filter(comment => !comment.deleted && (commentId === undefined || comment.id === commentId));
  if (!unread.length) return null;
  const read = async () => {
    if (reading || !unread.length) return;
    setReading(true);
    try {
      for (const comment of unread) takePlan(await plansApi.commentRead(R.id, comment.id));
      toast('코멘트를 확인했어요 · 부서장에게 ‘확인함’으로 보여요');
    } catch (err) {
      failToast(err, '확인 표시를 저장하지 못했어요');
    } finally {
      setReading(false);
    }
  };
  return (
<div className="actions" style={commentId === undefined ? { justifyContent: 'flex-end' } : { display: 'contents' }}>
        <button type="button" className="btn pri sm" style={{ flex: '0 0 auto', width: 'auto' }} disabled={reading} onClick={() => void read()}>
          {reading ? '확인 중…' : '확인했어요'}
        </button>
      </div>
  );
}

export function CommentsPage({ R }: { R: PlanRecord }) {
  const pl = R.plan;
  const priority = (c: Comment) => !c.deleted && c.skill && c.fit === 'partial' ? 0 : c.skill ? 1 : 2;
  const list = (R.comments || []).slice().reverse().sort((a, b) => priority(a) - priority(b));
  const unread = newComments(R).filter(comment => !comment.deleted);
  const n = unread.length;
  useWs((s) => s.plans[R.id]);
  if (!list.length) return <Page back={paths.roadmap(R.id)} title="받은 코멘트가 없어요" lead="이 로드맵에 부서장이 의견을 남기면 여기에 쌓여요." />;
  return (
    <Page back={paths.roadmap(R.id)} eyebrow={`${trackName(pl.opt, pl.name)} · v${pl.version} · 부서장 코멘트 ${list.length}개`} title={n ? '로드맵에 대한 의견이 왔어요' : '받은 코멘트'} lead={pl.goal}>
      <div className="stack">
        {list.map((c) => (
          <CmItem
            key={c.id}
            c={c}
            foot={<div className="actions cm-act">
              {c.skill && pl.def.learningReport && <Link className="btn line sm" to={paths.roadmap(R.id) + '#skill-' + encodeURIComponent(c.skill)}>해당 스킬 보기</Link>}
              <CommentRevisionButton R={R} c={c} />
            </div>}
          />
        ))}
      </div>
      <ConfirmComments R={R} />
    </Page>
  );
}
