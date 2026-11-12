import { useEffect, useRef, useState, type FormEvent } from 'react';
import { storeOptions, useBrowserOptions } from '@/shared/lib/browserOptions';

export function RunpodSettings({ focus, onDone }: { focus: 'url' | 'key'; onDone: (message: string) => void }) {
  const [url, setUrl] = useState(() => useBrowserOptions.getState().options.ollamaUrl || '');
  const [key, setKey] = useState(() => useBrowserOptions.getState().options.ollamaKey || '');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);
  const normalize = (value: string) => value.trim().toLowerCase().replace(/\/$/, '');

  async function save(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    const base = normalize(url);
    if (base && !/^https?:\/\/[a-z0-9.:-]{1,255}$/.test(base)) {
      setError('RunPod HTTPS 프록시 또는 공개 IPv4와 TCP 포트를 입력해 주세요.');
      return;
    }
    if (key && !/^[!-~]{1,1024}$/.test(key)) {
      setError('키는 공백 없는 ASCII 문자 1~1024자여야 합니다.');
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    setSaving(true);
    setError('');
    try {
      // 주소의 허용 범위는 서버가 판정한다. 확인 중에 실제 Pod를 호출하지 않는다.
      const response = await fetch('/api/v1/console/capabilities', {
        credentials: 'same-origin', mode: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: base ? { 'X-GrowPath-Ollama-Url': base } : {},
      });
      const data = await response.json();
      if (controller.signal.aborted) return;
      if (!response.ok || !data.demo || useBrowserOptions.getState().options.demo === false) {
        setError(data.error?.message || '시연 모드를 확인해 주세요.');
        return;
      }
      const next = { ...useBrowserOptions.getState().options };
      if (base) next.ollamaUrl = base;
      else delete next.ollamaUrl;
      if (key) next.ollamaKey = key;
      else delete next.ollamaKey;
      storeOptions(next);
      onDone('이 브라우저의 RunPod 연결 설정을 저장했습니다.');
    } catch {
      if (!controller.signal.aborted) setError('RunPod 설정을 저장하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  }

  return <form onSubmit={save} autoComplete="off">
    <fieldset disabled={saving}><legend>RunPod 연결 설정</legend>
      <label>OLLAMA_BASE_URL<input autoFocus={focus === 'url'} type="url" value={url} placeholder="서버 기본 주소"
        onChange={event => {
          if (normalize(event.target.value) !== normalize(url)) setKey('');
          setUrl(event.target.value);
        }} /></label>
      <label>OLLAMA_API_KEY<input autoFocus={focus === 'key'} type="password" value={key} autoComplete="off"
        placeholder={url.trim() ? '이 Pod의 키' : '서버 기본 키'} onChange={event => setKey(event.target.value)} /></label>
      <small>주소를 바꾸면 해당 Pod의 키를 다시 입력하세요. 개인 주소에서 키를 비우면 인증 없이 연결합니다.</small>
      {error && <p role="alert">{error}</p>}
      <footer><button type="submit">저장</button><button type="button" onClick={() => onDone('변경을 취소했습니다.')}>취소</button></footer>
    </fieldset>
  </form>;
}
