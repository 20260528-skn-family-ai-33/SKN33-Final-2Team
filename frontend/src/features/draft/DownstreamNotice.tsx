/* 앞 단계(1~3단계)를 고치면 뒤 단계 결과가 바로 지워진다(guard.tsx · invalidation.ts).
   지워지기 전에 알 수 있게, 뒤 단계 결과가 있을 때만 화면 위에 미리 적는다(#224 · 지우는 규칙 자체는 그대로) */
import { useWs } from '@/shared/state/workspace';
import { Note } from '@/shared/ui/parts';

export function DownstreamNotice() {
  const tested = useWs((s) => !!s.draft.v2Assessment?.completed);
  const made = useWs((s) => !!(s.draft.gen || s.draft.handoff));
  if (!tested && !made) return null;
  return (
    <Note>
      여기서 목표·기획서 요약·학습 여건·스킬을 바꾸면 {made ? '역량 테스트 응답과 만들어 둔 로드맵 3안이' : '역량 테스트 응답이'} 지워져요. 바꾼 뒤에는 역량 테스트부터 다시 진행해요.
    </Note>
  );
}
