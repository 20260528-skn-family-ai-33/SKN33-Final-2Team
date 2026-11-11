"""배포 단위 LLM 선택. 전 프로세스가 같은 영속 볼륨의 제공자 이름만 읽는다."""
from pathlib import Path
from tempfile import NamedTemporaryFile

from . import llm
from .config import S, level_ok
from .errors import ApiError, unavailable_reason


def _read_selection() -> tuple[str, str | None, str]:
    # 첫 줄은 기존 제공자 파일과 호환된다. 선택한 단계가 있을 때만 둘째 줄을 쓴다.
    path = S.var_dir / 'ai-provider'
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        lines = ['employee']
    except UnicodeDecodeError as exc:
        raise ApiError(503, 'BAD_PROVIDER_POLICY', '저장된 AI 설정을 확인해 주세요') from exc
    if len(lines) not in (1, 2) or lines[0] not in ('employee', 'ollama', 'openai'):
        raise ApiError(503, 'BAD_PROVIDER_POLICY', '저장된 AI 설정을 확인해 주세요')
    mode = lines[0]
    level = lines[1] if len(lines) == 2 else None
    if level is not None and (mode == 'employee' or not level_ok(level)):
        raise ApiError(503, 'BAD_PROVIDER_POLICY', '저장된 추론 정도를 확인해 주세요')
    if mode == 'employee' and not S.employee_ai_selection:
        return 'ollama', None, 'default_ollama'
    if mode == 'openai' and level not in S.openai_reasoning_levels:
        level = None
    return mode, level, 'active'


def selection() -> tuple[str, str | None]:
    mode, level, _ = _read_selection()
    return mode, level


def admin_selection() -> tuple[str | None, str | None, str]:
    """실행 경로는 손상된 설정을 거부하되, 관리자는 새 값으로 복구할 수 있다."""
    try:
        return _read_selection()
    except ApiError as exc:
        if exc.code != 'BAD_PROVIDER_POLICY':
            raise
        return None, None, 'invalid'


def current() -> str:
    return selection()[0]


def resolve(policy: str, employee_provider: str | None) -> str:
    return (employee_provider or 'ollama') if policy == 'employee' else policy


def save(mode: str, level: str | None = None) -> None:
    if mode not in ('employee', 'ollama', 'openai'):
        raise ApiError(422, 'BAD_PROVIDER', '사용할 AI 제공자를 선택해 주세요')
    if mode == 'employee' and not S.employee_ai_selection:
        raise ApiError(409, 'EMPLOYEE_SELECTION_DISABLED', '이 배포에서는 관리자만 모델을 선택할 수 있어요')
    if mode != 'employee' and not llm.available(mode):
        raise ApiError(409, 'AI_UNAVAILABLE', unavailable_reason(mode), kind='config')
    if level is not None:
        if not isinstance(level, str) or not level_ok(level) or mode == 'employee':
            raise ApiError(422, 'BAD_REASONING', '고정 모델의 추론 단계를 선택해 주세요')
        levels = S.openai_reasoning_levels
        if mode == 'ollama':
            info = llm.think_levels(llm.model_name('ollama'))
            if info is None:
                raise ApiError(409, 'AI_UNAVAILABLE', 'Ollama의 추론 단계를 확인하지 못했어요. 연결을 확인해 주세요')
            levels = info['levels']
        if level not in levels:
            raise ApiError(422, 'BAD_REASONING', '선택한 모델이 지원하는 추론 단계가 아니에요')
    S.var_dir.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=S.var_dir, delete=False, mode='w', encoding='utf-8') as tmp:
        temp_path = Path(tmp.name)
        tmp.write(mode + '\n')
        if level is not None:
            tmp.write(level + '\n')
    try:
        temp_path.replace(S.var_dir / 'ai-provider')
    finally:
        temp_path.unlink(missing_ok=True)


def require_employee_selection() -> None:
    if current() != 'employee':
        raise ApiError(409, 'PROVIDER_MANAGED', '관리자가 지정한 AI 모델을 사용하고 있어요')
