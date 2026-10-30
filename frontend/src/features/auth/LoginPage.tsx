/* 로그인 (API-01 · 5차 gp-app.js scr.login)
   팀 DB 직원(사번)과 관리자 전용 계정(직원과 별개)이 같은 칸으로 로그인한다. 비밀번호는 서버가 argon2 로 확인한다.
   '직원 고르기'(시연용)는 부서별로 묶고, 팀이 넣은 테스트 계정은 따로 묶는다 */
import { useRef, useState, type FormEvent } from 'react';
import { ApiError } from '@/api/client';
import { accountApi } from '@/api/endpoints/account';
import type { Account, DemoAccount } from '@/api/types/account';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { ai, cause, ping } from '@/shared/state/ai';
import { isSup, me, setAccount, useSession } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { ws } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Note } from '@/shared/ui/parts';

const Feat = ({ ic, t, d }: { ic: string; t: string; d: string }) => (
  <div className="feat">
    <span className="ico">
      <Icon name={ic} />
    </span>
    <span>
      <b>{t}</b>
      <small>{d}</small>
    </span>
  </div>
);

function deptGroups(accts: DemoAccount[]) {
  const out: { dept: string; list: DemoAccount[] }[] = [];
  const team: DemoAccount[] = [];
  accts.forEach((e) => {
    if (e.team) {
      team.push(e);
      return;
    }
    let g = out.find((x) => x.dept === (e.dept || '부서 없음'));
    if (!g) out.push((g = { dept: e.dept || '부서 없음', list: [] }));
    g.list.push(e);
  });
  out.forEach((g) => g.list.sort((a, b) => (b.supervisor ? 1 : 0) - (a.supervisor ? 1 : 0)));
  if (team.length) out.push({ dept: '팀 DB 테스트 계정', list: team });
  return out;
}

