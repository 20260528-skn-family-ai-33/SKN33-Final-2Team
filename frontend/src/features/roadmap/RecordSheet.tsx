/* 실행 기록 창 (5차 rec-open·rec-save · P.recBody·recRes)
   진행 상태는 이 창에서만 바꾼다(홈·내 로드맵 활동 줄은 보여 주기만 · 10/23). 저장하기를 눌러야 반영된다.
   자료 상자(10/23 사용자 결정): 그림을 크게, 버튼 두 개 — '원본 열기'(새 탭) + '자료 정보'(앱 안 자료 상세) */
import { resourceSource } from '@/shared/lib/resourceSource';
import { plansApi } from '@/api/endpoints/plans';
import type { Activity } from '@/api/types/plan';
import type { Resource } from '@/api/types/catalog';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { hrs } from '@/shared/lib/format';
import { st, stageName } from '@/shared/lib/plan';
import { setAt, useAt } from '@/shared/state/bind';
import { resOf } from '@/shared/state/catalog';
import { me } from '@/shared/state/session';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { updateWs, useWs, ws } from '@/shared/state/workspace';
import { BText } from '@/shared/ui/bound';
import { Icon } from '@/shared/ui/Icon';
import { Note, Thumb } from '@/shared/ui/parts';
import { saveProgress } from './planActions';

const STATUS: [string, string][] = [
  ['doing', '진행 중'],
  ['done', '완료'],
];
let recFile: File | null = null;

function RecRes({ a, r }: { a: Activity; r: Resource | null }) {
  const go = useGo();
  const url = r && /^https?:\/\//i.test(r.url || '') ? (r.url as string) : '';
  return (
    <div className="rec-res">
      <div className="rec-res-h">
        <Thumb r={r} size="md" />
        <div className="tx">
          <b>{r ? r.title : a.title}</b>
          {r ? (
            <small>
              {r.kind} · {resourceSource(r)}
              {r.real ? '' : ' · 가상 자료'}
            </small>
          ) : null}
        </div>
      </div>
      <div className="rec-res-b">
        {url ? (
          <a className="btn line" href={url} target="_blank" rel="noopener noreferrer">
            원본 열기
            <Icon name="out" />
          </a>
        ) : null}
        <button className="btn line" onClick={() => go(paths.resource(a.res as string))}>
          자료 정보
        </button>
      </div>
    </div>
  );
}

function RecBody({ pid, id }: { pid: string; id: string }) {
  const R = useWs((s) => s.plans[pid]);
  const status = useAt<string>('tmp.status');
  const a = R?.plan.acts.find((x) => x.id === id);
  if (!R || !a) return null;
  const pr = R.progress[a.id] || {};
  const r = a.res ? resOf(a.res) : null;
  const sup = me()?.mySupervisor;
  return (
    <>
      <p className="small muted">
        {a.stage}단계 {stageName(a.stage)} · {a.wFrom === a.wTo ? a.wFrom : a.wFrom + '~' + a.wTo}주차 · {hrs(a.hours)}
      </p>
      <p style={{ fontWeight: 650, fontSize: 17, margin: '4px 0 14px' }}>{a.title}</p>
      {a.task ? (
        <div className="callout soft">
          <Icon name="flag" />
          <div>
            <b>직접 수행 과제</b>
            <br />
            {a.how}
          </div>
        </div>
      ) : (
        <RecRes a={a} r={r} />
      )}
      <div className="field rec-st">
        <span className="flabel" id="recStL">
          진행 상태
        </span>
        <div className="mini-seg" role="radiogroup" aria-labelledby="recStL">
          {STATUS.map(([v, l]) => (
            <label key={v}>
              <input type="radio" name="recst" value={v} checked={status === v} onChange={() => setAt('tmp.status', v)} />
              {l}
            </label>
          ))}
        </div>
      </div>
      <div className="field">
        <label>
          메모 <span className="muted small">선택</span>
        </label>
        <BText path="tmp.memo" className="textarea sm" placeholder="한 일, 막힌 점, 다음에 할 일" />
      </div>
      <div className="field">
        <label>
          결과물·수료증 <span className="muted small">선택 · 서버에 보관(배포 때는 파일 저장소)</span>
        </label>
        {pr.file ? (
          <p className="small">
            <Icon name="file" /> {pr.file.name}
          </p>
        ) : null}
        <input className="input" type="file" id="recFile" onChange={(e) => (recFile = (e.target.files && e.target.files[0]) || null)} />
      </div>
      <Note>
        메모·첨부는 나만 봐요.{sup ? ` 완료 여부는 부서장 ${sup.name} 님에게 진행 상태로 보여요.` : ''} 자료를 내지 않았다고 하지 않은 것으로 보지 않아요.
      </Note>
    </>
  );
}

async function recSave(): Promise<void> {
  const t = ws().tmp;
  if (!t) return;
  const body: Record<string, unknown> = { status: t.status, memo: t.memo || '' };
  try {
    if (recFile) {
      const up = await plansApi.attach(t.pid, t.id, recFile);
      body.file = { fileId: up.fileId, name: up.name, size: up.size };
    }
  } catch (err) {
    failToast(err, '파일을 올리지 못했어요');
    return;
  }
  const ok = await saveProgress(t.pid, t.id, body);
  if (!ok) return;
  updateWs((s) => void (s.tmp = null));
  recFile = null;
  closeSheet();
  toast('실행 기록을 저장했어요');
}

function RecFoot() {
  const status = useAt<string>('tmp.status');
  return (
    <button className="btn pri" disabled={!status} onClick={() => void recSave()}>
      저장하기
    </button>
  );
}

export function openRecord(pid: string, id: string): void {
  const R = ws().plans[pid];
  const a = R && R.plan.acts.find((x) => x.id === id);
  if (!R || !a) return;
  const pr = R.progress[id] || {};
  updateWs((s) => void (s.tmp = { pid, id, status: st(R.progress, id), memo: pr.memo || '' }));
  recFile = null;
  openSheet({ title: '실행 기록', sub: R.plan.goal, body: () => <RecBody pid={pid} id={id} />, foot: () => <RecFoot /> });
}
