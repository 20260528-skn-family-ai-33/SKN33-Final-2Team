import json
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

from app import llm
from app.agents import roadmap, runtime


class FixedRoadmapOutputTests(unittest.TestCase):
    def generate(self, course, *, fixed=True, provider="ollama", request=None, resource=None, cost=0, count=3):
        names = ["스킬 A", "스킬 B", "스킬 C", "스킬 D", "스킬 E"][:count]
        handoff = {"skillOrder": names, "selectedSkillsFixed": fixed, "skillDetails": [],
                   "courseSkillSelection": fixed}
        data = {"handoff": handoff, "catalog": [{"id": "course-1"}]}
        rows = [{"name": name, "application": "문서 검색 실습"} for name in names]
        for row in rows:
            if course == "A2":
                row.update(coreOutcome="검색 결과", coreCriteria=["기본 동작 확인"], followUpScope=[])
            if course == "A3":
                row.update(targetOutcome="실험 보고서", completionCriteria=["검색 결과 확인", "검색 시간 비교"])
        result = {"acts": [{"res": resource, "title": "샘플 검증", "skills": names[:1]}]}
        if fixed:
            result["learningSkills"] = rows
        content = json.dumps(result, ensure_ascii=False)
        ctx = SimpleNamespace(mode=provider, provider=provider, reasoning={}, meta={})
        with ExitStack() as stack:
            stack.enter_context(patch.object(runtime, "run", side_effect=lambda c,a,t,i,m,live,**kw:live(i)))
            stack.enter_context(patch.object(runtime, "_record_call"))
            stack.enter_context(patch.object(roadmap, "_sys", return_value="[통합 생성 계약 roadmap-generation/v1]"))
            stack.enter_context(patch.object(roadmap.catalog, "skill_names", return_value=names))
            stack.enter_context(patch.object(roadmap, "_catalog_payload", return_value=data))
            stack.enter_context(patch.object(roadmap, "_cat", return_value={
                "course-1": {"id": "course-1", "title": "검색 실습", "type": "course", "cost": cost, "hours": 2}
            }))
            if provider == "ollama":
                post = stack.enter_context(patch.object(llm,"ollama",return_value={"message":{"content":content}}))
            else:
                post = stack.enter_context(patch.object(llm,"openai",return_value={"choices":[{"message":{"content":content}}]}))
            option = roadmap.option(ctx, {"pid": course,"handoff": handoff,"request": request})
        return post.call_args.args[1], option

    def test_ollama_fixed_request_preserves_names_depth_and_activity_types(self):
        for course, criteria, bounds in (("A2", "coreCriteria", (1, 3)), ("A3", "completionCriteria", (2, 4))):
            with self.subTest(course=course):
                body, option = self.generate(course)
                fields = body["format"]["properties"]
                skills = fields["learningSkills"]
                self.assertEqual((skills["minItems"],skills["maxItems"]), (3,3))
                self.assertEqual([row["properties"]["name"]["const"] for row in skills["prefixItems"]],
                                 [row["name"] for row in option["learningSkills"]])
                for row in skills["prefixItems"]:
                    self.assertIn(criteria, row["required"])
                    field = row["properties"][criteria]
                    self.assertEqual((field["minItems"], field["maxItems"]), bounds)
                task, resource = fields["acts"]["items"]["anyOf"]
                self.assertEqual(task["properties"]["res"],{"type":"null"})
                self.assertEqual(resource["properties"]["res"]["enum"],["course-1"])
                self.assertNotIn("summary",fields)

    def test_fixed_regeneration_can_return_change_summary_and_notes(self):
        body, _ = self.generate("A3",request={"wish":"활동 순서 변경"})
        self.assertTrue({"summary","notes"}.issubset(body["format"]["required"]))
        self.assertNotIn("maxItems", body["format"]["properties"]["acts"])

    def test_initial_free_and_challenge_bound_activities_in_prompt_and_schema(self):
        for course in ("A1", "A3"):
            for count, limit in ((1, 4), (2, 6), (3, 8)):
                with self.subTest(course=course, count=count):
                    body, _ = self.generate(course, count=count)
                    schema = body["format"]
                    self.assertIn("acts", schema["required"])
                    self.assertIn("learningSkills", schema["required"])
                    self.assertFalse(schema["additionalProperties"])
                    self.assertEqual(schema["properties"]["acts"]["maxItems"], limit)
                    self.assertIn(f"최대 {limit}개", body["messages"][0]["content"])
        crash, _ = self.generate("A2")
        self.assertNotIn("maxItems", crash["format"]["properties"]["acts"])
        free_regen, _ = self.generate("A1", request={"wish": "활동 변경"})
        self.assertEqual(free_regen["format"], "json")

    def test_free_resolves_only_offered_resource_ids(self):
        body, option = self.generate("A1", resource={"id": "course-1", "hours": 999})
        activity = option["acts"][0]
        self.assertEqual((activity["res"], activity["hours"]), ("course-1", 2))
        for ref in ({"id": "unknown"}, {}, {"id": []}, ["course-1"]):
            with self.subTest(ref=ref), self.assertRaisesRegex(llm.LlmError, r"acts\[0\]\.res"):
                self.generate("A1", resource=ref)
        with self.assertRaisesRegex(llm.LlmError, "비용이 0"):
            self.generate("A1", resource={"id": "course-1", "cost": 0}, cost=100)

    def test_other_provider_and_nonfixed_ollama_keep_existing_format(self):
        body, _ = self.generate("A2",fixed=False)
        self.assertEqual(body["format"],"json")
        body, _ = self.generate("A3",provider="openai")
        self.assertNotIn("format",body)
        self.assertNotEqual(body.get("response_format",{}).get("type"),"json_schema")
