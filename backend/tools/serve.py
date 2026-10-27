"""5차 목업 서버 실행: python tools/serve.py [--port 8785] [--env 설정파일] [--open-browser]

--env 로 다른 설정 파일을 줄 수 있다(모의 Ollama 시험용 등). 기본은 이 폴더의 .env.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8785)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--env')
    ap.add_argument('--open-browser', action='store_true')
    ap.add_argument('--reload', action='store_true', help='개발 중: app 코드가 바뀌면 서버를 다시 띄운다')
    a = ap.parse_args()
    if a.env:
        os.environ['GP5_ENV_FILE'] = str(Path(a.env).resolve())
    sys.path.insert(0, str(ROOT))
    import uvicorn
    url = f'http://{a.host}:{a.port}/'
    print(f'GrowPath 5차 목업 · {url} · API 문서 {url}api/docs · 종료 Ctrl+C', flush=True)
    if a.open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    os.chdir(ROOT)
    # 작업 결과를 기다리는 긴 요청(최대 15초)이 있어도 다시 띄우기·종료가 멈추지 않게 5초만 기다린다
    uvicorn.run('app.main:app', host=a.host, port=a.port, log_level='warning', reload=a.reload, reload_dirs=[str(ROOT / 'app')] if a.reload else None,
                timeout_graceful_shutdown=5)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
