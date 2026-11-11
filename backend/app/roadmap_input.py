"""로드맵 모델용 입력 투영. 저장 원문은 바꾸거나 길이로 자르지 않는다."""
from __future__ import annotations

from copy import deepcopy

from .track_policy import MAX_SKILLS


def skill_reference(handoff: dict) -> list[str] | None:
    names, order = handoff.get('skillNames'), handoff.get('skillOrder')
    for value in (names, order):
        if value is not None and (not isinstance(value, list) or any(not isinstance(name, str) for name in value)):
            raise ValueError('선정 스킬은 이름 목록이어야 합니다.')
    if handoff.get('selectedSkillsFixed'):
        if names is not None and order is not None and (set(names) != set(order) or len(names) != len(order)):
            raise ValueError('확정한 스킬 목록과 순서가 일치하지 않습니다. 스킬을 다시 선택하고 순서를 확인해 주세요.')
        return order if order is not None else names
    if names is None:
        return order
    return list(dict.fromkeys([name for name in order or [] if name in names] + names))


def cap_skills(handoff: dict) -> dict:
    """이전 상한으로 저장된 4~5개 handoff는 사용자 순서의 앞 3개만 모델 입력에 쓴다. 원본은 바꾸지 않는다."""
    try:
        order = skill_reference(handoff) or []
    except ValueError:
        return handoff  # 형식 오류는 기존 검사 위치에서 같은 오류로 알린다.
    if len(order) <= MAX_SKILLS:
        return handoff
    keep, dropped = order[:MAX_SKILLS], order[MAX_SKILLS:]
    capped = deepcopy(handoff)
    for field in ('skillNames', 'skillOrder', 'focus', 'coreSkills'):
        if isinstance(capped.get(field), list):
            capped[field] = [name for name in capped[field] if name not in dropped]
    if isinstance(capped.get('skillDetails'), list):
        capped['skillDetails'] = [row for row in capped['skillDetails'] if not isinstance(row, dict) or row.get('name') not in dropped]
    materials = capped.get('skillMaterials') if isinstance(capped.get('skillMaterials'), dict) else {}
    gone = {rid for name in dropped for rid in [(materials.get(name) or {}).get('course')] + list((materials.get(name) or {}).get('books') or []) if rid}
    gone -= {rid for name in keep for rid in [(materials.get(name) or {}).get('course')] + list((materials.get(name) or {}).get('books') or []) if rid}
    for field in ('skillMaterials', 'durationEstimates'):
        if isinstance(capped.get(field), dict):
            capped[field] = {name: value for name, value in capped[field].items() if name not in dropped}
    if isinstance(capped.get('resourceHints'), list):
        capped['resourceHints'] = [rid for rid in capped['resourceHints'] if rid not in gone]
    capped['excludedSkills'] = list(dict.fromkeys(list(capped.get('excludedSkills') or []) + dropped))
    return capped


def synchronize_skills(handoff: dict, skills: list[str]) -> None:
    """현재 이름으로 검증된 동일 이름만 연결한다. 옛 이름의 상세를 새 스킬에 전용하지 않는다."""
    old = set(handoff.get('skillNames') or []) | set(handoff.get('skillOrder') or [])
    handoff['skillNames'] = list(skills)
    handoff['skillOrder'] = list(skills)
    if 'coreSkills' in handoff:
        handoff['coreSkills'] = list(skills)
    if 'focus' in handoff:
        # 구판 focus에 사람이 적은 수행 목표가 들어 있으면 이름 정리로 지우지 않는다.
        handoff['focus'] = ([name for name in handoff['focus'] if name not in old or name in skills]
                            if not (handoff.get('courseSkillSelection') or handoff.get('selectedSkillsFixed')) else list(skills))
    if 'skillDetails' in handoff:
        by_name = {row['name']: row for row in handoff['skillDetails'] if isinstance(row, dict) and row.get('name') in skills}
        handoff['skillDetails'] = [by_name[name] for name in skills if name in by_name]
    if handoff.get('courseSkillSelection') and not handoff.get('selectedSkillsFixed'):
        by_name = {row['name']: row for row in handoff.get('skillDetails') or []}
        missing = [name for name in skills if name not in by_name]
        # 이름만 재추정했을 뿐 옛 스킬의 적용 범위·점검 근거가 새 스킬의 증거는 아니다.
        handoff['skillDetails'] = [by_name.get(name, {'name': name}) for name in skills]
        if missing:
            handoff['inferredSkillNames'] = missing
    for field in ('skillMaterials', 'durationEstimates'):
        if isinstance(handoff.get(field), dict):
            handoff[field] = {name: handoff[field][name] for name in skills if name in handoff[field]}
    if 'excludedSkills' in handoff:
        handoff['excludedSkills'] = [name for name in handoff['excludedSkills'] if name not in skills]


