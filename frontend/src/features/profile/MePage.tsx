/* 내 정보 (API-04~08 · 5차 gp-me.js)
   인사 정보·권한(부서·부서장)은 읽기 전용(관리자 화면의 인적 데이터 엑셀로 바뀜), 본인 입력 프로필과 평정의 목표 추천 활용 동의는 직접 고친다.
   고친 값은 서버에 저장하고, 저장하면 서버가 목표 후보를 새 값으로 다시 만든다(FR-05) */
import { Fragment, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { catalogApi } from '@/api/endpoints/catalog';
import { accountApi } from '@/api/endpoints/account';
import type { User } from '@/api/types/account';
import { newIdToPath, paths } from '@/app/paths';
import { dropGoals } from '@/features/draft/goal/goalStore';
import { MySkillMap } from '@/features/skillmap/MySkillMap';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { cause } from '@/shared/state/ai';
import { setAt, useAt } from '@/shared/state/bind';
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
    .filter(Boolean);
const profileEnough = (e: User | null) => !!(e && ((e.profile && (e.profile.workDesc || e.profile.expSummary)) || (e.tech || []).length || (e.projects || []).length));

function HrCard({ e }: { e: User }) {
  return (
    <details className="card handoff">
      <summary className="sec-h"><Icon name="right" />
        <h2 className="st">인사 정보</h2>
      </summary>
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
      <p className="small muted me-foot">인사 정보는 직접 고칠 수 없어요. 다르면 인사 담당 부서(인재경영실)에 정정을 요청해 주세요. 담당자가 관리자 화면의 인적 데이터로 고쳐요.</p>
    </details>
  );
}

function PermCard({ e }: { e: User }) {
  const go = useGo();
  const sup = isSup(e);
  const ms = e.members || [];
  const my = e.mySupervisor;
  return (
    <details className="card handoff">
      <summary className="sec-h"><Icon name="right" />
        <h2 className="st">권한·공개 범위</h2>
      </summary>
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
    </details>
  );
}

function ListView({ e, k }: { e: User; k: (typeof LISTS)[number][0] }) {
  const items = e[k] || [];
  if (items.length)
    return (
      <ul className="plain-list me-list">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    );
  return <span className="muted">없음</span>;
}

function SelfView({ e }: { e: User }) {
  const p = e.profile || {};
  return <>
    {e.profile ? null : <Note>본인 입력 프로필이 아직 없어요. ‘수정’을 눌러 업무 설명이나 프로젝트 경험을 채우면 내 업무에 맞는 목표 후보를 받을 수 있어요.</Note>}
    <h3 style={{ fontSize: 14, margin: '0 0 8px' }}>권장 <span className="small muted" style={{ fontWeight: 400 }}>업무와 프로젝트를 적으면 목표·학습 추천에 도움이 돼요.</span></h3>
    <dl className="kv me-kv"><dt>업무 설명</dt><dd><Val v={p.workDesc} /></dd></dl>
    <h3 style={{ fontSize: 14, margin: '20px 0 8px' }}>선택 사항</h3>
    <dl className="kv me-kv"><dt>경험 요약</dt><dd><Val v={p.expSummary} /></dd><dt>개발 경험</dt><dd>{p.devYears == null ? <None /> : `${p.devYears}년`}</dd>
      {LISTS.filter(([key]) => key !== 'projects').map(([k, label]) => <Fragment key={k}><dt>{label}</dt><dd>{k === 'certs' ? (
        <details className="handoff">
          <summary>보유 자격증 {e.certs?.length || 0}개</summary>
          <ListView e={e} k={k} />
        </details>
      ) : <ListView e={e} k={k} />}</dd></Fragment>)}
    </dl>
  </>;
}

function SelfForm({ err }: { err: string }) {
  const ed = useAt<Record<string, unknown>>('meEdit') || {};
  const skills = useQuery({ queryKey: ['skills-map'], queryFn: catalogApi.skillMap, staleTime: Infinity });
  const selected = lines(ed.tech);
  const [certificateInput, setCertificateInput] = useState('');
  const certificates = lines(ed.certs);
  const certificate = certificateInput.trim();
  const canAddCertificate = !!certificate && !certificates.includes(certificate) && certificates.length < 20;
  const [showAllSkills, setShowAllSkills] = useState(false);
  const catalogSkills = skills.data?.skills.map(skill => skill.name) || [];
  const skillNames = [...new Set([...catalogSkills, ...selected])];
  const visibleSkills = showAllSkills ? skillNames : skillNames.slice(0, 5);
  const renderListField = ([k, label, placeholder]: (typeof LISTS)[number]) => (
    <div className="field" key={k}>
      <label>{label}</label>
      <BText path={`meEdit.${k}`} className="textarea sm" maxLength={800} rows={3} ariaLabel={label} placeholder={placeholder} />
    </div>
  );
  return (
    <div className="me-form">
      <div className="field">
        <label>업무 설명</label>
        <BText path="meEdit.workDesc" className="textarea sm" maxLength={500} rows={3} ariaLabel="업무 설명" />
      </div>
      <div className="field">
        <label>경험 요약</label>
        <BText path="meEdit.expSummary" className="textarea sm" maxLength={500} rows={3} ariaLabel="경험 요약" />
      </div>
      <div className="field">
        <label>개발 경험</label>
        <div className="unit">
          <BNum path="meEdit.devYears" min={0} max={50} step={0.5} placeholder="예: 1.5" ariaLabel="개발 경험 연수" />
          <span>년</span>
        </div>
      </div>
      <div className="field">
        <label>기술 스택{skills.data ? ` · ${skills.data.skills.length}개 스킬에서 선택` : ''}</label>
        {skills.isPending ? <p className="small muted">스킬을 불러오는 중…</p> : null}
        {skills.isError ? <button type="button" className="btn line sm" onClick={() => void skills.refetch()}>스킬 다시 불러오기</button> : null}
        <div className="chips" id="profile-tech-skills">
          {visibleSkills.map(name => (
            <label className="chip" key={name}>
              <input type="checkbox" checked={selected.includes(name)} disabled={selected.length >= 36 && !selected.includes(name)} onChange={event => {
                const next = event.target.checked ? [...selected, name] : selected.filter(item => item !== name);
                setAt('meEdit.tech', next.join('\n'));
              }} />{name}
            </label>
          ))}
          {skillNames.length > 5 ? (
            <button type="button" className="btn line sm" aria-expanded={showAllSkills} aria-controls="profile-tech-skills" onClick={() => setShowAllSkills(value => !value)}>
              {showAllSkills ? '접기' : '더보기'}
            </button>
          ) : null}
        </div>
      </div>
      <div className="field">
        <label htmlFor="profile-certificate">보유 자격</label>
        <div className="addrow">
          <input id="profile-certificate" className="input" style={{ minHeight: 32, paddingBlock: 4 }} value={certificateInput} maxLength={160}
            onChange={event => setCertificateInput(event.target.value)} />
          <button type="button" className="btn line sm" disabled={!canAddCertificate} onClick={() => {
            setAt('meEdit.certs', [...certificates, certificate].join('\n'));
            setCertificateInput('');
          }}>추가</button>
        </div>
        <details className="handoff">
          <summary>보유 자격증 {certificates.length}개</summary>
          {certificates.length ? <ul className="plain-list me-list">
          {certificates.map((name, index) => <li key={index}>
            {name}{' '}
            <button type="button" className="link quiet" aria-label={`${name} 삭제`}
              onClick={() => setAt('meEdit.certs', certificates.filter((_, itemIndex) => itemIndex !== index).join('\n'))}>삭제</button>
          </li>)}
          </ul> : <p className="small muted">등록된 자격증이 없어요.</p>}
        </details>
      </div>
      {LISTS.filter(([key]) => key === 'learning').map(renderListField)}
      <p className="err" id="meErr" role="alert" hidden={!err}>{err}</p>
    </div>
  );
}

function UseCard() {
  const go = useGo();
  const lastNew = useWs((s) => s.lastNew);
  return (
    <div className="card flat">
      <h2 className="st">이 정보가 쓰이는 곳</h2>
      <div className="stack">
        <div className="row top">
          <Icon name="spark" />
          <span>
            <b>목표 후보 제안</b> · 저장한 정보로 목표 후보 3개를 준비해요.{' '}
            <button className="link" onClick={() => go(newIdToPath(lastNew))}>
              새 로드맵 작성 <Icon name="right" />
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}

export function MePage() {
  const go = useGo();
  const e = useMe();
  const ed = useWs((s) => s.meEdit);
  const [err, setErr] = useState('');
  if (!e) return null;
  const startEdit = () => {
    const p = e.profile || {};
    const v: Record<string, unknown> = { workDesc: p.workDesc || '', expSummary: p.expSummary || '', devYears: p.devYears == null ? '' : p.devYears };
    LISTS.forEach(([k]) => {
      v[k] = (e[k] || []).join('\n');
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
    const ls = { tech: lines(ed.tech), certs: lines(ed.certs), learning: lines(ed.learning), projects: e.projects || [] };
    if (ls.learning.length > 20) return setErr('교육 이력은 최대 20개까지 저장할 수 있어요.');
    try {
      const r = await accountApi.saveSelf({
        workDesc: wd,
        expSummary: ex,
        devYears: yrs,
        noneConfirmed: Object.fromEntries(LISTS.map(([k]) => [k, !ls[k].length])),
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
          직접 고친 본인 입력 정보(업무 설명·경험·기술 스택·자격·교육·프로젝트)를 지우고 팀 DB에 처음 들어온 값으로 되돌려요.
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
      titleAction={<button type="button" className="btn line sm" onClick={() => go(paths.password)}>비밀번호 변경</button>}
    >
      <MySkillMap />
      <div className="me-page">
        <details className="card handoff" open>
          <summary className="sec-h"><Icon name="right" />
            <h2 className="st">본인 입력 정보</h2>
            {e.edited ? <span className="tag acc">{`수정일${e.editedAt ? ` · ${e.editedAt}` : ''}`}</span> : null}
          </summary>
          {ed ? null : (
            <div className="me-edit-actions">
              <button className="btn line sm" onClick={startEdit}>
                <Icon name="edit" />
                수정
              </button>
            </div>
          )}
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
          {e.edited && !ed ? (
            <p className="small">
              <button type="button" className="link quiet" onClick={revert}>처음 값으로 되돌리기</button>
            </p>
          ) : null}
        </details>
        <HrCard e={e} />
        <PermCard e={e} />
        <UseCard />
      </div>
    </Page>
  );
}

