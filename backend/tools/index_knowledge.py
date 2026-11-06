"""회사 정보·사내 생활 BGE-M3 사전 색인. 기본은 읽기 전용, --apply에서만 생성·저장."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import bge_knowledge_search as search, regulation_embeddings as embeddings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--category', choices=search.CATEGORIES)
    parser.add_argument('--query', help='범주를 지정해 별도 BGE 벡터 검색. DB를 쓰지 않음')
    args = parser.parse_args(argv)
    if args.query and (not args.category or args.apply):
        parser.error('--query는 --category와 함께 사용하고 --apply와 분리해 주세요')
    if args.query:
        print(json.dumps({'model': embeddings.BGE_MODEL, 'hits': search.search(args.query, args.category)}, ensure_ascii=False))
        return 0
    chunks = search.source_chunks(args.category)
    result = {'mode': 'apply' if args.apply else 'preview', 'model': embeddings.BGE_MODEL,
              'dimensions': embeddings.BGE_DIMENSIONS, 'chunks': len(chunks)}
    if args.apply:
        search.install_schema()
        saved = 0
        for offset in range(0, len(chunks), 16):
            saved += search.ensure_vectors(chunks[offset:offset + 16])
            print(f'자료 색인 확인 {min(offset + 16, len(chunks))}/{len(chunks)}, 저장 {saved}', file=sys.stderr, flush=True)
        result['saved'] = saved
    else:
        result.update(embedding_calls=0, database_writes=0)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
