/* 관리자 개요 (5차 gp-admin.js overview) — 데이터별 개수 · 목표 후보 일괄 다시 만들기 · 최근 변경
   규정은 원문 PDF 개수만 보인다(2026-10-26 · 규정 색인은 서비스 운영팀이 하므로 관리자 화면에서 뺌) */
import type { ReactNode } from 'react';
import { adminApi } from '@/api/endpoints/admin';
import type { AdminOverview, GoalMode } from '@/api/types/admin';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { failToast } from '@/shared/lib/fail';
import { ai, useAi } from '@/shared/state/ai';
import { closeSheet, openSheet, toast } from '@/shared/state/ui';
import { Icon } from '@/shared/ui/Icon';
import { Loading, Note, Page } from '@/shared/ui/parts';
import { refreshGoals, useGoalEmployees, useOverview } from './adminData';
import { adm, pickGoal, setChoice, setGoal, useAdmin } from './adminStore';
import { DS, EDU_KIND, REG } from './datasets';
import { FailBox, Num, UploadList } from './parts';

const PAGE_HEAD = { eyebrow: '관리자', title: '데이터 관리' };
const EDU = ['course', 'book', 'cert'] as const;

function Card({ head, to, children }: { head: { title: string; icon: string }; to: string; children: ReactNode }) {
  const go = useGo();
  return (
    <div className="card">
      <div className="sec-h">
        <h2 className="st">
          <Icon name={head.icon} /> {head.title}
        </h2>
        <button className="link" onClick={() => go(to)}>
          관리 <Icon name="right" />
        </button>
      </div>
      {children}
    </div>
  );
}

/* ── 목표 후보 다시 만들기: 대상(재직 직원 모두 / 고른 직원만) × 모델(가데이터 · 각 직원의 AI 모드 · 관리자가 고른 모델) ──
   관리자가 고른 모델은 이번 작업에만 쓰고 직원이 고른 AI 모드는 바꾸지 않는다(2026-10-26) */
const GOAL_STATUS: Record<string, string> = { ready: '준비됨', default: '기본 후보', running: '만드는 중', failed: '실패' };
const GOAL_SRC: Record<string, string> = { mock: '가데이터', ollama: 'RunPod-Ollama', openai: 'OpenAI API' };
const MODE_LABEL: Record<string, string> = { mock: '가데이터', employee: '각 직원의 AI 모드', ollama: 'RunPod-Ollama', openai: 'OpenAI API' };
const withModel = (label: string, model: string) => (model ? `${label} · ${model}` : label);

function GoalPicker() {
  const q = useGoalEmployees();
  const { picked, q: text } = useAdmin((s) => s.goal);
  if (q.isPending) return <Loading text="직원 목록을 불러오는 중…" />;
  if (q.isError) return <FailBox err={q.error} what="직원 목록을 불러오지 못했어요" />;
  const t = text.trim().toLowerCase();
  const list = q.data.filter((e) => !t || `${e.name} ${e.dept} ${e.grade} ${e.no}`.toLowerCase().includes(t));
  const allOn = list.length > 0 && list.every((e) => picked.includes(e.id));
  return (
    <div className="stack" style={{ gap: 8, marginTop: 8 }}>
      <div className="adm-pick-h">
        <input className="input" placeholder="이름·부서·직급·사번으로 찾기" aria-label="직원 찾기" value={text} onChange={(e) => setGoal({ q: e.target.value })} />
        <button className="btn line sm" disabled={!list.length} onClick={() => pickGoal(list.map((e) => e.id), !allOn)}>
          {allOn ? '보이는 직원 빼기' : '보이는 직원 모두 고르기'}
        </button>
        <span className="small muted">{picked.length}명 고름</span>
      </div>
      <div className="adm-pick" role="group" aria-label="목표 후보를 다시 만들 직원">
        {list.map((e) => (
          <label className="radio" key={e.id}>
            <input type="checkbox" checked={picked.includes(e.id)} onChange={(ev) => pickGoal([e.id], ev.target.checked)} />
            <span>
              {e.name}{' '}
              <span className="small muted">
                · {[e.dept, e.grade, e.no].filter(Boolean).join(' · ')} · {GOAL_STATUS[e.status] || '후보 없음'}
                {GOAL_SRC[e.source] ? `(${GOAL_SRC[e.source]})` : ''}
              </span>
            </span>
          </label>
        ))}
        {!list.length ? (
          <p className="small muted" style={{ margin: 0 }}>
            찾는 직원이 없어요
          </p>
        ) : null}
      </div>
    </div>
  );
}

