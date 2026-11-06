"""회사 정보·사내 생활의 읽기 전용 BGE-M3 검색."""
from __future__ import annotations

from . import bge_knowledge_search

CATEGORY = '수자원공사 정보'
LIFE_CATEGORY = '사내 생활안내'


def search_company(question: str) -> list[dict]:
    """같은 범주의 검증된 실제 회사 자료만 검색한다."""
    return bge_knowledge_search.search(question, CATEGORY)


def search_life(question: str) -> list[dict]:
    """생활 자료의 범주·가상 여부·출처를 보존한다."""
    return bge_knowledge_search.search(question, LIFE_CATEGORY)
