import { useState } from 'react';
import { canUseDemo } from '@/shared/lib/demoAccess';
import { useAi } from '@/shared/state/ai';
import { toast } from '@/shared/state/ui';
import { useConsoleActions } from './consoleActions';

export function FillAnswersButton() {
  const showTools = useAi(s => canUseDemo(s.status.demoMode));
  const fill = useConsoleActions(s => s.actions.find(action => action.name === 'fill'));
  const [busy, setBusy] = useState(false);
  if (!showTools) return null;

  async function fillAnswers() {
    if (!fill || busy) return;
    setBusy(true);
    try {
      toast(await fill.run());
    } catch (error) {
      toast(error instanceof Error ? error.message : '응답을 채우지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  return <button type="button" className="btn line sm" disabled={!fill || busy} onClick={fillAnswers}>
    빈 응답 무작위 채우기
  </button>;
}
