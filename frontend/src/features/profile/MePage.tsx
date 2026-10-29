/* 내 정보 (API-04~08 · 5차 gp-me.js)
   인사 정보·권한(부서·부서장)은 읽기 전용(관리자 화면의 인적 데이터 엑셀로 바뀜), 본인 입력 프로필과 평정의 목표 추천 활용 동의는 직접 고친다.
   고친 값은 서버에 저장하고, 저장하면 서버가 목표 후보를 새 값으로 다시 만든다(FR-05) */
import { Fragment, useState, type ReactNode } from 'react';
import { accountApi } from '@/api/endpoints/account';
import type { User } from '@/api/types/account';
import { newIdToPath, paths } from '@/app/paths';
import { dropGoals } from '@/features/draft/goal/goalStore';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { regApplies, regGroups, regSet } from '@/shared/lib/reg';
import { cause } from '@/shared/state/ai';
import { setAt, useAt } from '@/shared/state/bind';
import { useCatalog } from '@/shared/state/catalog';
import { isSup, me as meNow, setMeView, useMe } from '@/shared/state/session';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { updateWs, useWs } from '@/shared/state/workspace';
import { BNum, BText } from '@/shared/ui/bound';
import { Icon } from '@/shared/ui/Icon';
import { Note, Page } from '@/shared/ui/parts';

/** 본인 입력 목록: [키, 이름, 입력 예시]. 입력 상태: reported 입력함 / none_confirmed 없음 확인 / unprovided 입력 안 함 */
const LISTS: [keyof Pick<User, 'tech' | 'certs' | 'learning' | 'projects'>, string, string][] = [
  ['tech', '기술 스택', '예: Python 2년'],
  ['certs', '보유 자격', '예: SQLD (2019-09-06 취득)'],
  ['learning', '교육 이력', '예: 생성형 AI 활용 과정 (2025, 16시간)'],
  ['projects', '프로젝트', '예: 업무 조회 API 개선 (백엔드 기능 구현 담당)'],
];
const None = () => <span className="muted">없음</span>;
const Val = ({ v }: { v: ReactNode }) => (v == null || v === '' ? <None /> : <>{v}</>);
const lines = (t: unknown) =>
  String(t || '')
    .split('\n')
    .map((x) => x.trim())
    .filter(Boolean)
    .slice(0, 20);
const profileEnough = (e: User | null) => !!(e && ((e.profile && (e.profile.workDesc || e.profile.expSummary)) || (e.tech || []).length || (e.projects || []).length));

function HrCard({ e }: { e: User }) {
  return (
    <div className="card">
      <div className="sec-h">
        <h2 className="st">인사 정보</h2>
        <span className="tag line">
          <Icon name="lock" />
          팀 DB · 읽기 전용
        </span>
      </div>
      <dl className="kv me-kv">
        <dt>이름</dt>
        <dd>{e.name}</dd>
        <dt>사번</dt>
        <dd className="num">
          <Val v={e.code} />
        </dd>
        <dt>직원 구분</dt>
        <dd>{[e.empGroup, e.status].filter(Boolean).join(' · ') || <None />}</dd>
        <dt>입사일</dt>
        <dd>
          <Val v={e.hireDate} />
        </dd>
        <dt>소속</dt>
        <dd>{[e.parentDept, e.dept].filter(Boolean).join(' › ') || <None />}</dd>
        <dt>직급</dt>
        <dd>
          <Val v={e.grade} />
          {e.gradeSince ? <span className="small muted"> · {e.gradeSince} 임용</span> : null}
        </dd>
        <dt>직종·직렬</dt>
        <dd>
          <Val v={e.jobFamily} />
        </dd>
        <dt>직위·보직</dt>
        <dd>
          <Val v={e.position} />
        </dd>
        <dt>직무</dt>
        <dd>
          <Val v={e.job} />
        </dd>
        <dt>주요 담당 업무</dt>
        <dd>
          <Val v={e.task} />
        </dd>
        {(e.education || []).length ? (
          <>
            <dt>학력</dt>
            <dd>
              {e.education.map((x, i) => (
                <span key={i}>
                  {i ? <br /> : null}
                  {x}
                </span>
              ))}
            </dd>
          </>
        ) : null}
        <dt>현재 근무</dt>
        <dd>{e.validFrom ? `${e.validFrom}부터${e.changeReason ? ` · ${e.changeReason}` : ''}` : <None />}</dd>
      </dl>
      <p className="small muted me-foot">인사 정보는 직접 고칠 수 없어요. 다르면 인사 담당 부서(인재경영실 · 가상)에 정정을 요청해 주세요. 담당자가 관리자 화면의 인적 데이터로 고쳐요.</p>
    </div>
  );
}