def assessment_evidence(assessment: dict) -> dict:
    """오답 보기 전체 대신 실제 선택·정답·문맥을 남긴다. 미응답은 오답이 아니다."""
    answers = assessment.get('answers') or {}
    used, groups = set(), []
    for group in assessment.get('groups') or []:
        result = {'skill': group.get('skill'), 'surveys': [], 'quizzes': []}
        for row in group.get('surveys') or []:
            key = row.get('id')
            used.add(key)
            result['surveys'].append({'text': row.get('text'), 'rating': answers.get(key)})
        for row in group.get('quizzes') or []:
            key = row.get('id')
            used.add(key)
            chosen, expected = answers.get(key), row.get('answer')
            options = row.get('options') or []
            valid = lambda value: type(value) is int and 0 <= value < len(options)
            quiz = {key: deepcopy(row[key]) for key in ('q', 'concept', 'difficulty') if key in row}
            # 유형·ID·선택하지 않은 오답은 학습 편성에 필요하지 않다.
            quiz['chosen'] = options[chosen] if valid(chosen) else deepcopy(chosen)
            quiz['expected'] = options[expected] if valid(expected) else deepcopy(expected)
            quiz['correct'] = chosen == expected if valid(chosen) and valid(expected) else None
            if quiz['correct'] is not True and row.get('explain'):
                quiz['explain'] = row['explain']
            result['quizzes'].append(quiz)
        groups.append(result)
    result = {'groups': groups}
    # 구판/확장 응답에 실제 자유 입력이 있으면 문항 ID 매칭 실패로 유실시키지 않는다.
    additional = {key: deepcopy(value) for key, value in answers.items() if key not in used}
    if additional:
        result['additionalAnswers'] = additional
    result.update({key: deepcopy(value) for key, value in assessment.items() if key not in ('groups', 'answers')})
    return result


def project(payload: dict, *, compact_assessment: bool = False) -> dict:
    """생성·재생성·수정의 공통 전달 형식. 알 수 없는 개인 입력 필드는 보존한다."""
    result = deepcopy(payload)
    handoff = result['handoff']
    if compact_assessment and 'assessment' in handoff:
        from app.services.assessment_context import compact
        handoff['assessment'] = compact(handoff['assessment'])
    elif isinstance(handoff.get('assessment'), dict) and 'groups' in handoff['assessment'] and 'answers' in handoff['assessment']:
        handoff['assessment'] = assessment_evidence(handoff['assessment'])
        if 'skillNames' in handoff:
            groups = handoff['assessment']['groups']
            unmatched = [dict(group, priorSkill=group['skill']) for group in groups if group['skill'] not in handoff['skillNames']]
            if unmatched:
                for group in unmatched:
                    del group['skill']
                handoff['assessment']['unmatchedGroups'] = unmatched
                handoff['assessment']['groups'] = [group for group in groups if group['skill'] in handoff['skillNames']]
    # 현행 압축 결과도 실제 소속을 확인한다. 새 스킬로 과거 점검 근거 전용 금지.
    assessment = handoff.get('assessment')
    if isinstance(assessment, dict) and assessment.get('version') == 'assessment-evidence/v1':
        names = handoff.get('skillNames', handoff.get('skillOrder'))
        if names is not None:
            groups = assessment['skills']
            unmatched = [dict(group, priorSkill=group['skill']) for group in groups if group['skill'] not in names]
            if unmatched:
                for group in unmatched:
                    del group['skill']
                assessment['unmatchedSkills'] = unmatched
                assessment['skills'] = [group for group in groups if group['skill'] in names]
    knowledge = handoff.get('learnerKnowledge') or result.get('learnerKnowledge') or {}
    hr = handoff.get('hrContext') or {}
    profile = handoff.get('profile')
    if isinstance(profile, dict):
        # 중복임이 값으로 확인된 필드만 정규 위치(learnerKnowledge/hrContext)에 남긴다.
        aliases = {'dept': 'department', 'parentDept': 'parentDepartment'}
        for key in list(profile):
            target = aliases.get(key, key)
            if target in hr and profile[key] == hr[target]:
                del profile[key]
        aliases = {'tech': 'technologies', 'techStack': 'technologies', 'technologies': 'technologies',
                   'certs': 'certifications', 'certifications': 'certifications', 'learning': 'learning'}
        for source in (profile, profile.get('self') or {}):
            for key, target in aliases.items():
                if key in source and source[key] == knowledge.get(target):
                    del source[key]
    if result.get('learnerKnowledge') == handoff.get('learnerKnowledge'):
        result.pop('learnerKnowledge', None)
    # 목표 원문과 다른 개인 입력은 모두 유지한다. 동일 문자열의 역할만 한 번 설명한다.
    aliases = []
    for key in ('outcome', 'desiredCompetencies'):
        if handoff.get('goal') and handoff.get(key) == handoff['goal']:
            aliases.append(key)
            del handoff[key]
    if aliases:
        handoff['goalAliases'] = aliases
    if handoff.get('known') == knowledge.get('technologies'):
        handoff.pop('known', None)
    # 캐시 식별자·UI 선택 이력은 모델 판단 근거가 아니며 사용자 내용과 구분한다.
    for key in ('key', 'assessmentGenerationId', 'userEdited'):
        handoff.pop(key, None)
    return result
