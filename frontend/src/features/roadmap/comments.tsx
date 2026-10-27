/* 부서장 코멘트 (10/14 · 5차 scr.comment · P.commentView·cmTag·cmItem·commentReq)
   쌓이고, 상태(새·확인함·vN에 반영)가 직원·부서장 화면에 같이 보인다. 답글은 없다 */
import type { ReactNode } from 'react';
import { plansApi } from '@/api/endpoints/plans';
import type { Comment, PlanRecord } from '@/api/types/plan';
import { paths } from '@/app/paths';
import { D } from '@/shared/constants/data';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { me } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { newComments, updateWs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Page } from '@/shared/ui/parts';
import { cmBy } from './parts';
import { freshRev, takePlan } from './planActions';

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
    <span className="tag ok">v{c.appliedVersion || ''}에 반영</span>
  ) : c.status === 'read' ? (
    <span className="tag line">확인함</span>
  ) : (
    <span className="tag acc">{mgr ? '확인 전' : '새 코멘트'}</span>
  );

export const cmMine = (c: Comment): boolean => !!(c.byCode && c.byCode === me()?.code);

export function CmItem({ c, foot, mgr }: { c: Comment; foot?: ReactNode; mgr?: boolean }) {
  return (
    <div className="cm-item">
      <div className="cm-h">
        <b>{mgr && cmMine(c) ? '보낸 코멘트' : cmBy(c)}</b>
        <span className="small muted">
          {c.at}
          {c.editedAt ? ` · 수정됨 ${c.editedAt}` : ''}
        </span>
        <CmTag c={c} mgr={mgr} />
      </div>
      <CommentView c={c} />
      {foot}
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

export function CommentsPage({ R }: { R: PlanRecord }) {
  const go = useGo();
  const pl = R.plan;
  const list = (R.comments || []).slice().reverse();
  const live = R.status === 'active';
  const n = newComments(R).length;
  useWs((s) => s.plans[R.id]);
  if (!list.length) return <Page back={paths.roadmap(R.id)} title="받은 코멘트가 없어요" lead="이 로드맵에 부서장이 의견을 남기면 여기에 쌓여요." />;
  const apply = (c: Comment) => {
    if (R.status !== 'active') return;
    updateWs((s) => {
      const x = s.plans[R.id];
      x.rev = { ...freshRev(x, commentReq(c), c.id), cmStamp: c.stamp };
      x.pending = null;
    });
    go(paths.revise(R.id));
  };
  const read = async (c: Comment) => {
    try {
      takePlan(await plansApi.commentRead(R.id, c.id));
      toast('코멘트를 확인했어요 · 부서장에게 ‘확인함’으로 보여요');
    } catch (err) {
      failToast(err, '확인 표시를 저장하지 못했어요');
    }
  };
  return (
    <Page back={paths.roadmap(R.id)} eyebrow={`${pl.name} · v${pl.version} · 부서장 코멘트 ${list.length}개`} title={n ? '로드맵에 대한 의견이 왔어요' : '받은 코멘트'} lead={pl.goal}>
      <div className="stack">
        {list.map((c) => (
          <CmItem
            key={c.id}
            c={c}
            foot={
              live && c.status !== 'applied' ? (
                <div className="actions cm-act">
                  <button className="btn pri sm" onClick={() => apply(c)}>
                    이 의견으로 수정안 받기
                  </button>
                  {c.status === 'new' ? (
                    <button className="btn line sm" onClick={() => void read(c)}>
                      확인했어요
                    </button>
                  ) : null}
                </div>
              ) : null
            }
          />
        ))}
      </div>
      <div className="callout soft" style={{ marginTop: 16 }}>
        <Icon name="info" />
        <div>
          코멘트만으로 로드맵이 바뀌지는 않아요. ‘이 의견으로 수정안 받기’를 누르면 코멘트를 채운 수정 요청 화면이 열려요. 반영할 부분만 남겨 수정안을 만들고, 내가 확정해야
          로드맵이 바뀌어요. 확인했는지와 몇 번째 버전에 반영했는지는 부서장에게도 보여요.
        </div>
      </div>
    </Page>
  );
}
