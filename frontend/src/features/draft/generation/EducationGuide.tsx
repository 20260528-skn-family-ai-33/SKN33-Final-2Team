import { useQuery } from '@tanstack/react-query';
import { draftsApi } from '@/api/endpoints/drafts';
import type { EducationGuide as Guide } from '@/api/types/draft';
import { useWs } from '@/shared/state/workspace';

export function EducationGuide({ saved }: { saved?: Guide }) {
  const draftId = useWs(s => s.draftId);
  const owner = useWs(s => s.owner);
  const query = useQuery({
    queryKey: ['education-guide', owner, draftId],
    queryFn: () => draftsApi.educationGuide(draftId!),
    enabled: !!draftId && !saved,
    staleTime: Infinity,
    retry: false,
  });
  const guide = saved ?? query.data;
  const basis = guide?.basis;
  return (
    <section className="card flat" aria-label="교육비 규정 안내">
      <h3>교육비 규정 안내</h3>
      {basis ? <>
        <p>
          {basis.version === '22차' && '국내 위탁교육비는 별도로 정한 기준에 따라 지급돼요. '}
          수강하려는 강좌가 지원 대상인지, 얼마까지 지원받을 수 있는지는 교육담당자에게 확인해 주세요.
        </p>
        <details>
          <summary>규정 원문 보기 · {basis.name} {basis.article} · {basis.version}{basis.page != null && <> · {basis.page}쪽</>}</summary>
          <blockquote>{basis.text}</blockquote>
        </details>
      </> : <p role="status">{guide ? '직원 구분에 해당하는 국내 위탁교육 조항을 찾지 못했어요. 교육비 지원 기준은 교육담당자에게 확인해 주세요.'
        : query.isError ? '교육비 규정을 불러오지 못했어요. 지원 기준은 교육담당자에게 확인해 주세요.' : '교육비 규정을 확인하고 있어요.'}</p>}
    </section>
  );
}