function PermCard({ e }: { e: User }) {
  const go = useGo();
  const sup = isSup(e);
  const ms = e.members || [];
  const my = e.mySupervisor;
  return (
    <div className="card">
      <div className="sec-h">
        <h2 className="st">권한·공개 범위</h2>
        <span className="tag line">
          <Icon name="lock" />
          부서 · 관리자가 정함
        </span>
      </div>
      <dl className="kv me-kv">
        <dt>서비스 역할</dt>
        <dd>
          일반 사용자 <span className="small muted">· 관리자 화면은 별도 관리자 계정으로 들어가요</span>
        </dd>
        <dt>부서장 권한</dt>
        <dd>
          {sup ? (
            <>
              있음 · {e.supGroup?.name} 부서장
              <br />
              <span className="small muted">
                볼 수 있는 직원 {ms.length}명: {ms.map((m) => m.name).join(', ')}
              </span>{' '}
              <button className="link" onClick={() => go(paths.team)}>
                소속 직원 계획 <Icon name="right" />
              </button>
            </>
          ) : e.supervisor ? (
            '부서장으로 지정됐지만 볼 수 있는 직원이 없어요'
          ) : (
            '없음'
          )}
        </dd>
        <dt>내 계획을 보는 부서장</dt>
        <dd>
          {my ? (
            <>
              {my.name}{' '}
              <span className="small muted">
                · 사번 {my.code}
                {e.planGroup ? ` · ${e.planGroup.name}` : ''}
              </span>
            </>
          ) : (
            '없음'
          )}
        </dd>
      </dl>
      {my ? (
        <p className="small muted me-foot">
          {my.name} 님은 내 소속·직급·직위, 확정 로드맵, 활동 진행 상태, 결과 보고서를 볼 수 있어요. 활동 메모·첨부, 작성 중인 로드맵, 본인 입력 정보는 부서장
          화면에 보이지 않아요.
        </p>
      ) : null}
    </div>
  );
}

function ListView({ e, k }: { e: User; k: (typeof LISTS)[number][0] }) {
  const items = e[k] || [];
  const st = e.profile && e.profile.inputStatus ? e.profile.inputStatus[k] : null;
  if (items.length)
    return (
      <ul className="plain-list me-list">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    );
  return <span className="muted">{st === 'none_confirmed' ? '없음(확인함)' : '입력 안 함'}</span>;
}

function SelfView({ e }: { e: User }) {
  const p = e.profile || {};
  return (
    <>
      {e.profile ? null : <Note>본인 입력 프로필이 아직 없어요. ‘수정’을 눌러 업무 설명이나 프로젝트 경험을 채우면 내 업무에 맞는 목표 후보를 받을 수 있어요.</Note>}
      <dl className="kv me-kv">
        <dt>업무 설명</dt>
        <dd>
          <Val v={p.workDesc} />
        </dd>
        <dt>경험 요약</dt>
        <dd>
          <Val v={p.expSummary} />
        </dd>
        <dt>개발 경험</dt>
        <dd>{p.devYears == null ? <None /> : `${p.devYears}년`}</dd>
        {LISTS.map(([k, l]) => (
          <Fragment key={k}>
            <dt>{l}</dt>
            <dd>
              <ListView e={e} k={k} />
            </dd>
          </Fragment>
        ))}
      </dl>
    </>
  );
}

function SelfForm({ err }: { err: string }) {
  const ed = useAt<Record<string, unknown>>('meEdit') || {};
  return (
    <div className="me-form">
      <div className="field">
        <label>
          업무 설명 <span className="muted small">선택 · 지금 하는 일과 AI로 줄이고 싶은 일</span>
        </label>
        <BText
          path="meEdit.workDesc"
          className="textarea sm"
          maxLength={500}
          rows={3}
          ariaLabel="업무 설명"
          placeholder="예: 사내 업무 시스템의 조회 기능을 유지보수해요. 규정 문서에서 근거를 찾는 데 시간이 오래 걸려요."
        />
      </div>
      <div className="field">
        <label>
          경험 요약 <span className="muted small">선택</span>
        </label>
        <BText path="meEdit.expSummary" className="textarea sm" maxLength={500} rows={3} ariaLabel="경험 요약" placeholder="예: 백엔드 개발 경험은 있지만 RAG는 직접 구현해 본 적이 없어요." />
      </div>
      <div className="field">
        <label>
          개발 경험 <span className="muted small">선택 · 0.5년 단위</span>
        </label>
        <div className="unit">
          <BNum path="meEdit.devYears" min={0} max={50} step={0.5} placeholder="예: 1.5" ariaLabel="개발 경험 연수" />
          <span>년</span>
        </div>
      </div>
      {LISTS.map(([k, l, ph]) => (
        <div className="field" key={k}>
          <label>
            {l} <span className="muted small">선택 · 한 줄에 하나씩</span>
          </label>
          <BText path={`meEdit.${k}`} className="textarea sm" maxLength={800} rows={3} ariaLabel={l} placeholder={ph} />
          <label className="check sm">
            <input type="checkbox" checked={!!ed[k + 'None']} onChange={(e) => setAt(`meEdit.${k}None`, e.target.checked)} />
            없어요 (없음을 확인함)
          </label>
        </div>
      ))}
      <p className="err" id="meErr" role="alert" hidden={!err}>
        {err}
      </p>
    </div>
  );
}

