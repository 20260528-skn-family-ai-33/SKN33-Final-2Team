/* 지원 조건 (10/14 · 5차 P.supCell·supNote·revSupView): 3안이 정해진 뒤 서버가 규정 에이전트를 한 번 불러 안별로 확인. 다시 만든 안은 그 안만 확인.
   근거는 내 직원 구분의 등록 규정 조항만(팀 DB 규정 · 일반직 규정 묶음 등). 실패하면 '다시 확인'을 눌러야만 다시 묻는다 */
import { draftsApi } from '@/api/endpoints/drafts';
import { plansApi } from '@/api/endpoints/plans';
import type { OptionDef } from '@/api/types/draft';
import type { PendingRevision } from '@/api/types/plan';
import { openAssistant } from '@/features/assistant/assistantStore';
import { failToast } from '@/shared/lib/fail';
import { article, artName, missLabel, regApplies, regGroups, regSet } from '@/shared/lib/reg';
import { cause, userText } from '@/shared/state/ai';
import { useCatalog } from '@/shared/state/catalog';
import { me } from '@/shared/state/session';
import { updateWs, ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Note, OpsBox } from '@/shared/ui/parts';
import { D } from '@/shared/constants/data';
import { draftCall } from '../draftSync';

export const SUP_LV: Record<string, [string, string]> = {
  ok: ['근거 확인', 'acc'],
  unclear: ['일부만 확인', 'warn'],
  missing: ['관련 자료 미확보', 'warn'],
  scope: ['적용 대상 아님', 'warn'],
};

/** 다시 만든 버전을 보고 있으면 options[관점] 을 그 버전으로 맞춘다 */
export function syncGenCur(): void {
  updateWs((s) => {
    const g = s.draft.gen;
    if (g && g.hist)
      Object.keys(g.hist).forEach((pid) => {
        const v = g.hist?.[pid][(g.cur || {})[pid] || 0];
        if (v) g.options[pid] = v;
      });
  });
}

export async function supRetry(pid: string): Promise<void> {
  if (!ws().draft.gen) return;
  syncGenCur();
  updateWs((s) => {
    const g = s.draft.gen;
    if (!g) return;
    D.optionOrder.filter((id) => g.options[id] && (pid === 'all' || id === pid)).forEach((id) => delete g.options[id].supportFail);
  });
  await draftCall('지원 조건을 다시 확인하지 못했어요', (id) => draftsApi.supportRetry(id, pid === 'all' ? null : pid), { soft: true });
}

/** 안 하나의 지원 조건: 수준 태그 · 요약 · 근거 조항 · 미등록 규정 (근거 조항이 없으면 '확인 필요'로만 보여 준다) */
export function SupCell({ o }: { o: OptionDef | null | undefined }) {
  useCatalog((s) => s.articles);
  if (!o) return null;
  if (o.supportFail) {
    const c = cause(o.supportFail.cause);
    return (
      <>
        <span className="tag fail">확인 실패</span> <span className="small muted">{c.user || userText(c.kind)}. 지원 조건은 ‘확인 필요’로 둬요.</span>{' '}
        <button className="link" onClick={() => void supRetry(o.id)}>
          <Icon name="retry" />
          다시 확인
        </button>
      </>
    );
  }
  if (!o.support)
    return (
      <>
        <span className="tag">확인 중</span> <span className="small muted">규정 에이전트가 확인하고 있어요</span>
      </>
    );
  const s = o.support;
  const [t, c] = SUP_LV[s.level] || SUP_LV.missing;
  const basis = (s.basis || [])
    .map((id) => article(id))
    .filter(Boolean)
    .map((a) => artName(a!))
    .join(', ');
  return (
    <>
      <span className={`tag ${c}`}>{t}</span> <span className="small">{s.summary}</span>
      {basis ? <span className="small muted sup-l">근거: {basis}</span> : null}
      {(s.missing || []).length ? <span className="small muted sup-l">등록되지 않은 기준: {s.missing.map((m) => missLabel(m)).join(', ')}</span> : null}
    </>
  );
}

export function SupNote() {
  useCatalog((s) => s.regSets);
  const grp = me()?.empGroup || '';
  if (!regApplies())
    return (
      <Note>
        등록된 규정은 {regGroups().join('·')} 대상이라 {grp} 직원의 지원 조건은 확인하지 않았어요. {grp} 대상 규정이 등록되면 규정 에이전트가 확인해요. 지원금은 예상
        비용에서 빼지 않았어요.
      </Note>
    );
  return (
    <Note>
      지원 조건은 규정 에이전트가 등록된 {regSet()?.label} 조항만 근거로 확인해요. 조항에 없는 지원 여부·금액은 짐작하지 않고 ‘확인 필요’로 둬요. 지원금은 예상 비용에서
      빼지 않았어요.{' '}
      <button className="link" onClick={() => openAssistant('교육비 지원을 받을 수 있나요?')}>
        <Icon name="chat" />
        사내 생활 도우미에게 묻기
      </button>
    </Note>
  );
}

/* 확정 뒤 수정안의 지원 조건 (설계서 v1.7 SCR-RM-06 · 10/20): 자료·자격·기간·비용이 바뀐 수정안만 서버가 규정 에이전트로 다시 확인한다.
   확인 전에는 '확인 필요'로 보여 주고, 실패하면 '다시 확인'을 눌러야만 다시 묻는다. 확정하면 그 버전에 결과를 남긴다 */
export function RevSupView({ pd, pid, onPulled }: { pd: PendingRevision; pid: string; onPulled: () => Promise<void> }) {
  const o = pd.to.def;
  let cell: React.ReactNode;
  if (o.support)
    cell = (
      <>
        <SupCell o={o} />
        {pd.supSame ? (
          <span className="small muted sup-l">자료·자격·기간·비용이 그대로라 이전 버전의 확인 결과를 그대로 써요.</span>
        ) : (
          <span className="small muted sup-l">자료·자격·기간·비용이 바뀌어 규정 에이전트가 이 버전을 다시 확인했어요.</span>
        )}
      </>
    );
  else if (pd.supFail) {
    const c = cause(pd.supFail.cause);
    cell = (
      <>
        <span className="tag warn">확인 필요</span> <span className="small muted">{c.user || userText(c.kind)}. 확인하지 못한 동안은 ‘확인 필요’로 둬요.</span>{' '}
        <button
          className="link"
          onClick={async () => {
            updateWs((s) => {
              const R = s.plans[pid];
              if (R && R.pending) delete R.pending.supFail;
            });
            try {
              await plansApi.reviseSupportRetry(pid);
            } catch (err) {
              failToast(err, '지원 조건을 다시 확인하지 못했어요');
            }
            await onPulled();
          }}
        >
          <Icon name="retry" />
          다시 확인
        </button>
        <OpsBox items={[['', c]]} cls="sm" />
      </>
    );
  } else
    cell = (
      <>
        <span className="tag warn">확인 필요</span> <span className="small muted">자료·자격·기간·비용이 바뀌어 규정 에이전트가 이 버전의 지원 조건을 다시 확인하고 있어요.</span>
      </>
    );
  return (
    <div className="card flat rv-sup">
      <dl className="kv">
        <dt>지원 조건 · v{(pd.from.version || 0) + 1}</dt>
        <dd>{cell}</dd>
      </dl>
    </div>
  );
}