export function LoginPage() {
  const demo = useSession((s) => s.demo);
  const go = useGo();
  const accts = demo?.accounts || [];
  const demoPw = demo?.demoPassword || '';
  const [code, setCode] = useState('');
  const [pw, setPw] = useState('');
  const [keep, setKeep] = useState(true);
  const [showPw, setShowPw] = useState(false);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const pwRef = useRef<HTMLInputElement>(null);
  const groups = deptGroups(accts);
  const picked = accts.some((a) => a.code === code) || (demo?.adminLogin && code === demo.adminLogin) ? code : '';

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const c = code.trim();
    if (!c || !pw) return setErr('사번과 비밀번호를 입력해 주세요.');
    setBusy(true);
    setErr('');
    let acct: Account;
    try {
      acct = await accountApi.login(c, pw, keep);
    } catch (x) {
      setBusy(false);
      setPw('');
      const k = x instanceof ApiError ? x.payload : {};
      return setErr(
        k.code === 'ACCOUNT_INACTIVE'
          ? '지금은 쓸 수 없는 계정이에요. 인사 담당 부서(인재경영실)에 문의해 주세요.'
          : x instanceof ApiError && x.status === 401
            ? '사번 또는 비밀번호가 맞지 않아요.'
            : cause(x).user,
      );
    }
    try {
      await setAccount(acct);
    } catch (x) {
      setBusy(false);
      return setErr(`로그인했지만 기록을 불러오지 못했어요 · ${cause(x).user}`);
    }
    setPw('');
    const last = ws().lastRoute;
    const admin = acct.accountType === 'admin';
    const back = last && last !== paths.login && !last.startsWith('/admin') && (!last.startsWith('/team') || isSup(me())) ? last : paths.home;
    go(admin ? paths.admin : back, { force: true, replace: true });
    toast(acct.accountType === 'admin' ? `관리자 ${acct.admin.name} 님, 반가워요` : `${acct.user.name} 님, 반가워요`);
    if (me() && ai.live()) void ping();
  };

  return (
    <div className="login-wrap">
      <section className="login-card" aria-labelledby="lgTitle">
        <span className="tag acc">
          <Icon name="lock" />
          한국수자원공사 임직원 로그인 · 시연용
        </span>
        <h1 className="t lg" id="lgTitle">
          다시 오신 걸 환영해요
        </h1>
        <p className="lead">AI 활용·개발 역량 성장 로드맵을 이어서 만들어 보세요.</p>
        <form id="loginForm" noValidate onSubmit={submit}>
          <div className="field lg-pick">
            <label htmlFor="lgPick">
              직원 고르기 <span className="muted small">시연용 · 고르면 사번을 채워요</span>
            </label>
            <select
              className="input"
              id="lgPick"
              value={picked}
              onChange={(e) => {
                if (e.target.value) {
                  setCode(e.target.value);
                  setErr('');
                  pwRef.current?.focus();
                }
              }}
            >
              <option value="">팀 DB 직원 {accts.length}명 중 고르기</option>
              {groups.map((g) => (
                <optgroup label={g.dept} key={g.dept}>
                  {g.list.map((e) => (
                    <option value={e.code} key={e.code}>
                      {e.name}
                      {e.supervisor ? ' (부서장)' : ''}
                      {e.team ? ` · ${e.dept}` : ''}
                    </option>
                  ))}
                </optgroup>
              ))}
              {demo?.adminLogin ? (
                <optgroup label="관리자">
                  <option value={demo.adminLogin}>관리자 전용 계정 ({demo.adminLogin})</option>
                </optgroup>
              ) : null}
            </select>
          </div>
          <div className="field">
            <label htmlFor="lgId">사번 또는 관리자 아이디</label>
            <input
              className="input"
              id="lgId"
              maxLength={40}
              autoComplete="username"
              placeholder="8자리 사번 (예: 20200001)"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="lgPw">비밀번호</label>
            <div className="pw">
              <input
                className="input"
                id="lgPw"
                ref={pwRef}
                type={showPw ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="비밀번호를 입력해 주세요"
                value={pw}
                onChange={(e) => setPw(e.target.value)}
              />
              <button type="button" className="eye" aria-label={showPw ? '비밀번호 숨기기' : '비밀번호 보기'} onClick={() => setShowPw(!showPw)}>
                <Icon name="eye" />
              </button>
            </div>
          </div>
          <div className="row" style={{ marginTop: 14 }}>
            <label className="check">
              <input type="checkbox" id="lgKeep" checked={keep} onChange={(e) => setKeep(e.target.checked)} />
              로그인 상태 유지
            </label>
            <span className="grow" />
            <button
              type="button"
              className="link quiet"
              onClick={() => toast(`시연에서는 비밀번호 찾기를 연결하지 않았어요. 초기 비밀번호는 ${demoPw || '.env에 정한 값'}이에요`)}
            >
              비밀번호 찾기
            </button>
          </div>
          <p className="err" id="lgErr" role="alert" hidden={!err}>
            {err}
          </p>
          <button className="btn pri block" type="submit" style={{ marginTop: 18 }} disabled={busy}>
            로그인 <Icon name="arrow" />
          </button>
        </form>
        <div className="or">또는</div>
        <button className="btn line block" onClick={() => toast('시연에서는 기관 통합인증을 연결하지 않았어요. 사번과 비밀번호로 로그인해 주세요')}>
          <Icon name="users" />
          기관 통합인증(SSO)으로 로그인
        </button>
        {accts.length ? null : <Note>직원 목록을 불러오지 못했어요. 백엔드와 DB가 켜져 있는지 확인해 주세요(docker compose ps).</Note>}
        <Note>
          시연용 화면이에요. 기관 통합인증은 연결하지 않았어요. 팀 DB(PostgreSQL) 직원의 사번으로 들어올 수 있고, 시연 환경의 초기 비밀번호는 모두{' '}
          {demoPw || '.env에 정한 값'}이에요. 비밀번호는 서버가 해시로만 확인해요. 관리자 화면은 관리자 전용 계정으로 들어가요. 다른 계정으로 바꾸려면 로그아웃한 뒤 다시
          로그인해 주세요.
        </Note>
      </section>
      <aside className="login-side">
        <span className="pill">
          <Icon name="spark" />
          개발·운영 직원 AI 역량 성장지원
        </span>
        <h2>
          목표만 적으면,
          <br />
          나에게 맞는 로드맵 3안을
        </h2>
        <p>목표와 학습 여건을 적고 짧은 점검에 답하면, 관점이 다른 로드맵 3안을 비교해 고를 수 있어요.</p>
        <div className="feats">
          <Feat ic="edit" t="학습 여건은 간단한 입력으로" d="학습 방식·자격증·시간·기간·예산을 적거나, 비워 두면 알아서 정해요." />
          <Feat ic="map" t="관점별 로드맵 3안" d="비용·시간·업무 적용 관점의 에이전트가 동시에 쓰고, 마음에 들지 않는 안은 그 안만 다시 만들어요." />
          <Feat ic="chat" t="사내 생활 도우미" d="업무·사내 생활 질문에 답하고, 규정 질문은 기관 규정 원문의 근거 조항과 함께 답해요." />
        </div>
        <p className="small" style={{ marginTop: 'auto', opacity: 0.82 }}>
          부서장은 자기 부서 직원이 확정한 로드맵·진행 상태·결과 보고서를 보고 코멘트만 남겨요.
        </p>
      </aside>
    </div>
  );
}
