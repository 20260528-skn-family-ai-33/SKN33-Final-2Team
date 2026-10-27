/* 변경 이력 (5차 gp-admin.js history) — 화면에서 고친 내용과 올린 파일의 미리보기·반영 결과 */
import { Loading, Page } from '@/shared/ui/parts';
import { useUploads } from './adminData';
import { FailBox, UploadList } from './parts';

export function HistoryPage() {
  const q = useUploads();
  if (q.isPending)
    return (
      <Page eyebrow="관리자" title="변경 이력">
        <Loading text="불러오는 중…" />
      </Page>
    );
  if (q.isError)
    return (
      <Page eyebrow="관리자" title="변경 이력">
        <FailBox err={q.error} what="이력을 불러오지 못했어요" />
      </Page>
    );
  return (
    <Page eyebrow="관리자" title="변경 이력" lead="화면에서 고친 내용과 올린 파일의 미리보기·반영 결과예요. 누르면 그때 바뀐 내용을 볼 수 있어요.">
      <UploadList list={q.data} />
    </Page>
  );
}
