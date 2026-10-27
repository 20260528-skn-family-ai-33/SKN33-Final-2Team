"""Separate taught content from explicit prerequisites/audience/biography sections."""
import re

EXCLUDED_HEADING = re.compile(
    r'^\s*(?:\d+[.)]\s*)?(?:\[\s*)?(?:학습\s*대상|수강\s*대상|선수\s*(?:지식|학습|요건)|'
    r'사전\s*(?:지식|요구\s*사항)|선행\s*(?:지식|학습)|prerequisites?|'
    r'강좌\s*운영팀\s*소개|교수자(?:\s*소개)?|교수\s*소개|강사\s*(?:소개|이력)|'
    r'교재\s*및\s*참고\s*문헌|참고\s*문헌|수강\s*정보)\s*(?:\])?\s*[:：]?\s*$', re.I)
TEACHING_HEADING = re.compile(
    r'^\s*(?:\d+[.)]\s*)?(?:\[\s*)?(?:강좌\s*소개|과정\s*소개|수업\s*내용(?:\s*/\s*목표)?|'
    r'학습\s*목표|학습\s*내용|교육\s*내용|커리큘럼|강의\s*목차|강좌\s*운영\s*계획|'
    r'주차별\s*학습\s*내용|공개\s*단원|learning\s*objectives|units?|curriculum)\s*(?:\])?\s*[:：]?\s*$', re.I)
PREREQUISITE_LINE = re.compile(
    r'(?:선수\s*(?:능력|지식|학습|요건)|선행\s*(?:지식|과목)|사전\s*요구\s*사항)\s*[:：]|'
    r'^\s*(?:[-•]\s*)?(?:prerequisites?|required\s*prior\s*knowledge)\s*:', re.I)
PREREQUISITE_HEADING = re.compile(r'선수|선행|사전|prerequisite', re.I)
BIOGRAPHY_HEADING = re.compile(r'강사|교수|운영팀')
BIOGRAPHY_CONTENT = re.compile(r'경력|교수|박사|졸업|재직|재학|\d{4}[.년~]')


def teaching_text(value: str) -> str:
    """Keep original taught lines; never alter the stored full source description."""
    result, excluded, paragraph, seen_content = [], False, False, False
    lines = str(value or '').splitlines()
    for index, line in enumerate(lines):
        if TEACHING_HEADING.fullmatch(line):
            excluded = False
        elif EXCLUDED_HEADING.fullmatch(line):
            if BIOGRAPHY_HEADING.search(line):
                following = next((item for item in lines[index + 1:] if item.strip()), '')
                # An actual video lesson called "강사소개" must not hide the rest
                # of an Inflearn curriculum. A biography needs biography content.
                if not BIOGRAPHY_CONTENT.search(following):
                    continue
            excluded = True
            paragraph = bool(PREREQUISITE_HEADING.search(line))
            seen_content = False
            continue
        if excluded and paragraph:
            # Legacy LifeCoding sources separate prerequisites from the rest of
            # the course by a paragraph rather than a named curriculum heading.
            if seen_content and not line.strip():
                excluded = False
            elif line.strip():
                seen_content = True
        if excluded or PREREQUISITE_LINE.search(line):
            continue
        result.append(line)
    return '\n'.join(result)
