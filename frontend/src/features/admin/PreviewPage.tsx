/* 미리보기 · 반영 (5차 gp-admin.js preview) — 올린 파일과 지금 데이터를 비교한 결과(행마다 추가·변경·삭제·오류).
   오류가 하나라도 있으면 반영할 수 없다. 화면에서 고친 기록(source form)도 같은 화면으로 본다 */
import { useEffect } from 'react';
import { useParams } from 'react-router';
import { adminApi } from '@/api/endpoints/admin';
import { ApiError } from '@/api/client';
import type { UploadView } from '@/api/types/admin';
import { queryClient } from '@/app/queryClient';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { toast } from '@/shared/state/ui';
import { Icon } from '@/shared/ui/Icon';
import { Loading, Note, Page } from '@/shared/ui/parts';
import { adminKeys, refreshAdmin, useUpload } from './adminData';
import { adm, setAdm, setChoice, useAdmin } from './adminStore';
import { DS, isDataset } from './datasets';
import { FailBox, RowCard } from './parts';

const APPLIED_ACT: Record<string, string> = { add: '추가', update: '변경', delete: '삭제', hidden: '목록에서 뺌' };
/** 이 오류면 미리보기가 바뀌었으니 다시 받는다 */
const STALE = ['STALE_PREVIEW', 'NOW_INVALID', 'PREVIEW_EXPIRED', 'UPLOAD_DONE'];

function AppliedNote({ p }: { p: UploadView }) {
  const ap = p.applied || {};
  const sheetsDone = Object.entries(ap)
    .filter(([, v]) => v && typeof v === 'object' && !Array.isArray(v) && Object.values(v as object).some(Boolean))
    .map(
      ([k, v]) =>
        `${k} ${Object.entries(v as Record<string, number>)
          .filter(([, n]) => n)
          .map(([a, n]) => `${APPLIED_ACT[a] || a} ${n}`)
          .join(' · ')}`,
    );
  return (
    <Note>
      반영 결과 · {sheetsDone.join(' / ') || '바뀐 행 없음'}
      {ap.transfers ? ` · 인사이동·권한 이력 ${ap.transfers}건` : ''}
      {p.goalCount ? ` · 목표 후보를 다시 만드는 직원 ${p.goalCount}명` : ''}
    </Note>
  );
}

async function applyUpload(id: string): Promise<void> {
  const p = queryClient.getQueryData<UploadView>(adminKeys.upload(id));
  if (!p || !p.canApply || adm().saving) return;
  setAdm((s) => void (s.saving = true));
  try {
    const r = await adminApi.apply(id, adm().choice.applyGoal === 'mock' ? 'mock' : null);
    queryClient.setQueryData<UploadView>(adminKeys.upload(id), { ...p, status: 'applied', canApply: false, applied: r.applied, goalCount: r.goalCount });
    refreshAdmin();
    window.scrollTo(0, 0);
    toast('반영했어요');
  } catch (err) {
    failToast(err, '반영하지 못했어요');
    if (err instanceof ApiError && STALE.includes(err.code || '')) void queryClient.invalidateQueries({ queryKey: adminKeys.upload(id) });
  } finally {
    setAdm((s) => void (s.saving = false));
  }
}

function ApplyFoot({ p }: { p: UploadView }) {
  const goal = useAdmin((s) => s.choice.applyGoal);
  const saving = useAdmin((s) => s.saving);
  const go = useGo();
  const discard = async () => {
    try {
      await adminApi.discard(p.uploadId);
    } catch {
      /* 이미 끝난 미리보기면 그대로 */
    }
    refreshAdmin(p.dataset);
    void queryClient.invalidateQueries({ queryKey: adminKeys.upload(p.uploadId) });
    go(isDataset(p.dataset) ? paths.adminData(p.dataset) : paths.admin);
    toast('미리보기를 취소했어요. 아무것도 바뀌지 않았어요');
  };
  return (
    <>
      {p.dataset === 'hr' ? (
        <div className="stack" style={{ marginBottom: 10 }}>
          <span className="small muted">반영한 뒤 바뀐 직원의 목표 후보를 다시 만들 때</span>
          <label className="radio">
            <input type="radio" name="admApplyGoal" value="mock" checked={goal === 'mock'} onChange={() => setChoice('applyGoal', 'mock')} />
            시연용 가데이터로 만들기
          </label>
          <label className="radio">
            <input type="radio" name="admApplyGoal" value="employee" checked={goal === 'employee'} onChange={() => setChoice('applyGoal', 'employee')} />각 직원이 고른 AI 모드로
            만들기(설정 안 된 직원은 실패로 남아요)
          </label>
        </div>
      ) : null}
      <div className="actions" style={{ marginTop: 0 }}>
        <button className="btn pri" disabled={!p.canApply || saving} onClick={() => void applyUpload(p.uploadId)}>
          {saving ? (
            <>
              <span className="sp" />
              반영하는 중…
            </>
          ) : (
            <>
              <Icon name="check" />
              반영하기
            </>
          )}
        </button>
        <button className="btn line" onClick={() => void discard()}>
          취소
        </button>
      </div>
      {p.canApply ? null : (
        <p className="small muted" style={{ margin: '6px 0 0' }}>
          {p.errorRows ? `오류가 있는 행 ${p.errorRows}개를 고친 파일을 다시 올려 주세요.` : '바뀌는 행이 없어 반영할 것이 없어요.'}
        </p>
      )}
    </>
  );
}

