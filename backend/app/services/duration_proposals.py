"""자료 ID 기준 일정. 스킬 구간은 겹칠 수 있으므로 전체 기간과 구분한다."""
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from hashlib import sha256
import json
import math

from app.agents.resource_recommendations import (
    RecommendationError, validate_choices, validate_skill_order,
)

METHOD = 'resource-hours-books/v3'


def positive(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _courses(choice: dict) -> list[str]:
    return list(dict.fromkeys(choice.get('courses') or ([choice['course']] if choice.get('course') else [])))


def _time(course: dict, weekly: float) -> tuple[float, str]:
    hours = positive(course.get('hours'))
    status = course.get('timeStatus')
    if hours is None or status == 'unknown':
        return weekly, 'unknown'
    estimated = 'hours' in (course.get('estimated') or []) or status == 'estimated'
    return hours, 'estimated' if estimated else 'confirmed'


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def resource_schedule(recommendations: dict, choices: dict, order: list[str], weekly_hours) -> dict:
    """첫 참조에 자료를 배정하고 이후 참조는 같은 구간을 사용한다.

    올림은 누적 작업량에만 적용한다. 도서는 고유 ID당 1주이며, 주 중간에
    시작한 자료의 달력 구간은 그 작업량보다 길 수 있다.
    """
    weekly = positive(weekly_hours)
    if weekly is None:
        raise RecommendationError('주당 학습시간을 확인해 주세요.')
    by_name = {row['name']: row for row in recommendations['skills']}
    active = [name for name in order if choices[name].get('enabled', True)]
    selection = {name: {'enabled': choices[name].get('enabled', True),
                        'courses': _courses(choices[name]), 'books': sorted(choices[name]['books'])}
                 for name in order}
    context = {'skillOrder': list(order), 'selection': selection, 'weeklyHours': weekly}
    key = sha256(json.dumps([METHOD, recommendations.get('id'), context], ensure_ascii=False,
                            sort_keys=True).encode()).hexdigest()
    # 동일 ID의 카드가 다르면 확인된 근거를 우선하고 같은 등급에서는 큰 값을 쓴다.
    times = {}
    rank = {'unknown': 0, 'estimated': 1, 'confirmed': 2}
    for name in active:
        selected = set(_courses(choices[name]))
        for course in by_name[name]['courses']:
            if course['id'] in selected:
                value = _time(course, weekly)
                if course['id'] not in times or (rank[value[1]], value[0]) > (rank[times[course['id']][1]], times[course['id']][0]):
                    times[course['id']] = value
        if not selected <= times.keys():
            raise RecommendationError('선택한 강좌의 시간 근거를 확인해 주세요.')
    budget = Decimal(str(weekly))
    cursor = 0
    course_slots, book_slots, skill_book_slots, estimates = {}, {}, {}, {}
    course_counts = {}
    for name in active:
        for rid in _courses(choices[name]):
            course_counts[rid] = course_counts.get(rid, 0) + 1

    def allocate_weeks(weeks_count: int) -> dict:
        nonlocal cursor
        start = cursor + 1
        cursor += weeks_count
        return {'startWeek': start, 'endWeek': cursor}

    for name in active:
        before = cursor
        choice = choices[name]
        slots = []
        course_added = 0
        for rid in _courses(choice):
            if rid not in course_slots:
                hours, status = times[rid]
                base_weeks = max(1, _ceil(Decimal(str(hours)) / budget))
                extra_weeks = 1 if course_counts.get(rid, 0) > 1 else 0
                w = base_weeks + extra_weeks
                course_slots[rid] = dict(allocate_weeks(w), id=rid,
                                         hours=None if status == 'unknown' else hours, timeStatus=status)
                course_added += w
            slots.append(course_slots[rid])
        book_added = 0
        own_slots = []
        for rid in sorted(choice['books']):
            slot = dict(allocate_weeks(1), id=rid)
            book_slots.setdefault(rid, slot)
            skill_book_slots[(name, rid)] = slot
            slots.append(slot)
            own_slots.append(slot)
            book_added += 1
        for rid in _courses(choice):
            if course_counts.get(rid, 0) <= 1 or course_added > 0:
                own_slots.append(course_slots[rid])
        window_slots = own_slots or slots
        start = min((slot['startWeek'] for slot in window_slots), default=None)
        end = max((slot['endWeek'] for slot in window_slots), default=None)
        unknown = [rid for rid in _courses(choice) if times[rid][1] == 'unknown']
        estimated = [rid for rid in _courses(choice) if times[rid][1] == 'estimated']
        note = f'시간 미확인 {len(unknown)}개(각 1주 가정)' if unknown else ''
        if estimated:
            note = ' · '.join(filter(None, [note, f'추정 시간 {len(estimated)}개 포함']))
        estimates[name] = {**deepcopy(context), 'weeks': end - start + 1 if window_slots else 0,
                           'startWeek': start, 'endWeek': end,
                           'addedWeeks': cursor - before,
                           'courseWeeks': course_added, 'bookWeeks': book_added,
                           'basis': ' · '.join(filter(None, ['강좌 ID별 시간 1회 합산 후 전체 올림 + 도서 ID별 1주', note])),
                           'method': METHOD, 'scheduleKey': key,
                           'course': choice.get('course'), 'courses': _courses(choice),
                           'books': sorted(choice['books']), 'unknownCourses': unknown, 'estimatedCourses': estimated,
                           'resources': deepcopy(slots)}
    total = cursor
    for estimate in estimates.values():
        estimate['totalWeeks'] = total
    return {'estimates': estimates, 'weeks': total, 'courses': course_slots, 'books': book_slots, 'skillBooks': skill_book_slots}


def calculate_durations(project, recommendations, choices, order, weekly_hours):
    validate_choices(recommendations, choices)
    validate_skill_order(recommendations, order)
    if any('courses' in choice and choice['courses'] != ([choice['course']] if choice.get('course') else [])
           for choice in choices.values()):
        raise RecommendationError('추천 자료에서는 스킬별 강좌 한 개만 선택할 수 있습니다.')
    weekly = positive((project.get('details') or {}).get('hours')) or positive(weekly_hours)
    return resource_schedule(recommendations, choices, order, weekly)['estimates']


def material_duration(courses, books, weekly_hours):
    """독립 자료 묶음도 전체 일정과 같은 계산 규칙을 사용한다."""
    choice = {'course': courses[0]['id'] if courses else None,
              'courses': [item['id'] for item in courses], 'books': [item['id'] for item in books]}
    return resource_schedule({'skills': [{'name': 'materials', 'courses': courses, 'books': books}]},
                             {'materials': choice}, ['materials'], weekly_hours)['estimates']['materials']


def schedule_rows(estimates: dict) -> list[dict]:
    return [{'skill': name, 'weeks': row['weeks'], 'startWeek': row.get('startWeek'),
             'endWeek': row.get('endWeek'), 'addedWeeks': row.get('addedWeeks'),
             'totalWeeks': row.get('totalWeeks')} for name, row in estimates.items()]


def apply_plan_schedule(plan: dict) -> dict:
    """build_plan의 마지막에 호출. 기존 확정 기록을 읽거나 변경하지 않는다."""
    option = plan.get('def') or {}
    report = option.get('learningReport')
    if 'materialSchedule' not in option or not isinstance(report, dict) or not report.get('recommendations'):
        return plan
    # build_plan의 def는 호출자의 option과 같은 객체일 수 있다.
    plan = deepcopy(plan)
    option = plan['def']
    report = option['learningReport']
    schedule = resource_schedule(report['recommendations'], report['choices'], report['skillOrder'], plan['hours'])
    plan['acts'] = [activity for activity in plan['acts']
                    if report['choices'].get(activity.get('skill'), {}).get('enabled', True)]
    report['durationEstimates'] = schedule['estimates']
    option['materialSchedule'] = schedule_rows(schedule['estimates'])
    plan['weeks'] = schedule['weeks']
    seen_courses = set()
    seen_books = set()
    seen_other = set()
    material_hours = Decimal(0)
    task_hours = Decimal(0)
    other_material_hours = Decimal(0)
    for activity in plan['acts']:
        name, rid = activity.get('skill'), activity.get('res')
        resource_slot = schedule['courses'].get(rid) or schedule.get('skillBooks', {}).get((name, rid)) or schedule['books'].get(rid)
        slot = resource_slot
        slot = slot or schedule['estimates'].get(name)
        if slot:
            activity['wFrom'] = slot['startWeek'] or max(1, plan['weeks'])
            activity['wTo'] = slot['endWeek'] or activity['wFrom']
            if resource_slot:
                activity['resourceWindow'] = {'from': slot['startWeek'], 'to': slot['endWeek']}
            if slot.get('timeStatus'):
                activity['hoursEstimated'] = slot['timeStatus'] != 'confirmed'
                activity['timeStatus'] = slot['timeStatus']
                if slot.get('hours') is not None:
                    activity['hours'] = slot['hours']
                else:
                    activity['hours'] = plan['hours']
                    activity['hoursBasis'] = '강좌 시간 미확인: 일정 계산용으로 1주 배정'
            if rid in schedule['books']:
                # 카탈로그 참고 시간과 이 계획에서 배정한 시간은 서로 다른 값이다.
                activity.setdefault('catalogHours', activity.get('hours'))
                activity['hours'] = plan['hours']
                activity['hoursAllocation'] = 'book-week'
                activity['hoursEstimated'] = True
                activity['hoursBasis'] = '도서 1권당 1주 배정(주당 학습시간 기준), 실제 독서시간 아님'
        if rid in schedule['courses']:
            if rid in seen_courses:
                continue
            seen_courses.add(rid)
            hours = activity['hours']
        elif rid in schedule['books']:
            if rid in seen_books:
                continue
            seen_books.add(rid)
            hours = plan['hours']
        elif not rid:
            task_hours += Decimal(str(positive(activity.get('hours')) or 0))
            continue
        else:
            # 자격증 등 자료 일정에 없는 자료도 과제로 오인하거나 총합에서 버리지 않는다.
            if rid not in seen_other:
                seen_other.add(rid)
                other_material_hours += Decimal(str(positive(activity.get('hours')) or 0))
            continue
        if hours is not None:
            material_hours += Decimal(str(hours))
    plan['materialHours'] = float(material_hours)
    plan['taskHours'] = float(task_hours)
    plan['otherMaterialHours'] = float(other_material_hours)
    plan['totalH'] = float(material_hours + task_hours + other_material_hours)
    plan['totalHUnknown'] = any(row['timeStatus'] == 'unknown' for row in schedule['courses'].values())
    plan['totalHEstimated'] = any(activity.get('hoursEstimated') for activity in plan['acts'])
    plan['durationBasis'] = 'materials-only'
    return plan