function GoalsAllBody({ active }: { active: number }) {
  const v = useAdmin((s) => s.choice.goalsAll);
  const target = useAdmin((s) => s.goal.target);
  // 모델 사용 가능 여부는 서버 설정(/ai/providers)에서 받으므로 받은 뒤 다시 그린다
  useAi((s) => s.status);
  const mode = (value: string, label: string, note: string, ok = true, why = '') => (
    <label className={`radio${ok ? '' : ' off'}`}>
      <input type="radio" name="admGoalMode" value={value} checked={v === value} disabled={!ok} onChange={() => setChoice('goalsAll', value)} />
      <span>
        {label} <span className="small muted">· {ok ? note : `지금 쓸 수 없어요 · ${why}`}</span>
      </span>
    </label>
  );
  return (
    <>
      <p style={{ marginTop: 0 }}>목표 후보를 다시 만들어요. 본인 입력이 없는 직원은 AI 활용 업무 기본 후보로 바로 저장해요.</p>
      <p className="small" style={{ margin: '0 0 6px' }}>
        <b>누구의 후보를</b>
      </p>
      <div className="stack" style={{ gap: 6 }}>
        <label className="radio">
          <input type="radio" name="admGoalTarget" checked={target === 'all'} onChange={() => setGoal({ target: 'all' })} />
          <span>
            재직 직원 모두 <span className="small muted">· {active}명</span>
          </span>
        </label>
        <label className="radio">
          <input type="radio" name="admGoalTarget" checked={target === 'pick'} onChange={() => setGoal({ target: 'pick' })} />
          <span>고른 직원만</span>
        </label>
      </div>
      {target === 'pick' ? <GoalPicker /> : null}
      <p className="small" style={{ margin: '14px 0 6px' }}>
        <b>어떤 모델로</b>
      </p>
      <div className="stack" style={{ gap: 6 }}>
        {mode('mock', '시연용 가데이터', '비용 없음 · 바로 끝나요')}
        {mode('employee', '각 직원이 고른 AI 모드', '실제 모델 호출(OpenAI API는 비용이 들어요) · 모드가 설정되지 않은 직원은 실패로 남아요')}
        {mode('ollama', withModel('RunPod-Ollama', ai.ollamaInfo().model), '직원이 고른 모드와 관계없이 이 모델로 만들어요 · 직원 설정은 바꾸지 않아요', ai.available('ollama'), ai.unavailableWhy('ollama'))}
        {mode('openai', withModel('OpenAI API', ai.openaiModel()), '직원 한 명마다 한 번 호출해서 비용이 들어요 · 직원 설정은 바꾸지 않아요', ai.available('api'), ai.unavailableWhy('api'))}
      </div>
    </>
  );
}

async function goalsAllOk() {
  const s = adm();
  const m = s.choice.goalsAll;
  const pick = s.goal.target === 'pick' ? s.goal.picked : undefined;
  if (pick && !pick.length) return;
  closeSheet();
  try {
    const r = await adminApi.goalsAll(m === 'employee' ? null : (m as GoalMode), pick);
    toast(`직원 ${r.employees}명 · 작업 ${r.started}개 시작 · 기본 후보 ${r.defaults}명 저장 · ${MODE_LABEL[r.mode] || r.mode}`);
    /* 작업이 조금 진행된 뒤에 개수를 다시 받는다 */
    setTimeout(refreshGoals, 1500);
  } catch (err) {
    failToast(err, '목표 후보를 다시 만들지 못했어요');
  }
}

function GoalsAllFoot() {
  const empty = useAdmin((s) => s.goal.target === 'pick' && !s.goal.picked.length);
  return (
    <>
      <button className="btn line" onClick={closeSheet}>
        취소
      </button>
      <button className="btn pri" disabled={empty} title={empty ? '다시 만들 직원을 골라 주세요' : undefined} onClick={() => void goalsAllOk()}>
        다시 만들기
      </button>
    </>
  );
}

function openGoalsAll(o: AdminOverview) {
  setChoice('goalsAll', 'mock');
  setGoal({ target: 'all', picked: [], q: '' });
  openSheet({
    title: '목표 후보를 다시 만들까요?',
    body: () => <GoalsAllBody active={o.hr.active} />,
    foot: () => <GoalsAllFoot />,
  });
}

