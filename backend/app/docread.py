"""기획서 파일에서 글자와 이미지를 꺼낸다 (4차 묶음 3 · server.py 의 POST /api/doc-read 가 쓴다)

- 표준 라이브러리로 항상 읽음: DOCX · PPTX · HWPX (zip + XML), TXT · MD
- 설치돼 있을 때만 읽음: PDF (pypdf), HWP 옛 형식 (olefile). 없으면 그 형식만 읽을 수 없다고 알린다
- 이미지: 글자 밖의 그림·도표를 비전 모델에 보여 주려고 큰 것부터 최대 4장만 돌려준다
  (장당 15KB 이상 1.5MB 이하 · PNG·JPEG·GIF·WEBP. 작은 아이콘·큰 파일·EMF/WMF 같은 형식은 개수만 센다)
오류 문구 앞머리('기획서 형식' / '기획서 읽기 실패' / 'pypdf 없음' / 'olefile 없음')는
화면에서 원인을 고를 때 쓰므로 바꾸면 assets/gp-ai.js 의 CAUSES 도 같이 고친다
"""
from __future__ import annotations

import base64
import io
import re
import struct
import zipfile
import zlib
from xml.etree import ElementTree as ET

MAX_TEXT = 12000          # 에이전트에게 넘길 글자 수 상한 (요약 에이전트 입력 · 화면 저장용)
MAX_IMAGES = 4
MIN_IMG, MAX_IMG = 15_000, 1_500_000
IMG_MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp'}
OTHER_IMG = ('.emf', '.wmf', '.bmp', '.tif', '.tiff', '.svg', '.jfif', '.ole')


class DocError(Exception):
    pass


def has_pdf() -> bool:
    try:
        import pypdf  # noqa: F401
        return True
    except ImportError:
        return False


def has_hwp() -> bool:
    try:
        import olefile  # noqa: F401
        return True
    except ImportError:
        return False


# ── 글자 ──
def _paras(xml: bytes, p_tag: str, t_tag: str) -> list[str]:
    """문단(p) 단위로 글자(t)를 모은다. 표 안 문단처럼 문단 안의 문단은 따로 한 줄로 뺀다"""
    out: list[str] = []

    def walk(el, buf):
        tag = el.tag.rsplit('}', 1)[-1]
        if tag == p_tag:
            mine: list[str] = []
            for ch in el:
                walk(ch, mine)
            line = re.sub(r'\s+', ' ', ''.join(mine)).strip()
            if line:
                out.append(line)
            return
        if tag == t_tag:
            buf.append(''.join(el.itertext()))
            return
        if tag in ('tab', 'br'):
            buf.append(' ')
        for ch in el:
            walk(ch, buf)

    walk(ET.fromstring(xml), [])
    return out


def _numbered(names: list[str], pattern: str) -> list[str]:
    pick = [(int(m.group(1)), n) for n in names for m in [re.fullmatch(pattern, n)] if m]
    return [n for _, n in sorted(pick)]


def _zip_doc(raw: bytes, kind: str) -> tuple[list[str], list[tuple[str, bytes]]]:
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise DocError(f'기획서 읽기 실패: {kind.upper()} 파일이 손상됐거나 형식이 맞지 않아요') from e
    names = z.namelist()
    lines: list[str] = []
    if kind == 'docx':
        if 'word/document.xml' not in names:
            raise DocError('기획서 읽기 실패: DOCX 본문(word/document.xml)이 없어요')
        lines = _paras(z.read('word/document.xml'), 'p', 't')
        media = 'word/media/'
    elif kind == 'pptx':
        for i, n in enumerate(_numbered(names, r'ppt/slides/slide(\d+)\.xml'), 1):
            body = _paras(z.read(n), 'p', 't')
            if body:
                lines.append(f'[슬라이드 {i}]')
                lines.extend(body)
        media = 'ppt/media/'
    else:  # hwpx
        secs = _numbered(names, r'Contents/section(\d+)\.xml')
        if not secs:
            raise DocError('기획서 읽기 실패: HWPX 본문(Contents/section0.xml)이 없어요')
        for n in secs:
            lines.extend(_paras(z.read(n), 'p', 't'))
        media = 'BinData/'
    imgs = [(n, z.read(n)) for n in names if n.startswith(media) and not n.endswith('/')]
    return lines, imgs


def _pdf(raw: bytes) -> tuple[list[str], list[tuple[str, bytes]], int]:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise DocError('pypdf 없음: 이 PC에 PDF 읽기 도구(pypdf)가 설치되지 않았어요') from e
    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = list(reader.pages)
    except Exception as e:  # noqa: BLE001 - 암호·손상 등 pypdf 오류 종류가 많음
        raise DocError(f'기획서 읽기 실패: PDF를 열지 못했어요 ({type(e).__name__})') from e
    lines: list[str] = []
    imgs: list[tuple[str, bytes]] = []
    for i, p in enumerate(pages):
        try:
            t = p.extract_text() or ''
        except Exception:  # noqa: BLE001
            t = ''
        lines.extend(x.strip() for x in t.splitlines() if x.strip())
        if i < 30 and len(imgs) < 40:
            try:
                for im in p.images:
                    imgs.append((im.name, im.data))
            except Exception:  # noqa: BLE001 - 이미지 디코딩 실패(Pillow 없음 등)는 건너뜀
                pass
    return lines, imgs, len(pages)


