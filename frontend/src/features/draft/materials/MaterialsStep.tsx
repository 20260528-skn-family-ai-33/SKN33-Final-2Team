import { useRef, useState } from 'react';
import { paths } from '@/app/paths';
import { useGo } from '@/shared/hooks/useGo';
import { Page } from '@/shared/ui/parts';
import { Stepper } from '../Stepper';
import { ResourceSelection, type ResourceSelectionHandle } from '../result/ResultStep';
import { completeMaterialSelection } from './materialTransition';
import { updateWs } from '@/shared/state/workspace';
import { invalidateDraft } from '../invalidation';

export function MaterialsStep() {
  const go = useGo();
  const editor = useRef<ResourceSelectionHandle>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function next() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      await completeMaterialSelection(() => editor.current?.save() || Promise.resolve(false), go);
    } catch (e) {
      setError(e instanceof Error ? e.message : '저장한 자료를 불러오지 못했어요. 다시 시도해 주세요.');
    } finally { setBusy(false); }
  }
  return <><Stepper cur="materials" busy={busy} /><Page title="학습할 자료를 골라 주세요" lead="강좌·도서를 선택하고 저장해 주세요. 다음 화면에서 선택한 자료를 바탕으로 산출물을 제안받아요."
    foot={<><button className="btn line" disabled={busy} onClick={() => go(paths.newOptions)}>이전: 로드맵 선택</button>
      <button className="btn pri" disabled={busy} onClick={() => void next()}>{busy ? '저장 중…' : '다음: 검토·확정'}</button></>}>
    <ResourceSelection ref={editor} locked={busy} onChoicesChanged={() => updateWs(s => invalidateDraft(s, 'materials'))} />
    {error && <p className="err" role="alert">{error}</p>}
  </Page></>;
}