function EvalCard({ e }: { e: User }) {
  const ev = e.evals || [];
  const consent = async (period: string, on: boolean) => {
    try {
      await accountApi.consent(period, on);
      setMeView({ ...e, evals: ev.map((v) => (v.period === period ? { ...v, consent: on } : v)) });
      dropGoals();
      toast(on ? '이 평정을 목표 추천에 활용하도록 동의했어요' : '이 평정은 목표 추천에 쓰지 않아요');
    } catch (x) {
      failToast(x, '동의를 저장하지 못했어요');
    }
  };
  return (
    <div className="card">
      <div className="sec-h">
        <h2 className="st">근무성적평정</h2>
        <span className="tag line">본인 입력 평가</span>
      </div>
      {ev.length ? (
        <div className="list me-evals">
          {ev.map((v) => (
            <div className="li" key={v.period}>
              <div className="tx">
                <b>
                  {v.period} · {v.grade}
                  {v.score ? ` · ${v.score}` : ''}
                </b>
                <small>{v.title}</small>
              </div>
              <label className="check sm">
                <input type="checkbox" checked={v.consent} onChange={(x) => void consent(v.period, x.target.checked)} />
                목표 추천 활용 동의
              </label>
            </div>
          ))}
        </div>
      ) : (
        <p className="muted small" style={{ margin: 0 }}>
          등록된 평정이 없어요.
        </p>
      )}
      <p className="small muted me-foot">목표 추천 활용에 동의한 평정만 목표 후보 제안에 참고로 넘겨요. 등급·점수로 목표를 정하거나 문장에 쓰지 않아요. 동의는 언제든 바꿀 수 있어요.</p>
    </div>
  );
}

function UseCard({ e }: { e: User }) {
  const go = useGo();
  const lastNew = useWs((s) => s.lastNew);
  useCatalog((s) => s.regSets);
  const set = regSet();
  return (
    <div className="card flat">
      <h2 className="st">이 정보가 쓰이는 곳</h2>
      <div className="stack">
        <div className="row top">
          <Icon name="spark" />
          <span>
            <b>목표 후보 제안</b> · 로그인 직후 최초 한 번, 또는 업무·프로젝트 등 추천에 쓰는 정보가 바뀌면 후보 3개를 미리 준비해요. 같은 정보로 다시 로그인하면 저장된 후보를 사용해요.{' '}
            <button className="link" onClick={() => go(newIdToPath(lastNew))}>
              새 로드맵 작성 <Icon name="right" />
            </button>
          </span>
        </div>
        <div className="row top">
          <Icon name="scale" />
          <span>
            <b>사내 생활 도우미·지원 조건 확인</b> · 규정 에이전트가 직원 구분·직급을 봐요.{' '}
            {regApplies() && set
              ? `${e.empGroup || ''} 직원이라 등록된 ${set.label}(${set.regs
                  .filter((r) => !r.overseas)
                  .map((r) => r.name)
                  .slice(0, 3)
                  .join('·')} 등)에서 근거를 찾아요. 국외근무 규정은 국외근무를 물을 때만 봐요.`
              : `${e.empGroup ? `${e.empGroup} 직원에게 맞는 규정 묶음이 아직 등록되지 않아` : '직원 구분이 없어'} 규정 질문에는 ‘적용 대상 아님’으로 안내해요. 등록된 규정 묶음: ${regGroups().join('·') || '없음'}.`}
          </span>
        </div>
      </div>
    </div>
  );
}