function Preview({ id }: { id: string }) {
  const go = useGo();
  const q = useUpload(id);
  const filter = useAdmin((s) => s.filter);
  useEffect(() => setChoice('applyGoal', 'mock'), [id]);
  if (q.isPending)
    return (
      <Page back={paths.adminHistory} title="미리보기">
        <Loading text="불러오는 중…" />
      </Page>
    );
  if (q.isError)
    return (
      <Page back={paths.adminHistory} title="미리보기">
        <FailBox err={q.error} what="미리보기를 불러오지 못했어요" />
      </Page>
    );
  const p = q.data;
  const D = isDataset(p.dataset) ? DS[p.dataset] : { title: p.dataset };
  const rows = p.rows || [];
  const applied = p.status === 'applied';
  const form = p.source === 'form';
  const cnt = (a: string) => rows.filter((r) => r.action === a).length;
  const shown = filter === 'all' ? rows : rows.filter((r) => r.action === filter);
  const sums = p.summary || {};
  const title = form
    ? '화면에서 저장했어요'
    : applied
      ? '반영했어요'
      : p.status === 'rejected'
        ? '취소한 미리보기예요'
        : p.status === 'expired'
          ? '시간이 지난 미리보기예요'
          : p.errorRows
            ? '오류를 고쳐야 반영할 수 있어요'
            : p.changeRows
              ? '이 내용으로 반영할까요?'
              : '바뀐 내용이 없어요';
  const tabs = (
    [
      ['all', '전체', rows.length],
      ['error', '오류', cnt('error')],
      ['add', '추가', cnt('add')],
      ['update', '변경', cnt('update')],
      ['delete', '삭제', cnt('delete')],
      ['skip', '건너뜀', cnt('skip')],
    ] as const
  ).filter(([k, , n]) => k === 'all' || n);
  return (
    <Page
      back={isDataset(p.dataset) ? paths.adminData(p.dataset) : paths.admin}
      eyebrow={`${D.title} · ${p.fileName}${p.createdAt ? ` · ${p.createdAt}` : ''}`}
      title={title}
      lead={form ? '관리자 화면에서 고쳐 팀 DB에 저장한 내용이에요.' : applied ? '팀 DB에 반영했어요. 아래는 반영한 행이에요.' : '파일과 지금 데이터를 비교했어요. 아직 아무것도 바뀌지 않았어요. 미리보기는 30분 동안만 반영할 수 있어요.'}
    >
      {applied ? <AppliedNote p={p} /> : null}
      <div className="card">
        <table className="adm-sum">
          <thead>
            <tr>
              <th>시트</th>
              <th>추가</th>
              <th>변경</th>
              <th>삭제</th>
              <th>그대로</th>
              <th>오류</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(sums).map(([s, c]) => (
              <tr key={s}>
                <td>{s}</td>
                <td>{c.add}</td>
                <td>{c.update}</td>
                <td>{c.delete}</td>
                <td>{c.same}</td>
                <td className={c.error ? 'err' : ''}>{c.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(p.notes || []).map((n, i) => (
          <p className="small muted" style={{ margin: '8px 0 0' }} key={i}>
            <Icon name="info" /> {n}
          </p>
        ))}
      </div>
      <div className="adm-tabs">
        {tabs.map(([k, l, n]) => (
          <button key={k} className={`chip ${filter === k ? 'on' : ''}`} onClick={() => setAdm((s) => void (s.filter = k))}>
            {l} {n}
          </button>
        ))}
      </div>
      <div className="adm-rows">
        {shown.length ? shown.slice(0, 300).map((r, i) => <RowCard key={i} r={r} form={form} />) : <p className="muted small">보여 줄 행이 없어요.</p>}
        {shown.length > 300 ? <p className="small muted">처음 300행만 보여요(전체 {shown.length}행).</p> : null}
      </div>
      <div className="adm-foot">
        {p.status !== 'previewed' ? (
          <button className="btn line" onClick={() => go(isDataset(p.dataset) ? paths.adminData(p.dataset) : paths.admin)}>
            {D.title}로
          </button>
        ) : (
          <ApplyFoot p={p} />
        )}
      </div>
    </Page>
  );
}

export function PreviewPage() {
  const { id } = useParams();
  return <Preview key={id} id={String(id)} />;
}
