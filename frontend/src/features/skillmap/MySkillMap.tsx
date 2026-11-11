/* 내 스킬 지도(누적) — 점검·보고서 화면과 내 정보 화면 (시제품)
   확정한 로드맵 전체에서 스킬별 뱃지(브론즈·실버·골드)와 학습한 횟수를 뽑아 스킬 지도 위에 보여 준다.
   그리는 틀은 스킬 지도(SkillMap.tsx 의 MapBox)를 그대로 쓰고, 뱃지 계산은 earned.ts 에 둔다 */
import type { SkillMapData } from '@/api/types/catalog';
import { paths } from '@/app/paths';
import { matchingCertificates } from '@/features/roadmap/roadmapLearningData';
import { useGo } from '@/shared/hooks/useGo';
import { useCatalog } from '@/shared/state/catalog';
import { useMe } from '@/shared/state/session';
import { recs, useWs } from '@/shared/state/workspace';
import { Icon } from '@/shared/ui/Icon';
import { Note } from '@/shared/ui/parts';
import { earnedSkills, isEarned, LEVEL_TEXT, medalOf, type SkillMark } from './earned';
import { relOf } from './layout';
import { MapBox } from './SkillMap';

function MyInfo({ data, picked, marks, onClose }: { data: SkillMapData; picked: number | null; marks: Map<number, SkillMark>; onClose: () => void }) {
  const certificates = useCatalog((state) => state.certById);
  const me = useMe();
  const go = useGo();
  const s = picked == null ? undefined : data.skills.find((x) => x.id === picked);
  if (picked == null || !s) return <p className="small muted">스킬 점을 누르면 이 스킬을 어느 로드맵에서 배웠는지와 선수 관계를 보여 줘요.</p>;
  const { parents, kids } = relOf(data);
  const mark = marks.get(picked);
  const certs = matchingCertificates(Object.values(certificates), [s.name], me?.certs);
  const names = (ids?: number[]) =>
    ids && ids.length ? ids.map((id) => data.skills.find((x) => x.id === id)?.name || '').join(', ') : <span className="muted">없어요</span>;
  return (
    <>
      <div className="sm-pick-h">
        <b>{s.name}</b>
        <span className="tag">{s.category}</span>
        <span className={`tag ${mark ? 'acc' : 'line'}`}>{mark ? LEVEL_TEXT[mark.level] : '시작 전'}</span>
        {mark && mark.plans.length > 1 ? <span className="tag line">{mark.plans.length}회 학습</span> : null}
        <button className="link quiet" aria-label="설명 닫기" onClick={onClose}>
          <Icon name="x" />
        </button>
      </div>
      <dl className="kv sm-kv">
        <dt>먼저 배울 스킬</dt>
        <dd>{names(parents[picked])}</dd>
        <dt>이어지는 스킬</dt>
        <dd>{names(kids[picked])}</dd>
        <dt>추천 자격증</dt>
        <dd>{certs.length ? certs.map((cert) => cert.name).join(', ') : '일치하는 자격증이 없어요.'}</dd>
        <dt>내 로드맵</dt>
        <dd>
          {mark?.plans.length ? (
            mark.plans.map((plan, i) => (
              <span key={plan.id}>
                {i ? <br /> : null}
                <button className="link" onClick={() => go(paths.roadmap(plan.id))}>
                  {plan.title}
                </button>{' '}
                · {LEVEL_TEXT[plan.level]}
                {plan.quiz ? ` · 사후 퀴즈 ${plan.quiz.post}/${plan.quiz.count}` : ''}
              </span>
            ))
          ) : (
            <span className="muted">아직 이 스킬을 다룬 로드맵이 없어요.</span>
          )}
        </dd>
      </dl>
    </>
  );
}

