import { useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { adminApi, type AdminProviderSettings } from '@/api/endpoints/admin';
import { checkStatus } from '@/shared/state/ai';

export function RunpodConnection({ settings }: { settings: AdminProviderSettings }) {
  const cache = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState('');
  const [key, setKey] = useState('');
  const [pending, setPending] = useState(false);
  const [checked, setChecked] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const current = settings.runpod;
  const provider = settings.providers.ollama;

  function clearResult() {
    setChecked(false);
    setNotice('');
    setError('');
  }

  async function run(action: 'check' | 'save' | 'reset') {
    setPending(true);
    clearResult();
    const draft = { url: url.trim(), key };
    try {
      if (action === 'check') {
        const result = await adminApi.checkRunpod(editing ? draft : undefined);
        setChecked(editing);
        setNotice(['연결 확인 완료', ...(result.models ?? []).map(model => model.name)].join(' · '));
      } else {
        const saved = action === 'save' ? await adminApi.saveRunpod(draft) : await adminApi.resetRunpod();
        cache.setQueryData(['admin', 'ai-provider'], saved);
        setKey('');
        setEditing(false);
        setNotice(action === 'save' ? '공용 RunPod 연결을 저장했어요.' : '기존 서버 연결로 복원했어요.');
        void checkStatus();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '공용 RunPod 설정을 확인해 주세요.');
    } finally {
      setPending(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(checked ? 'save' : 'check');
  }

  return <fieldset disabled={pending}>
    <legend>공용 RunPod 연결</legend>
    {editing ? <form onSubmit={submit}>
      <label>RunPod 주소 <input className="input" type="url" required value={url} placeholder="https://my-pod-11434.proxy.runpod.net"
        onChange={e => { setUrl(e.target.value); setKey(''); clearResult(); }} /></label>
      <label>RunPod API 키 <input className="input" type="password" value={key} autoComplete="new-password"
        maxLength={4096} pattern="[!-~]+" onChange={e => { setKey(e.target.value); clearResult(); }} /></label>
      <p className="small muted">이 Pod에서 사용할 키를 입력하세요. 비워 두면 키 없이 연결합니다.</p>
      <div className="actions">
        <button type="submit" className="btn pri sm">{pending ? '확인 중…' : checked ? '공용 연결 저장' : '연결 확인'}</button>
        <button type="button" className="btn line sm" onClick={() => { setEditing(false); setKey(''); clearResult(); }}>취소</button>
      </div>
    </form> : <>
      <p>{current.url || (provider.available ? '서버 기본 주소' : '주소 미설정')} · {provider.keyConfigured ? '키 설정됨' : '키 없음'}</p>
      <div className="actions">
        <button type="button" className="btn line sm" onClick={() => { setUrl(current.url); setKey(''); setEditing(true); clearResult(); }}>주소·키 변경</button>
        <button type="button" className="btn line sm" disabled={!provider.available} onClick={() => void run('check')}>{pending ? '확인 중…' : '연결 확인'}</button>
        {current.managed && <button type="button" className="btn line sm" onClick={() => void run('reset')}>기존 서버 연결로 복원</button>}
      </div>
    </>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
  </fieldset>;
}
