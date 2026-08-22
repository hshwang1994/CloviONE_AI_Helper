"""로컬 파일 업로드 저장·검증 (팀 공간 첨부, 보안 §22).

원칙:
- **매직바이트로 형식을 판정**한다 — 선언된 Content-Type이나 사용자 확장자를 믿지 않는다.
- 저장명은 **서버가 만든 UUID + 판정된 확장자**다. 사용자 파일명은 표시용으로만 새니타이즈해
  보관하고 경로로 절대 쓰지 않는다(경로 traversal 원천 차단).
- 크기·개수 상한을 강제한다. 파일은 웹 루트 밖(data_dir/uploads/...)에 저장하고, 서빙은
  인증된 엔드포인트가 nosniff 헤더와 함께 한다(실행 불가).

**네임스페이스(namespace)가 곧 접근 통제 경계다.** 예전엔 이 모듈이 `uploads/board/<post_id>`
하나만 알았고, 서빙도 `GET /api/board/attachments/{id}` 하나뿐이라 "로그인한 사람 = 전부 열람"
이었다(게시판은 조직 전체 공개라 그게 맞았다). 그 네임스페이스를 팀 채팅이 재사용하면
**1:1 DM 이미지가 전사 공개**가 된다 — 게시판 서빙 라우트는 채팅방 멤버십을 모른다.
그래서 저장 경로와 traversal 가드를 `uploads/<namespace>/<owner_id>/` 로 일반화하고,
네임스페이스별로 **자기 접근 검사를 하는 서빙 라우트**를 따로 두게 했다.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from app.core.errors import StorageUnavailableError, ValidationAppError

logger = logging.getLogger("app.uploads")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
MAX_ATTACHMENTS_PER_POST = 5

# 판정된 media_type → 저장 확장자.
_EXT_BY_MEDIA = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
ALLOWED_MEDIA_TYPES = frozenset(_EXT_BY_MEDIA)

# ── 확장 판정 (S8) ───────────────────────────────────────────────────────────
#
# 지식 문서 첨부는 이미지와 PDF 만으로 부족하다 — 회의록에 붙는 것은 보통 문서와
# 스프레드시트다. 그런데 **판정기를 새로 만들지 않는다.** 두 벌이 되면 한쪽만 아는
# 형식이 생기고, 그 차이는 「어떤 화면에서는 되는데 어떤 화면에서는 안 된다」로만
# 드러난다. 그래서 이 파일의 `sniff_media_type` 하나를 넓히고, **무엇을 받을지는
# 네임스페이스가 `allowed_media_types` 로 좁힌다.** 게시판·채팅·티켓의 허용 집합은
# 그대로다.
#
# OOXML(docx·xlsx·pptx)은 앞부분 바이트가 전부 ZIP 이라 `head` 만으로는 못 가른다.
# 그래서 `full=` 을 받아 zip 안의 항목 이름을 본다 — 확장자나 선언된 Content-Type 을
# 믿지 않는다는 원칙은 그대로다.
_EXT_BY_MEDIA_EXTENDED = {
    **_EXT_BY_MEDIA,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/zip": ".zip",
    "text/plain": ".txt",
}

#: 지식 문서 첨부가 받는 형식. 일반 ZIP 은 **일부러 뺐다** — 안에 무엇이 들었는지
#: 서버가 판정할 수 없는데 받으면, 「판정된 형식만 신뢰한다」는 이 모듈의 원칙이
#: 그 한 줄에서 깨진다. 판정기는 `application/zip` 을 여전히 **알아본다**(그래야
#: OOXML 인 척하는 zip 을 「모르는 형식」이 아니라 정확한 이유로 거절한다).
DOCUMENT_MEDIA_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
    }
)

#: 브라우저 안에서 그대로 펼쳐도 되는 형식. 나머지는 내려받기로 준다 — `nosniff` 가
#: 실행을 막지만, 「받아서 여는 것」과 「탭 안에서 열리는 것」은 사용자가 느끼는
#: 위험이 다르다.
INLINE_MEDIA_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}
)


def extension_for(media_type: str) -> str:
    """판정된 형식의 저장 확장자. 모르는 형식은 확장자가 없다."""
    return _EXT_BY_MEDIA_EXTENDED.get(media_type, "")


# 이미지 전용 네임스페이스(채팅 붙여넣기 등) — PDF는 말풍선에 인라인으로 그릴 수 없다.
IMAGE_MEDIA_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)

# 업로드 네임스페이스 — 저장 루트(uploads/<namespace>/)의 한 조각이 되므로 소문자·밑줄만.
NS_BOARD = "board"
NS_TEAM_CHAT = "team_chat"
# 프로필 사진. owner_id 는 **사용자 id** 이고 서빙은 profiles 라우터가 한다.
# 게시판 네임스페이스를 재사용하지 않는 이유가 이 모듈 docstring 에 이미 적혀 있다:
# 서빙 라우트가 곧 접근 통제이고, board 라우트는 '글이 살아 있는가'만 볼 줄 안다.
# 아바타는 그 질문 자체가 다르다(계정이 살아 있는가 / 요청자가 로그인했는가).
NS_AVATAR = "avatar"
# 티켓 첨부. owner_id 는 **ticket_cache.id(자체 UUID)** 이고 Notion page id 가 아니다 —
# 소스를 바꾸는 순간 첨부가 전부 고아가 되기 때문이다(댓글과 같은 이유, tickets/models.py).
# 게시판을 재사용하지 않는 이유는 위와 같다: 서빙 라우트가 곧 접근 통제인데 board 라우트는
# '글이 살아 있는가'만 볼 줄 알고, 티켓은 '이 티켓이 아직 있는가'를 묻는다.
NS_TICKET = "ticket"
_NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

# 서버 생성 저장명 패턴(서빙 시 방어적으로 재검증).
_STORED_NAME_RE = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{2,5}$")


def sniff_media_type(head: bytes, *, full: bytes | None = None) -> str | None:
    """앞부분 바이트로 형식을 판정한다. 판정 못 하면 None.

    `full` 을 주면 **전체 내용이 있어야 답할 수 있는 형식**까지 본다(OOXML · 평문).
    안 주면 예전과 **바이트 단위로 같은 답**을 낸다 — 게시판·채팅·티켓·프로필은
    그대로 다섯 형식만 안다.
    """
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if full is None:
        return None
    if head.startswith(b"PK\x03\x04"):
        return _sniff_zip_family(full)
    return _sniff_text(full)


def _sniff_zip_family(content: bytes) -> str | None:
    """ZIP 안을 들여다봐서 OOXML 셋을 가른다. 압축은 풀지 않는다(목록만 읽는다).

    확장자를 안 믿는 것과 같은 이유로 `[Content_Types].xml` 의 선언도 안 믿는다 —
    **실제로 들어 있는 항목**을 본다. `word/` 가 없는 파일은 아무리 docx 라고 적혀
    있어도 워드 문서가 아니다.
    """
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = set(zf.namelist())
    except (zipfile.BadZipFile, OSError, ValueError):
        return None
    if "word/document.xml" in names:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if "xl/workbook.xml" in names:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if "ppt/presentation.xml" in names:
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    return "application/zip"


# 평문에서 허용하는 제어문자. 탭·줄바꿈만이다.
_TEXT_ALLOWED_CONTROL = frozenset({0x09, 0x0A, 0x0D})


def _sniff_text(content: bytes) -> str | None:
    """UTF-8 로 읽히고 제어문자가 없으면 평문. 아니면 None.

    평문에는 매직바이트가 없어서 「아닌 것을 배제하는」 방식으로만 판정할 수 있다.
    그래서 **엄격하게** 본다: UTF-8 디코딩 실패, 널바이트, 탭·줄바꿈 아닌 제어문자
    중 하나라도 있으면 평문이 아니다. BOM 은 떼고 본다(윈도우 메모장이 붙인다).
    """
    if not content:
        return None
    body = content[3:] if content.startswith(b"\xef\xbb\xbf") else content
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(b < 0x20 and b not in _TEXT_ALLOWED_CONTROL for b in body):
        return None
    if 0x7F in body:
        return None
    return "text/plain"


def sanitize_filename(name: str) -> str:
    """표시용 원본 파일명 정리 — 경로 구분자·제어문자·상위경로 토큰 제거, 길이 제한.

    반환값은 표시(다운로드 시 Content-Disposition)로만 쓴다. 절대 경로 구성에 쓰지 않는다.
    """
    if not name:
        return "file"
    # 경로 구분자 기준 마지막 요소만.
    base = name.replace("\\", "/").split("/")[-1]
    # 널바이트·제어문자 제거.
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '\r\n\t')
    # 상위경로 토큰 무력화.
    base = base.replace("..", "_").strip().strip(".")
    if not base:
        base = "file"
    return base[:200]


def _namespace_root(data_dir: Path, namespace: str) -> Path:
    """`uploads/<namespace>/` — traversal 가드가 기준으로 삼는 뿌리."""
    if not _NAMESPACE_RE.match(namespace or ""):
        # 호출자(우리 코드)의 버그다 — 사용자 입력이 여기 닿을 길은 없다.
        raise ValueError(f"invalid upload namespace: {namespace!r}")
    return Path(data_dir) / "uploads" / namespace


def _owner_dir(data_dir: Path, namespace: str, owner_id: str) -> Path:
    # owner_id는 서버가 만든 UUID이며 라우터가 실제 존재하는 객체(글·채팅방)에서 얻는다 —
    # 그래도 방어적으로 경로 구분자를 허용하지 않는다.
    safe_owner = re.sub(r"[^0-9a-fA-F-]", "", owner_id or "")
    return _namespace_root(data_dir, namespace) / safe_owner


def uploads_writable(data_dir: Path) -> bool:
    """OPS-03: 실제로 파일을 만들어 봐서 uploads 루트가 쓰기 가능한지 확인한다.

    디스크 용량 확인(`app/health/service.py::_disk_usage`)과는 다른 결함을 잡는다 —
    용량은 남아 있는데 소유권/권한이 드리프트된 경우(`OPS-01` 실사고가 정확히 이
    유형이었다: `root:clovirassist 750`이라 서비스 계정에 쓰기 비트가 없었다)는
    디스크 용량만으로는 안 보인다. 네임스페이스 각각이 아니라 루트(`uploads/`) 하나만
    본다 — 이 종류의 드리프트는 루트에서 한 번에 나서 모든 네임스페이스를 같이 막으므로,
    하나만 확인해도 충분하고 매 반복(대시보드 폴링 등)마다 여러 번 도는 비용을 줄인다.
    """
    root = Path(data_dir) / "uploads"
    marker = root / ".write_probe"
    try:
        root.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(b"")
        marker.unlink()
        return True
    except OSError:
        return False


def save_upload(
    data_dir: Path,
    owner_id: str,
    *,
    filename: str,
    content: bytes,
    namespace: str = NS_BOARD,
    allowed_media_types: frozenset[str] = ALLOWED_MEDIA_TYPES,
) -> tuple[str, str, int, str]:
    """검증 후 파일을 `uploads/<namespace>/<owner_id>/` 아래에 저장한다.

    ``owner_id`` 는 네임스페이스마다 다르다: board=글 id, team_chat=채팅방 id.
    ``allowed_media_types`` 로 네임스페이스별 허용 형식을 좁힌다(채팅은 이미지 전용).

    반환: (stored_name, media_type, size_bytes, display_filename).
    검증 실패는 ValidationAppError(422). 디스크 쓰기 실패(디스크 풀·권한 드리프트 등)는
    StorageUnavailableError(503) — 원문 OSError·경로는 서버 로그에만 남고 사용자에게는
    안 샌다(OPS-05, 예전엔 여기 try/except가 없어 raw OSError가 그대로 500으로 샜다).
    """
    size = len(content)
    if size == 0:
        raise ValidationAppError("빈 파일은 올릴 수 없습니다.")
    if size > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationAppError(f"파일이 너무 큽니다. 최대 {mb}MB까지 올릴 수 있습니다.")

    media_type = sniff_media_type(content[:16])
    if media_type is None or media_type not in allowed_media_types:
        if allowed_media_types == IMAGE_MEDIA_TYPES:
            raise ValidationAppError(
                "이미지 파일만 붙여넣을 수 있습니다(PNG, JPEG, GIF, WebP)."
            )
        raise ValidationAppError(
            "허용되지 않은 파일 형식입니다. 이미지(PNG, JPEG, GIF, WebP) 또는 PDF만 올릴 수 있습니다."
        )

    stored_name = f"{uuid.uuid4().hex}{extension_for(media_type)}"
    target_dir = _owner_dir(data_dir, namespace, owner_id)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / stored_name).write_bytes(content)
    except OSError:
        logger.exception(
            "upload write failed namespace=%s owner_id=%s", namespace, owner_id
        )
        raise StorageUnavailableError() from None

    return stored_name, media_type, size, sanitize_filename(filename)


def attachment_path(
    data_dir: Path,
    owner_id: str,
    stored_name: str,
    *,
    namespace: str = NS_BOARD,
) -> Path | None:
    """저장된 첨부의 실제 경로. 저장명이 서버 패턴에 맞고 파일이 실제로 있을 때만 반환.

    최종 방어: 해석된 경로가 반드시 **그 네임스페이스의** 업로드 뿌리 안이어야 한다 —
    네임스페이스를 섞어 부르면(board 라우트가 team_chat 파일을 가리키는 식) 경로가
    뿌리 밖으로 나가 None 이 된다.
    """
    if not _STORED_NAME_RE.match(stored_name or ""):
        return None
    path = _owner_dir(data_dir, namespace, owner_id) / stored_name
    root = _namespace_root(data_dir, namespace).resolve()
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_file() else None


def content_disposition(filename: str, *, inline: bool = True) -> str:
    """다운로드/표시 시 **원본 파일명**을 실어 보내는 `Content-Disposition` 값.

    예전에는 세 첨부 라우트가 전부 `"inline"` 만 보냈다. 원본 표시명을 DB 에 저장해 두고
    `sanitize_filename` 으로 살균까지 해 놓고도(그 함수의 주석이 "다운로드 시
    Content-Disposition 표시용" 이라고 적고 있다) **한 번도 보내지 않았다.** 그래서
    `스크린샷 2026-08-05 092127.png` 를 저장하면 **UUID 이름에 확장자 없는 파일**이 떨어졌다.
    (운영 실측 2026-08-05: 첨부 2건이 전부 한글 파일명이다.)

    한글 파일명은 헤더에 그대로 못 넣는다 — HTTP 헤더는 latin-1 이다. RFC 6266/5987 대로
    두 벌을 보낸다:

      * `filename=` : ASCII 로 떨어뜨린 폴백. RFC 5987 을 모르는 옛 클라이언트용.
      * `filename*=UTF-8''…` : 퍼센트 인코딩한 진짜 이름. 요즘 브라우저는 이걸 쓴다.

    둘 다 보내면 신·구 클라이언트가 각자 아는 쪽을 고른다.
    """
    safe = sanitize_filename(filename)
    # 헤더 문법을 깨뜨리는 문자(따옴표·역슬래시)를 없애고 비ASCII 는 `_` 로 떨어뜨린다.
    ascii_fallback = (
        safe.encode("ascii", "replace").decode("ascii").replace('"', "_").replace("\\", "_")
    )
    ascii_fallback = ascii_fallback.replace("?", "_").strip() or "file"
    quoted = quote(safe, safe="")
    disposition = "inline" if inline else "attachment"
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quoted}"
