"""규정 벡터 사전 준비. 기본은 읽기 전용이며 --apply를 지정해야 임베딩·DB 저장한다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import bge_regulation_search, regstore, regulation_embeddings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--group', help='생략하면 활성 규정 전체(직원 구분·국외 포함)를 색인')
    parser.add_argument('--query', help='별도 BGE 색인으로 검색. --group 필수이며 DB를 쓰지 않음')
    args = parser.parse_args(argv)
    if args.query and (not args.group or args.apply):
        parser.error('--query는 --group과 함께 사용하고 --apply와는 분리해 주세요')
    model = regulation_embeddings.model()
    articles = list(regstore.data()['arts'].values())
    if args.group:
        if args.group not in regstore.groups():
            parser.error('등록되지 않은 직원 구분이에요')
        articles = [a for a in articles if a['group'] == args.group]
    result = {'mode': 'apply' if args.apply else 'preview', 'model': model, 'chunks': len(articles)}
    if args.query:
        result['mode'] = 'search'
        result['hits'] = bge_regulation_search.search(args.query, 4, args.group)
        for hit in result['hits']:
            article = regstore.article(hit['id'])
            hit.update(regulation=regstore.data()['regs'][article['reg']]['name'], article=article['no'])
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.apply:
        saved = 0
        for offset in range(0, len(articles), 32):
            part = articles[offset:offset + 32]
            saved += bge_regulation_search.ensure_vectors([a['id'] for a in part])
            print(f'규정 색인 확인 {min(offset + 32, len(articles))}/{len(articles)}, 저장 {saved}', file=sys.stderr, flush=True)
        result['saved'] = saved
    else:
        result.update(embedding_calls=0, database_writes=0)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
