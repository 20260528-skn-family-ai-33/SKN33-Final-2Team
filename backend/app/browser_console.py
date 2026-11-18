"""요청을 보낸 브라우저의 테스트 설정. 서버 환경과 계정 설정에는 저장하지 않는다."""
from contextvars import ContextVar
from dataclasses import dataclass, field
from ipaddress import IPv4Address
import re

from .config import S


@dataclass(frozen=True)
class BrowserOptions:
    picker: bool | None = None
    demo: bool | None = None
    timeout: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    ollama_url: str | None = None
    ollama_key: str | None = field(default=None, repr=False)
    # (직원 ID, 직접 고른 모델). 선택 박스만 연 상태에서는 모델이 None이다.
    model_selection: tuple[int, str | None] | None = None


options = ContextVar('browser_options', default=BrowserOptions())


def provider_allowed(employee_id: int) -> bool:
    return S.browser_overrides and str(employee_id) in S.console_provider_employees


def demo_enabled(default: bool) -> bool:
    override = options.get().demo
    return default if override is None else override


def runpod_url(value: str) -> str:
    # 팀 배포의 TCP 공개 주소와 RunPod HTTPS 프록시만 브라우저에서 지정할 수 있다.
    if re.fullmatch(r'https://[a-z0-9-]{1,63}\.proxy\.runpod\.net/?', value, re.ASCII | re.IGNORECASE):
        return value.rstrip('/').lower()
    match = re.fullmatch(r'(https?)://([0-9.]+):([1-9][0-9]{0,4})/?', value, re.ASCII | re.IGNORECASE)
    if match and int(match[3]) <= 65535:
        try:
            address = IPv4Address(match[2])
        except ValueError:
            pass
        else:
            if address.is_global and not address.is_multicast and not address.is_reserved:
                return value.rstrip('/').lower()
    raise ValueError('RunPod HTTPS 프록시 또는 공개 IPv4와 TCP 포트를 입력해 주세요.')


def from_headers(headers, demo_default: bool, *, allow_overrides: bool = False) -> BrowserOptions:
    def toggle(name: str) -> bool | None:
        value = headers.get(name)
        if value == 'off':
            return False
        return True if value == 'on' and allow_overrides else None

    demo = toggle('x-growpath-demo')
    enabled = allow_overrides and (demo_default if demo is None else demo)

    def number(name: str, maximum: int) -> int | None:
        raw = headers.get(name)
        if raw is None or not enabled:
            return None
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 6 or not 1 <= int(raw) <= maximum:
            raise ValueError(f'{name} 범위는 1~{maximum}입니다.')
        return int(raw)

    url = key = None
    if enabled:
        url = headers.get('x-growpath-ollama-url')
        if url is not None:
            url = runpod_url(url)
        key = headers.get('x-growpath-ollama-key')
        if key is not None and not re.fullmatch(r'[!-~]{1,1024}', key):
            raise ValueError('Ollama API 키는 공백 없는 ASCII 문자 1~1024자여야 합니다.')
    return BrowserOptions(toggle('x-growpath-picker'), demo,
                          number('x-growpath-timeout', 900), number('x-growpath-input', 131072),
                          number('x-growpath-output', 32768), url, key)
