import { useRef, useState, type FormEvent } from 'react';
import { ApiError } from '@/api/client';
import { accountApi } from '@/api/endpoints/account';
import { paths } from '@/app/paths';
import { logoutAndReset } from '@/features/auth/actions';
import { useGo } from '@/shared/hooks/useGo';
import { toast } from '@/shared/state/ui';
import { Page } from '@/shared/ui/parts';

export function PasswordPage() {
  const go = useGo();
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    const form = event.currentTarget;
    const fields = new FormData(form);
    const current = String(fields.get('current') ?? '');
    const next = String(fields.get('next') ?? '');
    if (next !== fields.get('confirm')) {
      setError('새 비밀번호 확인이 일치하지 않아요.');
      return;
    }
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      await accountApi.changePassword(current, next);
      form.reset();
      await logoutAndReset(go);
      toast('비밀번호를 변경했어요. 새 비밀번호로 다시 로그인해 주세요.');
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : '비밀번호를 변경하지 못했어요.');
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return (
    <Page back={busy ? undefined : paths.me} eyebrow="내 정보" title="비밀번호 변경">
      <form className="card stack" onSubmit={submit}>
        <label>현재 비밀번호
          <input className="input" name="current" type="password" autoComplete="current-password" required maxLength={1024} disabled={busy} />
        </label>
        <label>새 비밀번호
          <input className="input" name="next" type="password" autoComplete="new-password" required minLength={4} maxLength={128} disabled={busy} />
        </label>
        <label>새 비밀번호 확인
          <input className="input" name="confirm" type="password" autoComplete="new-password" required minLength={4} maxLength={128} disabled={busy} />
        </label>
        {error && <p className="err" role="alert">{error}</p>}
        <div className="actions">
          <button type="submit" className="btn pri" disabled={busy}>{busy ? '변경 중…' : '비밀번호 변경'}</button>
          <button type="button" className="btn line" disabled={busy} onClick={() => go(paths.me)}>취소</button>
        </div>
      </form>
    </Page>
  );
}
