"""강좌 시간÷주당 시간(올림) + 도서 권당 1주. 모델 호출 없음."""
import math
from app.agents.resource_recommendations import validate_choices, validate_skill_order, RecommendationError
METHOD='course-hours-books/v1'

def positive(value):
    if isinstance(value,bool):return None
    try:number=float(value)
    except (ValueError,TypeError):return None
    return number if math.isfinite(number) and number>0 else None

def calculate_durations(project,recommendations,choices,order,weekly_hours):
    validate_choices(recommendations,choices)
    validate_skill_order(recommendations,order)
    weekly=positive((project.get('details') or {}).get('hours')) or positive(weekly_hours)
    if weekly is None:raise RecommendationError('주당 학습시간을 확인해 주세요.')
    by_name={row['name']:row for row in recommendations['skills']}
    result={}
    for name in order:
        choice=choices[name]
        if choice.get('enabled',True) is False:continue
        course=next((row for row in by_name[name]['courses'] if row['id']==choice['course']),None)
        hours=positive((course or {}).get('hours')) if 'hours' not in ((course or {}).get('estimated') or []) else None
        course_weeks=(max(1,math.ceil(hours/weekly)) if hours else 1) if course else 0
        book_weeks=len(choice['books'])
        result[name]={'weeks':course_weeks+book_weeks,'courseWeeks':course_weeks,'bookWeeks':book_weeks,'weeklyHours':weekly,
            'basis':f"강좌 {course_weeks}주 + 도서 {book_weeks}권 × 1주",'method':METHOD,'course':choice['course'],'books':sorted(choice['books'])}
    # Selection estimates remain informative; period policy is handled during recommendation.
    return result


def material_duration(courses, books, weekly_hours):
    """자료 활동만의 기간. 추가된 여러 강좌도 같은 규칙으로 합산한다."""
    weekly = positive(weekly_hours)
    if weekly is None:
        raise RecommendationError('주당 학습시간을 확인해 주세요.')
    course_weeks = 0
    for course in courses:
        hours = positive(course.get('hours')) if 'hours' not in (course.get('estimated') or []) else None
        course_weeks += max(1, math.ceil(hours / weekly)) if hours else 1
    book_weeks = len(books)
    return {'weeks': course_weeks + book_weeks, 'courseWeeks': course_weeks,
            'bookWeeks': book_weeks, 'weeklyHours': weekly,
            'basis': f'강좌 {course_weeks}주 + 도서 {book_weeks}권 × 1주', 'method': METHOD,
            'course': courses[0]['id'] if courses else None,
            'courses': [item['id'] for item in courses], 'books': sorted(item['id'] for item in books)}


def period_limit(project, course=None):
    details = project.get('details') or {}
    course = course or project.get('selectedCourse') or {}
    limits = [value for value in (positive(details.get('weeks')), positive((course or {}).get('weeks'))) if value]
    return min(limits) if limits else None


def course_fits_period(item, project, course=None):
    limit = period_limit(project, course)
    weekly = positive((project.get('details') or {}).get('hours')) or positive((course or {}).get('weeklyHours'))
    hours = positive(item.get('hours'))
    # 미확인·추정 시간을 확정된 짧은 강좌로 간주하지 않는다. 기존 추정 표시는 유지한다.
    if not limit or not weekly or not hours or 'hours' in (item.get('estimated') or []):
        return True
    return math.ceil(hours / weekly) <= limit
