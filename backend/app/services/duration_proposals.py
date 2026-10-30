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
    return result
