/* 로그인 (API-01 · 5차 gp-app.js scr.login)
   팀 DB 직원(사번)과 관리자 전용 계정(직원과 별개)이 같은 칸으로 로그인한다. 비밀번호는 서버가 argon2 로 확인한다.
   '직원 고르기'(베타용)는 부서별로 묶고, 팀이 넣은 테스트 계정은 따로 묶는다 */
import { useRef, useState, type FormEvent } from 'react';
import { ApiError } from '@/api/client';
import { accountApi } from '@/api/endpoints/account';
import type { Account, DemoAccount } from '@/api/types/account';
import { ai, cause, ping } from '@/shared/state/ai';
import { me, setAccount, useSession } from '@/shared/state/session';
import { toast } from '@/shared/state/ui';
import { Icon } from '@/shared/ui/Icon';
import { AppVersion } from '@/shared/ui/AppVersion';
import { ThemeToggle } from '@/skins/ThemeControls';
import { loadLastLoginId, saveLastLoginId } from './lastLoginId';
import { LoginFlow } from './LoginFlow';

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
  const accts = demo?.accounts || [];
  // 마지막으로 로그인한 사번을 채워 두고, 그때는 바로 비밀번호를 입력하도록 비밀번호 칸에 초점을 둔다
  const [lastId] = useState(loadLastLoginId);
  const [code, setCode] = useState(lastId);
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
    saveLastLoginId(c);
    try {
      await setAccount(acct);
    } catch (x) {
      setBusy(false);
      return setErr(`로그인했지만 기록을 불러오지 못했어요 · ${cause(x).user}`);
    }
    setPw('');
    toast(acct.accountType === 'admin' ? `관리자 ${acct.admin.name} 님, 반가워요` : `${acct.user.name} 님, 반가워요`);
    if (me() && ai.live()) void ping();
  };

  return (
    <div className="login-wrap">
      <section className="login-card" aria-labelledby="lgTitle">
        {/* 화면을 좌우 두 면으로 나눈다(2026-11-17 · vyblor 기준으로 정돈). 왼쪽 면은 로그인 하나에 집중한다:
            위 로고·서비스 이름·모드 버튼 · 그 아래 제목 · 가운데 입력 칸 · 아래 버전. 서비스 이름은 꾸밈 꼬리표 대신 로고 옆 글자로 둔다 */}
        <header className="login-brand">
          <span className="logo" aria-hidden="true">
            <Icon name="logo" />
          </span>
          <b>GrowPath</b>
          <span className="login-brand-sub">개발·운영 직원 AI 역량 성장지원</span>
          <ThemeToggle />
        </header>
        {/* 제목은 로고 줄과 입력 칸 사이의 가운데에 둔다(gp-v2.css .login-card 줄 나눔) */}
        <div className="login-title">
          <h1 className="t lg" id="lgTitle">
            다시 오신 걸 환영해요
          </h1>
        </div>
        <div className="login-body">
          <form id="loginForm" noValidate onSubmit={submit}>
            {accts.length > 0 && <div className="field lg-pick">
              <label htmlFor="lgPick">
                직원 고르기 <span className="muted small">고르면 사번을 채워요</span>
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
            </div>}
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
                  autoFocus={!!lastId}
                  type={showPw ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="비밀번호를 입력해 주세요"
                  value={pw}
                  onChange={(e) => setPw(e.target.value)}
                />
                {/* 보이는 중에는 빗금 친 눈 · 눌린 모양(aria-pressed)으로 지금 상태를 구분한다 */}
                <button
                  type="button"
                  className="eye"
                  aria-label={showPw ? '비밀번호 숨기기' : '비밀번호 보기'}
                  aria-pressed={showPw}
                  title={showPw ? '비밀번호 숨기기' : '비밀번호 보기'}
                  onClick={() => setShowPw(!showPw)}
                >
                  <Icon name={showPw ? 'eyeOff' : 'eye'} />
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
                onClick={() => toast('비밀번호는 관리자에게 문의해 주세요. 관리자에게 받은 초기 비밀번호로 로그인해 주세요.')}
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
        </div>
        <AppVersion />
      </section>
      <LoginFlow />
    </div>
  );
}
