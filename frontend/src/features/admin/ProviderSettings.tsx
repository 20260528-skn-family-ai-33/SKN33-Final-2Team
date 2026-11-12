import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminApi, type AdminProviderSettings } from '@/api/endpoints/admin';
import { aiApi } from '@/api/endpoints/account';
import type { ProviderPolicy, ServerProvider } from '@/api/types/account';
import { checkStatus, levelLabel, PROV } from '@/shared/state/ai';
import { FailBox } from './parts';

const key = ['admin', 'ai-provider'] as const;
const label = (p: ProviderPolicy) => p === 'employee' ? '직원별 선택 (베타)' : PROV[p];

function ProviderKey({ provider, settings }: { provider: ServerProvider; settings: AdminProviderSettings['providers'][ServerProvider] }) {
  const cache = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState('');
  async function update(value?: string) {
    setPending(true);
    setNotice('');
    try {
      const saved = value === undefined ? await adminApi.resetProviderKey(provider) : await adminApi.setProviderKey(provider, value);
      cache.setQueryData(key, saved);
      setEditing(false);
      setNotice(value === undefined ? '관리자 등록 키를 해제했어요.' : '새 키를 저장했어요.');
      void checkStatus();
    } catch {
      setNotice('키 설정을 저장하지 못했어요. 다시 확인해 주세요.');
    } finally {
      setPending(false);
    }
  }
  return <div>
    <p className="small muted">{settings.model} · {settings.keySource === 'admin' ? '관리자 등록 키 사용 중' : settings.keySource === 'env' ? '서버 기본 키 사용 중' : 'API 키 미등록'}{!settings.available && ' · 서버 연결 설정 필요'}</p>
    {editing ? <form onSubmit={event => {
      event.preventDefault();
      const input = event.currentTarget.elements.namedItem('providerKey') as HTMLInputElement;
      const value = input.value;
      input.value = '';
      void update(value);
    }}>
      <label>새 API 키 <input className="input" type="password" name="providerKey" autoComplete="new-password" required maxLength={4096} pattern="[!-~]+" disabled={pending} /></label>
      <div className="actions">
        <button className="btn line sm" type="submit" disabled={pending}>키 저장</button>
        <button className="btn line sm" type="button" disabled={pending} onClick={() => setEditing(false)}>취소</button>
      </div>
    </form> : <div className="actions">
      <button className="btn line sm" disabled={pending} onClick={() => { setEditing(true); setNotice(''); }}>API 키 {settings.keyConfigured ? '변경' : '등록'}</button>
      {settings.keySource === 'admin' && <button className="btn line sm" disabled={pending} onClick={() => void update()}>{settings.hasDefaultKey ? '기본 키로 복원' : '등록 키 삭제'}</button>}
    </div>}
    {notice && <p role="status">{notice}</p>}
  </div>;
}

export function ProviderSettings() {
  const cache = useQueryClient();
  const q = useQuery({ queryKey: key, queryFn: adminApi.providerSettings });
  const [selection, setSelection] = useState<ProviderPolicy>();
  const [draftLevel, setDraftLevel] = useState<string>();
  const [notice, setNotice] = useState('');
  const save = useMutation({ mutationFn: adminApi.setProviderPolicy, onSuccess: (saved) => {
    cache.setQueryData(key, saved);
    setSelection(undefined);
    setDraftLevel(undefined);
    setNotice('모델 설정을 저장했어요.');
    void checkStatus();
  } });
  const check = useMutation({ mutationFn: async (provider: ServerProvider) => {
    const result = await aiApi.status(provider);
    const missing = result.models?.filter((m) => !m.installed).map((m) => m.name);
    return missing?.length ? '설치가 필요한 모델 · ' + missing.join(', ') : PROV[provider] + ' 연결을 확인했어요.';
  }, onSuccess: setNotice });
  const data = q.data;
  const selected = selection ?? data?.policy;
  // 추론 단계는 OpenAI 만 고른다. RunPod-Ollama 는 서버가 모든 호출을 추론 없이 보낸다
  const savedLevel = selected === 'openai' && selected === data?.policy ? data?.level || '' : '';
  const level = draftLevel ?? savedLevel;
  const choices = data?.providers.openai.levels || [];
  const validLevel = !level || choices.includes(level);
  return (
    <section className="card">
      <h2 className="st">AI 모델 설정</h2>
      {q.isError && <FailBox err={q.error} what="AI 설정을 불러오지 못했어요" />}
      {data ? <>
        {data.policy ? <p>현재 적용 · <strong>{label(data.policy)}</strong></p> :
          <p role="alert">저장된 모델 설정을 읽을 수 없어요. 사용할 모델을 선택하고 저장해 주세요.</p>}
        {data.policyStatus === 'default_ollama' && <p className="small muted">직원별 선택이 꺼져 있고 지정된 모델이 없어 Ollama를 사용 중이에요.</p>}
        <label>사용할 모델 <select className="input" value={selected ?? ''} disabled={save.isPending || check.isPending}
          onChange={(event) => { setSelection(event.target.value as ProviderPolicy); setDraftLevel(undefined); setNotice(''); check.reset(); save.reset(); }}>
          {!selected && <option value="" disabled>모델을 선택해 주세요</option>}
          {data.employeeSelectionAllowed && <option value="employee">{label('employee')}</option>}
          {(['openai', 'ollama'] as const).map((p) => <option key={p} value={p}>{label(p)} · {data.providers[p].model}</option>)}
        </select></label>
        {selected === 'openai' && <label>추론 정도 <select className="input" value={level} disabled={save.isPending || check.isPending || (!choices.length && !level)}
          onChange={event => { setDraftLevel(event.target.value); setNotice(''); save.reset(); }}>
          <option value="">서버 기본값</option>
          {choices.map(option => <option key={option} value={option}>{levelLabel(option)} ({option})</option>)}
          {!validLevel && <option disabled value={level}>{levelLabel(level)} · 현재 모델에서 사용 불가</option>}
        </select></label>}
        {selected === 'ollama' && <p className="small muted">추론 없음 · RunPod-Ollama는 모든 답변을 추론 없이 만들어요.</p>}
        {selected && selected !== 'employee' && <ProviderKey key={selected} provider={selected} settings={data.providers[selected]} />}
        <div className="actions">
          {selected && selected !== 'employee' && <button className="btn line sm" disabled={save.isPending || check.isPending || !data.providers[selected].available}
            onClick={() => { setNotice(''); check.mutate(selected); }}>{check.isPending ? '확인 중…' : '연결 확인'}</button>}
          <button className="btn pri sm" disabled={!selected || (data.policyStatus !== 'default_ollama' && selected === data.policy && level === savedLevel) || !validLevel || save.isPending || check.isPending || (selected !== 'employee' && !data.providers[selected].available)}
            onClick={() => { if (selected) { setNotice(''); save.mutate({ policy: selected, level: level || null }); } }}>설정 저장</button>
        </div>
        {save.isError && <FailBox err={save.error} what="AI 설정을 저장하지 못했어요" />}
        {check.isError && <p role="alert">모델 연결에 실패했어요. 서버 주소와 API 키 설정을 확인해 주세요.</p>}
        {notice && <p role="status">{notice}</p>}
      </> : q.isPending && <p>설정을 불러오는 중…</p>}
    </section>
  );
}
