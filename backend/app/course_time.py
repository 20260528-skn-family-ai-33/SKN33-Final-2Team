"""Provider duration vs explicit curriculum planning allowance; preserve manual edits."""
import math


def display_hours(value) -> str:
    """표시만 10분 단위로 반올림한다. 일정 계산·저장용 숫자는 바꾸지 않는다."""
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return '시간 미확인'
    if not math.isfinite(hours) or hours < 0:
        return '시간 미확인'
    if hours == 0:
        return '0시간'
    if hours < 5 / 60:
        return '10분 미만'
    # Python round의 짝수 반올림 대신 프런트 Math.round와 같은 양수 절반 올림.
    minutes = max(10, math.floor(hours * 6 + 0.5) * 10)
    h, m = divmod(minutes, 60)
    return ' '.join(part for part in (f'{h}시간' if h else '', f'{m}분' if m else '') if part)


def effective(course: dict, meta: dict) -> dict:
    estimated = list(meta.get('estimated_fields') or [])
    origin = meta.get('hours_origin') or 'legacy'
    manual = origin == 'manual' or (origin == 'legacy' and meta.get('hours') is not None and 'hours' not in estimated)
    proof = course.get('duration_provenance') or {}
    seconds = course.get('duration_seconds')
    if manual and meta.get('hours') is not None:
        hours, status, kind = float(meta['hours']), 'manual', 'manual'
        note = '관리자가 확인·입력한 계획 시간입니다.'
    elif seconds is not None:
        hours, status, kind = seconds / 3600, 'confirmed', course.get('duration_kind')
        note = '제공처의 영상 총시간입니다. 복습·실습 시간은 별도입니다.' if kind == 'video' else '제공처의 학습 시간입니다. 영상 재생시간과 다를 수 있습니다.'
    else:
        hours, status, kind = (course.get('estimated_duration_seconds') or 7200) / 3600, 'estimated', None
        count = proof.get('lesson_count')
        missing = proof.get('missing_video_durations')
        minutes = proof.get('minutes_per_lesson')
        if count:
            label = '전체 목차' if proof.get('curriculum_lesson_count') else '공개 차시 묶음'
            note = f'총시간 미확보 · {label} {count}개 × 학습 {minutes}분을 가정한 계획용 추정입니다. 실제 재생시간과 다를 수 있습니다.'
        elif missing:
            imputed = proof.get('imputed_video_seconds')
            if imputed and proof.get('observed_video_count'):
                note = f'총시간 일부 미확보 · 확인된 영상 합계에 누락 영상 {missing}개의 시간을 같은 강좌 영상 길이의 중앙값으로 보완한 계획용 추정입니다.'
            else:
                note = '총시간 미확보 · 영상별 초기 계획 시간을 가정한 추정입니다. 실제 재생시간과 다를 수 있습니다.'
        else:
            note = '총시간·차시 수 미확보 · 일정 작성을 위한 초기 계획 시간입니다. 강좌 확인 후 조정해 주세요.'
    estimated = [field for field in estimated if field != 'hours']
    if status == 'estimated':estimated.append('hours')
    return {'hours': hours, 'timeStatus': status, 'durationKind': kind,
            'durationSeconds': seconds if not manual else None,
            'timeNote': note, 'estimated': estimated}


def sync(t=None):
    """Refresh catalog-controlled values on repeated setup; never replace manual hours."""
    if t is None:
        from . import db
        with db.tx() as transaction:
            return sync(transaction)
    t.run("""UPDATE app_ext.resource_meta SET hours_origin='manual' WHERE resource_type='course'
        AND hours_origin='legacy' AND hours IS NOT NULL AND NOT estimated_fields ? 'hours'""")
    return t.run("""UPDATE app_ext.resource_meta m SET
        hours=coalesce(c.duration_seconds,c.estimated_duration_seconds,7200)::numeric/3600,
        hours_origin='catalog',
        estimated_fields=(SELECT coalesce(jsonb_agg(x),'[]'::jsonb) FROM jsonb_array_elements_text(m.estimated_fields) x WHERE x<>'hours')
            || CASE WHEN c.duration_seconds IS NULL THEN '["hours"]'::jsonb ELSE '[]'::jsonb END
        FROM public.courses c WHERE m.course_id=c.course_id AND m.resource_type='course' AND m.hours_origin<>'manual'""")
