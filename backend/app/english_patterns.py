"""한국어 조사가 붙어도 영문·숫자 토큰의 경계를 유지한다."""


def english_token(body: str, *, left: bool = True, right: bool = True) -> str:
    return ((r'(?<![a-z0-9_])' if left else '') + '(?:' + body + ')'
            + (r'(?![a-z0-9_])' if right else ''))