export function MySkillMap() {
  const me = useMe();
  const plans = useWs((s) => s.plans);
  const reports = useWs((s) => s.reports);
  const resources = useCatalog((s) => s.res);
  // 확정한 로드맵이 없어도 지도는 그린다(내 정보 화면에서 채워 갈 스킬을 미리 볼 수 있게)
  const records = recs({ plans });
  return (
    <MapBox
      id="mySmBox"
      title="내 스킬 지도"
      viewKey="mine"
      wheelZoom
      build={(data, pid) => {
        const { marks, unmatched } = earnedSkills(data, records, reports, resources);
        const owned = new Set((me?.tech || []).map((name) => name.trim()));
        for (const skill of data.skills) {
          if (owned.has(skill.name.trim())) {
            marks.set(skill.id, { level: 'gold', plans: marks.get(skill.id)?.plans || [] });
          }
        }
        const draft = data.prerequisiteSource !== 'db';
        const medals = [...marks.values()].map(medalOf);
        const countOf = (medal: string) => medals.filter((m) => m === medal).length;
        const earned = medals.filter(Boolean).length;
        return {
          label: '내 스킬 지도: 팀 DB 스킬과 선수 관계, 내가 뱃지를 받았거나 배우는 중인 스킬 표시',
          sum: (
            <>
              팀 DB 스킬 {data.skills.length}개 가운데 <b>{earned}개</b>에 뱃지가 있고(골드 {countOf('gold')} · 실버 {countOf('silver')} · 브론즈 {countOf('bronze')}){' '}
              <b>{marks.size - earned}개</b>를 배우는 중이에요.
            </>
          ),
          keys: (
            <>
              <span>
                <i className="k-gold" />
                골드 · 보유 스킬 또는 사후 퀴즈 모두 정답
              </span>
              <span>
                <i className="k-silver" />
                실버 · 사후 퀴즈 3문항 중 2개
              </span>
              <span>
                <i className="k-bronze" />
                브론즈 · 활동 모두 완료
              </span>
              <span>
                <i className="k-cov" />
                학습 중
              </span>
              <span>
                <i className="k-e" />
                지나온 길
              </span>
            </>
          ),
          look: (skillId) => {
            const mark = marks.get(skillId);
            if (!mark) return { cls: 'off' };
            const times = mark.plans.length;
            const medal = medalOf(mark);
            return { cls: 'cov', tag: times > 1 ? `${times}회` : '', aria: ` · ${LEVEL_TEXT[mark.level]}${times > 1 ? ` · ${times}회 학습` : ''}`, ring: !medal, medal };
          },
          edge: (from, to) => (isEarned(marks.get(from)) && marks.has(to) ? 'trail' : ''),
          info: (close) => <MyInfo data={data} picked={pid} marks={marks} onClose={close} />,
          notes: (
            <>
              {marks.size ? null : (
                <Note>
                  아직 뱃지를 받았거나 배우는 중인 스킬이 없어요. {records.length ? '활동을 완료로 기록하면' : '로드맵을 확정하고 활동을 완료로 기록하면'} 지도에 채워져요.
                </Note>
              )}
              <details className="handoff" style={{ marginBottom: '3pt' }}>
                <summary style={{ color: 'var(--ink-3)', fontSize: 13 }}><span aria-hidden="true">•</span>참고사항</summary>
                <Note>
                  브론즈는 그 스킬의 활동(도서 제외)을 모두 완료로 기록했을 때, 실버와 골드는 결과 보고서 학습 점검의 사후 퀴즈에서 그 스킬 문항의 3분의 2 이상 또는 전부를 맞힌 적이 있을
                  때 표시해요. 내 정보에 등록한 보유 스킬도 골드로 표시해요. 꼬리표의 숫자는 그 스킬을 배운 로드맵 수예요(한 번이면 표시하지 않아요). 내가 기록한 학습 이력이에요. 역량 판정이나 인사평가에 쓰지 않아요.
                </Note>
                {draft ? (
                  <Note>선수 관계 {data.prerequisites.length}개는 팀 DB에 아직 없어 임시 초안(가정)으로 그렸어요. 팀 검토 전에는 참고로만 봐 주세요.</Note>
                ) : null}
              </details>
              {unmatched.length ? (
                <Note>
                  로드맵의 스킬 {unmatched.length}개는 팀 DB 스킬 이름과 맞지 않아 지도에 표시하지 못했어요({unmatched.join(', ')}).
                </Note>
              ) : null}
            </>
          ),
        };
      }}
    />
  );
}
