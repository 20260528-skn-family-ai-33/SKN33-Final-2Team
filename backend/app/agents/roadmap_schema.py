"""확정 스킬로 Ollama 로드맵을 생성할 때 사용하는 출력 형식."""
from __future__ import annotations


def _object(fields: dict) -> dict:
    return {"type": "object", "properties": fields, "additionalProperties": False,
            "required": list(fields)}


def _strings(minimum: int, maximum: int) -> dict:
    return {"type": "array", "items": {"type": "string", "minLength": 1},
            "minItems": minimum, "maxItems": maximum}


def initial_activity_limit(skill_count: int) -> int:
    # 스킬별 학습·적용 활동과 공통 도입·검증 활동을 위한 초안 예산이다.
    return 2 * skill_count + 2


def compact_plan_guidance(activity_limit: int) -> str:
    return (f"\n로드맵 본문은 최상위 JSON 객체 하나에 직접 쓴다. acts는 최대 {activity_limit}개이며 "
            "같은 결과물을 만드는 활동은 합친다. 모든 확정 스킬을 다루되 후보 자료를 하나씩 나열하지 않는다. "
            "how는 실행 방법과 완료 확인을 짧은 두 문장으로, 스킬별 목표와 각 기준은 짧은 한 문장으로 쓴다.")


def fixed_plan_schema(course: str, payload: dict, *, regeneration: bool = False,
                      activity_limit: int | None = None) -> dict:
    names = payload["handoff"]["skillOrder"]
    text = {"type": "string", "minLength": 1}
    depth = {}
    if course == "A2":
        depth = {"coreOutcome": text, "coreCriteria": _strings(1, 3), "followUpScope": _strings(0, 3)}
    elif course == "A3":
        depth = {"targetOutcome": text, "completionCriteria": _strings(2, 4)}

    # 위치별 이름을 고정해 중복 항목이 다른 확정 스킬을 밀어내지 않게 한다.
    skills = [_object({"name": {"const": name}, "application": text, **depth}) for name in names]
    ids = [row["id"] for row in payload.get("catalog", [])]
    activity = {"stage": {"type": "integer", "minimum": 1, "maximum": 4}, "title": text,
                "res": {"type": "null"}, "hours": {"type": "number"}, "how": text}
    task = _object({**activity, "skills": _strings(1, 3)})
    activity_types = [task]
    if ids:
        activity_types.append(_object({**activity, "res": {"type": "string", "enum": ids}}))
    fields = {"displayTitle": text, "tagline": text, "reason": text, "pros": _strings(1, 3),
              "cons": _strings(1, 3), "scope": text, "weeklyHours": {"type": "number"},
              "acts": {"type": "array", "minItems": 1, "items": {"anyOf": activity_types}},
              "learningSkills": {"type": "array", "prefixItems": skills,
                                 "minItems": len(skills), "maxItems": len(skills)}}
    if regeneration:
        fields.update(summary=text, notes={"type": "array", "items": text})
    if activity_limit is not None:
        fields["acts"]["maxItems"] = activity_limit
    return _object(fields)