def _hwp(raw: bytes) -> tuple[list[str], list[tuple[str, bytes]]]:
    """HWP 5.0 (OLE 복합 문서). BodyText/SectionN 레코드 중 문단 글자(HWPTAG_PARA_TEXT=67)만 읽는다"""
    try:
        import olefile
    except ImportError as e:
        raise DocError('olefile 없음: 이 PC에 HWP 읽기 도구(olefile)가 설치되지 않았어요') from e
    try:
        ole = olefile.OleFileIO(io.BytesIO(raw))
        header = ole.openstream('FileHeader').read()
    except Exception as e:  # noqa: BLE001
        raise DocError('기획서 읽기 실패: HWP 파일을 열지 못했어요 (손상됐거나 HWP 5.0 형식이 아님)') from e
    compressed = bool(header[36] & 1)
    if header[36] & 2:
        raise DocError('기획서 읽기 실패: 암호가 걸린 HWP 파일이에요')
    unpack = (lambda b: zlib.decompress(b, -15)) if compressed else (lambda b: b)
    secs = sorted((e for e in ole.listdir() if len(e) == 2 and e[0] == 'BodyText' and e[1].startswith('Section')), key=lambda e: int(e[1][7:] or 0))
    lines: list[str] = []
    for s in secs:
        data = unpack(ole.openstream(s).read())
        i = 0
        while i + 4 <= len(data):
            h = struct.unpack_from('<I', data, i)[0]
            tag, size = h & 0x3FF, (h >> 20) & 0xFFF
            i += 4
            if size == 0xFFF:
                size = struct.unpack_from('<I', data, i)[0]
                i += 4
            if tag == 67:
                lines.append(_hwp_text(data[i:i + size]))
            i += size
    lines = [re.sub(r'\s+', ' ', x).strip() for x in lines]
    imgs = []
    for e in ole.listdir():
        if len(e) == 2 and e[0] == 'BinData':
            try:
                b = ole.openstream(e).read()
                imgs.append((e[1], unpack(b) if compressed else b))
            except Exception:  # noqa: BLE001
                pass
    return [x for x in lines if x], imgs


def _hwp_text(b: bytes) -> str:
    """문단 글자(UTF-16LE)에서 제어 문자를 뺀다. 1~3·11~18·21~23 등은 8글자 길이의 확장 제어"""
    out, n, i = [], len(b) // 2, 0
    while i < n:
        c = struct.unpack_from('<H', b, i * 2)[0]
        if c >= 32:
            out.append(chr(c))
            i += 1
        elif c in (10, 13):
            out.append(' ')
            i += 1
        elif c in (0, 24, 25, 26, 27, 28, 29, 30, 31):
            i += 1
        else:
            i += 8
    return ''.join(out)


def _decode_text(raw: bytes) -> str:
    for enc in ('utf-8-sig', 'cp949'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'replace')


# ── 이미지 고르기 ──
def _ext(name: str) -> str:
    m = re.search(r'\.[A-Za-z0-9]+$', name)
    return m.group(0).lower() if m else ''


def _pick_images(imgs: list[tuple[str, bytes]]) -> tuple[list[dict], dict, int]:
    skipped = {'small': 0, 'big': 0, 'format': 0}
    ok = []
    for name, data in imgs:
        ext = _ext(name)
        if ext not in IMG_MIME:
            if ext in OTHER_IMG or ext:
                skipped['format'] += 1
            continue
        if len(data) < MIN_IMG:
            skipped['small'] += 1
            continue
        if len(data) > MAX_IMG:
            skipped['big'] += 1
            continue
        ok.append((name, data, IMG_MIME[ext]))
    ok.sort(key=lambda x: -len(x[1]))
    chosen = ok[:MAX_IMAGES]
    skipped['more'] = max(0, len(ok) - MAX_IMAGES)
    total = len(imgs)
    return [{'name': n, 'mime': m, 'bytes': len(d), 'b64': base64.b64encode(d).decode('ascii')} for n, d, m in chosen], skipped, total


# ── 진입점 ──
def read(name: str, raw: bytes) -> dict:
    ext = _ext(name)
    pages = None
    if ext in ('.txt', '.md'):
        lines, imgs = [x.rstrip() for x in _decode_text(raw).splitlines()], []
        fmt = ext[1:].upper()
    elif ext in ('.docx', '.pptx', '.hwpx'):
        lines, imgs = _zip_doc(raw, ext[1:])
        fmt = ext[1:].upper()
    elif ext == '.pdf':
        lines, imgs, pages = _pdf(raw)
        fmt = 'PDF'
    elif ext == '.hwp':
        lines, imgs = _hwp(raw)
        fmt = 'HWP'
    elif ext in ('.doc', '.ppt'):
        raise DocError(f'기획서 형식: {ext[1:].upper()}(옛 형식)는 읽을 수 없어요. {ext[1:].upper()}X로 저장해 주세요')
    else:
        raise DocError(f'기획서 형식: {ext or "확장자 없는"} 파일은 읽을 수 없어요')
    text = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
    chosen, skipped, total = _pick_images(imgs)
    warnings = []
    if not text and fmt == 'PDF':
        warnings.append('PDF에서 글자를 찾지 못했어요. 스캔한 이미지 PDF일 수 있어요')
    return {'format': fmt, 'chars': len(text), 'truncated': len(text) > MAX_TEXT, 'text': text[:MAX_TEXT], 'pages': pages,
            'images': chosen, 'imageTotal': total, 'imageSkipped': skipped, 'warnings': warnings}