export function OverviewPage() {
  const go = useGo();
  const q = useOverview();
  if (q.isPending) return <Page {...PAGE_HEAD}>{<Loading text="지금 데이터를 불러오는 중…" />}</Page>;
  if (q.isError)
    return (
      <Page {...PAGE_HEAD}>
        <FailBox err={q.error} what="개요를 불러오지 못했어요" />
        <div className="actions">
          <button className="btn line" onClick={() => void q.refetch()}>
            다시 불러오기
          </button>
        </div>
      </Page>
    );
  const o = q.data;
  const e = o.education;
  const g = o.goals || {};
  const rg = o.regulations;
  const pv = o.providers;
  return (
    <Page
      {...PAGE_HEAD}
      lead="인적·교육 데이터는 화면에서 한 건씩 고치거나, 여러 건은 엑셀·CSV로 내려받아 고친 뒤 다시 올려요. 어느 쪽이든 같은 규칙으로 검사하고, 오류가 있으면 저장하지 않아요. 규정은 원문 PDF로 올리고 내려받아요."
    >
      <div className="adm-grid">
        <Card head={DS.hr} to={paths.adminData('hr')}>
          <div className="adm-num">
            <Num l="재직" v={o.hr.active} />
            <Num l="퇴직" v={o.hr.retired} />
            <Num l="부서" v={o.hr.departments} />
            <Num l="부서장" v={o.hr.heads} />
            <Num l="평정" v={o.hr.evaluations} />
          </div>
          {o.hr.noNumber ? (
            <p className="small muted" style={{ margin: 0 }}>
              사번이 없는 팀 테스트 계정 {o.hr.noNumber}명은 엑셀로 다루지 않아요.
            </p>
          ) : null}
          {o.hr.transfers.length ? (
            <>
              <p className="small" style={{ margin: '8px 0 0' }}>
                <b>최근 인사이동·권한 변경</b>
              </p>
              <ul className="plain-list small">
                {o.hr.transfers.map((t, i) => (
                  <li key={i}>
                    {t.at} · {t.name} · {t.from || '없음'} → {t.to || '없음'}
                    {t.headBefore !== t.headAfter ? ` · ${t.headAfter ? '부서장 지정' : '부서장 해제'}` : ''}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </Card>
        <Card head={REG} to={paths.adminRegulations}>
          <div className="adm-num">
            <Num l="지금 규정" v={rg.count} />
            <Num l="원문 PDF" v={rg.files} />
            <Num l="올린 PDF" v={rg.uploads} />
          </div>
          <p className="small muted" style={{ margin: 0 }}>
            규정은 고치지 않고 원문 PDF로 올려요. 올린 PDF는 서비스 운영팀이 받아 도우미 검색에 반영해요.
            {rg.lastUpload ? ` 마지막으로 올린 때 ${rg.lastUpload}.` : ''}
          </p>
        </Card>
        <Card head={DS.education} to={paths.adminData('education')}>
          <div className="adm-num">
            {EDU.map((k) => (
              <Num key={k} l={EDU_KIND[k]} v={e[k]?.count} />
            ))}
          </div>
          <p className="small muted" style={{ margin: 0 }}>
            추정 값이 남은 자료: {EDU.map((k) => `${EDU_KIND[k]} ${e[k]?.estimated || 0}`).join(' · ')}
          </p>
        </Card>
        <div className="card">
          <div className="sec-h">
            <h2 className="st">
              <Icon name="spark" /> 목표 후보
            </h2>
          </div>
          <div className="adm-num">
            <Num l="준비됨" v={g.ready || 0} />
            <Num l="기본 후보" v={g.default || 0} />
            <Num l="만드는 중" v={g.running || 0} />
            <Num l="실패" v={g.failed || 0} />
          </div>
          <p className="small muted" style={{ margin: 0 }}>
            직원 데이터가 바뀌면(이 화면의 저장·반영, 직원의 내 정보 저장) 그 직원의 후보를 서버가 미리 다시 만들어요.
          </p>
          <div className="actions" style={{ marginTop: 10 }}>
            <button className="btn line sm" onClick={() => openGoalsAll(o)}>
              <Icon name="retry" />
              다시 만들기
            </button>
          </div>
        </div>
      </div>
      <div className="sec">
        <div className="sec-h">
          <h2 className="st">최근 변경</h2>
          <button className="link" onClick={() => go(paths.adminHistory)}>
            전체 이력 <Icon name="right" />
          </button>
        </div>
        <UploadList list={o.uploads} />
      </div>
      <Note>
        RunPod-Ollama {pv.ollama.available ? '설정됨' : '설정 안 됨'} · OpenAI API {pv.openai.available ? '설정됨' : '설정 안 됨'}. 관리자 계정은 직원의 로드맵·점검·보고서를 보지 않아요.
      </Note>
    </Page>
  );
}