export function MePage() {
  const e = useMe();
  const ed = useWs((s) => s.meEdit);
  const [err, setErr] = useState('');
  if (!e) return null;
  const startEdit = () => {
    const p = e.profile || {};
    const st = p.inputStatus || {};
    const v: Record<string, unknown> = { workDesc: p.workDesc || '', expSummary: p.expSummary || '', devYears: p.devYears == null ? '' : p.devYears };
    LISTS.forEach(([k]) => {
      v[k] = (e[k] || []).join('\n');
      v[k + 'None'] = st[k] === 'none_confirmed';
    });
    setErr('');
    updateWs((s) => void (s.meEdit = v));
  };
  const save = async () => {
    if (!ed) return;
    const wd = String(ed.workDesc || '').trim();
    const ex = String(ed.expSummary || '').trim();
    const yrs = ed.devYears === '' || ed.devYears == null ? null : Number(ed.devYears);
    if (yrs != null && !(yrs >= 0 && yrs <= 50)) return setErr('개발 경험은 0~50년 사이로 적거나 비워 주세요.');
    const ls = Object.fromEntries(LISTS.map(([k]) => [k, lines(ed[k])]));
    try {
      const r = await accountApi.saveSelf({
        workDesc: wd,
        expSummary: ex,
        devYears: yrs,
        noneConfirmed: Object.fromEntries(LISTS.map(([k]) => [k, !!ed[k + 'None']])),
        ...ls,
      });
      if (r && r.view) setMeView(r.view);
      dropGoals();
    } catch (x) {
      return setErr(cause(x).user);
    }
    updateWs((s) => void (s.meEdit = null));
    toast(profileEnough(meNow()) ? '본인 입력 정보를 저장했어요 · 추천 정보가 바뀌면 목표 후보를 새로 준비해요' : '본인 입력 정보를 저장했어요');
  };
  const revert = () =>
    openSheet({
      title: '처음 값으로 되돌릴까요?',
      body: () => (
        <p style={{ marginTop: 0 }}>
          직접 고친 본인 입력 정보(업무 설명·경험·기술 스택·자격·교육·프로젝트)를 지우고 팀 DB에 처음 들어온 값으로 되돌려요. 평정의 목표 추천 활용 동의는 그대로예요.
        </p>
      ),
      foot: () => (
        <>
          <button className="btn line" onClick={closeSheet}>
            취소
          </button>
          <button
            className="btn pri"
            onClick={async () => {
              closeSheet();
              try {
                const r = await accountApi.revertSelf();
                if (r && r.view) setMeView(r.view);
                dropGoals();
                toast('처음 값으로 되돌렸어요 · 목표 후보도 다시 만들어요');
              } catch (x) {
                failToast(x, '되돌리지 못했어요');
              }
            }}
          >
            되돌리기
          </button>
        </>
      ),
    });
  return (
    <Page
      eyebrow="내 정보"
      title={`${e.name} 님의 정보`}
      lead="인사 정보와 권한은 팀 DB의 인사 데이터에서 가져와 고칠 수 없어요. 본인 입력 정보와 평정의 목표 추천 활용 동의는 직접 고칠 수 있고, 목표 후보 제안에 쓰여요."
    >
      <div className="me-page">
        <HrCard e={e} />
        <div className="card">
          <div className="sec-h">
            <h2 className="st">본인 입력 정보</h2>
            <span className={`tag ${e.edited ? 'acc' : 'line'}`}>{e.edited ? `직접 고침${e.editedAt ? ` · ${e.editedAt}` : ''}` : '처음 값'}</span>
            {ed ? null : (
              <button className="btn line sm me-ed" onClick={startEdit}>
                <Icon name="edit" />
                수정
              </button>
            )}
          </div>
          {ed ? <SelfForm err={err} /> : <SelfView e={e} />}
          {ed ? (
            <div className="actions me-act">
              <button className="btn pri" onClick={() => void save()}>
                저장
              </button>
              <button className="btn line" onClick={() => updateWs((s) => void (s.meEdit = null))}>
                취소
              </button>
            </div>
          ) : null}
          <p className="small muted me-foot">
            고친 내용은 팀 DB의 직원 입력 정보에 저장되고, 처음 들어온 값은 되돌릴 수 있게 따로 남아요.
            {e.edited && !ed ? (
              <>
                {' '}
                <button className="link quiet" onClick={revert}>
                  처음 값으로 되돌리기
                </button>
              </>
            ) : null}
          </p>
        </div>
        <EvalCard e={e} />
        <PermCard e={e} />
        <UseCard e={e} />
      </div>
    </Page>
  );
}

