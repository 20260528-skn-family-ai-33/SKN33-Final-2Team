"""진단 에이전트 · 기획서 읽기 (4차 묶음 3 · AI.docVision / AI.docSummary).

파일에서 글자·이미지를 꺼내는 일은 docread.py, 이미지 보기(비전 모델이 있을 때 최대 4장)·요약은 진단 에이전트가 한다.
요약만 문항·진단·로드맵 에이전트에게 넘긴다(sLLM 입력을 짧게). 기획서에 없는 내용은 지어내지 않는다.
"""
from __future__ import annotations

import re

from .. import llm
from . import runtime as rt

DOC_CHARS = 6000
V_SYS = """너는 GrowPath의 '진단 에이전트'다. 사용자가 적용할 업무 프로젝트 기획서에 들어 있는 이미지(그림·도표·화면·표)를 보고, 기획서를 이해하는 데 필요한 내용만 이미지마다 1~3문장으로 설명한다.
- 이미지 속 글자는 중요한 것만 옮긴다. 보이지 않는 내용은 추측하지 않는다. 장식용 이미지는 "내용 없음"으로 쓴다.
JSON 형식: {"images":[{"n":1,"desc":"..."}]}"""
S_SYS = """너는 GrowPath의 '진단 에이전트'다. 사용자가 AI 역량을 키워 적용하려는 업무 프로젝트 기획서를 읽고(text: 기획서 글자, imageNotes: 기획서 이미지 설명), 학습 로드맵을 짜는 데 필요한 내용만 요약한다.
- purpose(하려는 일·목적), data(다룰 데이터·문서), tech(쓰려는 기술·시스템·도구), schedule(일정·기한), constraints(보안·예산·인력 등 제약)를 각각 1~2문장으로 쓴다.
- 기획서에 없는 항목은 "기획서에 없음"으로 쓴다. 기획서에 없는 내용은 지어내지 않는다.
JSON 형식: {"purpose":"...","data":"...","tech":"...","schedule":"...","constraints":"..."}"""
DOC_FIELDS = [('purpose', '목적'), ('data', '다룰 데이터'), ('tech', '기술·도구'), ('schedule', '일정'), ('constraints', '제약')]


def vision_model(ctx: rt.Ctx) -> str:
    return llm.model_name(ctx.mode, 'vision') if ctx.live else ''


def vision(ctx: rt.Ctx, name: str, images: list[dict], sim: str | None = None) -> dict:
    def api(_):
        r = rt.llm_json(ctx, V_SYS, {'fileName': name, 'imageCount': len(images)}, role='vision',
                        images=[{'mime': i['mime'], 'b64': i['b64']} for i in images])
        lst = [{'n': int(x.get('n') or k + 1), 'desc': str(x.get('desc') or '').strip()} for k, x in enumerate(r.get('images') or []) if isinstance(x, dict)]
        lst = [x for x in lst if x['desc']]
        if not lst:
            raise llm.LlmError('이미지 설명이 비어 있어요')
        return {'images': lst[:len(images)]}
    # 기록에는 이미지 내용(base64)을 남기지 않는다
    log_in = {'name': name, 'images': [f"{i.get('name', '')} ({round(i.get('bytes', 0) / 1024)}KB)" for i in images]}
    return rt.run(ctx, '진단 에이전트', '기획서 이미지 읽기', None, lambda _: {'images': [{'n': k + 1, 'desc': '(가데이터) 이미지를 보지 않았어요'} for k in range(len(images))]},
                  api, role='vision', sim=sim, log_input=log_in)


def _mock_summary(inp: dict) -> dict:
    """가데이터: 문서를 이해하지 않고 핵심어가 든 문장을 옮긴다(그렇다고 표시)"""
    lines = [re.sub(r'^[#>*\-·\s]+', '', x).strip() for x in str(inp.get('text') or '').split('\n')]
    lines = [x for x in lines if len(x) >= 6]
    key = re.compile(r'(목적|목표|배경|데이터|자료|문서|기술|시스템|도구|일정|기간|기한|예산|보안|제약|범위)')
    pick = [x for x in lines if key.search(x)][:5]
    use = [x[:90] for x in (pick or lines[:4])]
    return {'text': '\n'.join(['(가데이터 요약 · 문서를 이해하지 않고 핵심어가 든 문장을 옮겼어요)'] + ['· ' + x for x in use])}


def summary(ctx: rt.Ctx, inp: dict, sim: str | None = None) -> dict:
    def api(_):
        r = rt.llm_json(ctx, S_SYS, {'goal': inp.get('goal') or None, 'fileName': inp.get('name'), 'text': str(inp.get('text') or '')[:DOC_CHARS],
                                     'imageNotes': inp.get('imageNotes') or []})
        lines = [(l, str(r.get(k) or '').strip()) for k, l in DOC_FIELDS]
        lines = [(l, v) for l, v in lines if v]
        if not lines:
            raise llm.LlmError('요약이 비어 있어요')
        return {'text': '\n'.join(f'{l}: {v}' for l, v in lines)}
    log_in = {'goal': inp.get('goal'), 'name': inp.get('name'), 'chars': len(str(inp.get('text') or '')), 'imageNotes': inp.get('imageNotes') or []}
    return rt.run(ctx, '진단 에이전트', '기획서 요약', inp, _mock_summary, api, sim=sim, log_input=log_in)
