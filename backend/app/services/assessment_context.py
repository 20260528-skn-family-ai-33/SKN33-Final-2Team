"""원본 점검 기록을 변경하지 않는 로드맵 전용 측정 결과 전달본."""
from copy import deepcopy

VERSION = 'assessment-evidence/v1'


def compact(assessment):
    if not isinstance(assessment, dict) or assessment.get('version') == VERSION:
        return deepcopy(assessment)
    groups, answers = assessment.get('groups'), assessment.get('answers')
    if not isinstance(groups, list) or not groups or not isinstance(answers, dict):
        return deepcopy(assessment)
    if set(assessment) - {'groups', 'answers'}:
        return deepcopy(assessment)
    result, ids = [], set()
    # 알 수 없는 구형 형식은 원문 전달. 유효한 일부만 골라 누락시키지 않는다.
    try:
        for group in groups:
            if not isinstance(group.get('skill'), str) or set(group) - {'skill', 'title', 'surveys', 'quizzes'}:
                raise ValueError()
            surveys, quizzes = [], []
            for row in group['surveys']:
                if set(row) - {'id', 'text'} or row['id'] in ids:
                    raise ValueError()
                ids.add(row['id'])
                value = answers.get(row['id'])
                if not isinstance(row.get('text'), str) or (value is not None and (type(value) is not int or not 1 <= value <= 5)):
                    raise ValueError()
                surveys.append({'measure': row['text'], 'selfRating': value})
            for row in group['quizzes']:
                if set(row) - {'id','q','options','answer','explain','concept','questionType','difficulty'} or row['id'] in ids:
                    raise ValueError()
                ids.add(row['id'])
                options, correct = row['options'], row['answer']
                selected = answers.get(row['id'])
                if (not isinstance(options, list) or not options or not all(isinstance(x, str) for x in options)
                        or type(correct) is not int or not 0 <= correct < len(options)
                        or (selected is not None and (type(selected) is not int or not 0 <= selected < len(options)))):
                    raise ValueError()
                concept = row.get('concept') or row.get('q')
                if not isinstance(concept, str) or not concept.strip():
                    raise ValueError()
                item = {'concept': concept, 'questionType': row.get('questionType'), 'difficulty': row.get('difficulty'),
                        'result': 'unanswered' if selected is None else 'correct' if selected == correct else 'incorrect'}
                if selected != correct:
                    item.update(selectedAnswer=options[selected] if selected is not None else None,
                                correctAnswer=options[correct], reason=row.get('explain') or '')
                quizzes.append(item)
            result.append({'skill': group['skill'], 'surveys': surveys, 'quizzes': quizzes})
        if set(answers) - ids:
            raise ValueError()
    except (KeyError, TypeError, IndexError, ValueError, AttributeError):
        return deepcopy(assessment)
    return {'version': VERSION, 'skills': result}
