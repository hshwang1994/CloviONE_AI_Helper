"""색인 파이프라인 — 문서 하나를 chunk 와 벡터로 바꾸는 곳.

    Upload → 원본 저장 → 검사 → Parsing → 구조 추출 → Chunk → Embedding → Search Ready

앞의 셋(업로드·저장·검사)은 S8 이 이미 한다. 이 파일이 하는 것은 뒤의 넷이다.

## 🔴 생성 Adapter 가 없어도 여기는 돈다

색인은 **임베딩까지**가 일이고 임베딩은 CPU Local 이다(D-200). 자연어 생성 Provider 가
없어도 파싱·chunk·임베딩은 그대로 돈다. 임베딩 모델까지 없으면 chunk 는 만들고 벡터
칸을 **NULL 로 둔다** — 그 상태에서 키워드 검색은 이미 되고, 모델이 생기면 그때
`embedding IS NULL` 인 chunk 만 채운다.

이것을 「AI 없이도 전부 된다」로 적지 않는다(D-201). 요약·분석·문서생성은 생성
Provider 가 필요하고, 그것이 없으면 그 기능은 **정지**한다.

## 상태가 곧 작업 목록이다

`ai_index_state` 한 표가 「할 일」과 「끝난 일」을 함께 들고 있다. 큐를 따로 두면
큐에서 사라졌는데 결과가 없는 상태가 만들어지고, 그 상태는 아무 화면에도 안 나온다.

신호(문서 저장 시 `enqueue`)와 훑기(`sweep_stale`)를 **둘 다** 쓴다. 신호 하나만
믿으면 신호를 빠뜨린 문서가 영원히 옛 내용으로 남고, 그것이 가장 알아채기 어려운
결함이다 (`app/search/indexer.py` 가 같은 이유로 전체 재구축을 골랐다).

## 같은 글은 다시 임베딩하지 않는다

문서를 한 글자 고쳐도 chunk 는 전부 다시 만들어진다. 그런데 그중 바뀐 것은 보통
하나뿐이다. 그래서 지우기 전에 **글 지문 → 벡터** 표를 만들어 두고, 지문이 같고
모델·판도 같으면 그 벡터를 그대로 옮긴다. 임베딩이 이 파이프라인에서 가장 비싼
단계라 이 재사용이 곧 색인 시간이다.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai import catalog, chunking
from app.ai.gateway import contract
from app.ai.models import (
    ANCHOR_BLOCK,
    SOURCE_DOCUMENT,
    SOURCE_FILE,
    STATE_FAILED,
    STATE_OK,
    STATE_PENDING,
    VECTOR_INDEX_THRESHOLD,
    AiIndexState,
    DocumentChunk,
)
from app.ai.parsing import registry as parsers
from app.ai.parsing.base import PARSE_OK, PARSE_UNSUPPORTED, ParsedUnit
from app.core.errors import NotFoundError, StorageUnavailableError
from app.core.models_base import utcnow
from app.knowledge import blocks
from app.knowledge.models import Document, DocumentAttachment, DocumentVersion
from app.storage.models import File

logger = logging.getLogger("app.ai.index")

#: 실패한 문서를 다시 잡기까지의 대기. 곧바로 다시 잡으면 못 읽는 파일 하나가 레인을
#: 통째로 돌린다(그리고 그 사이 다른 문서는 한 건도 색인되지 않는다).
RETRY_BASE_SECONDS = 60
RETRY_MAX_SECONDS = 3600

#: 한 문서에서 만드는 chunk 수 상한. 넘으면 앞부분만 싣는다 — 파서 상한을 이미
#: 지났는데도 chunk 가 이만큼 나오는 문서는 색인 대상이라기보다 데이터 덤프다.
MAX_CHUNKS_PER_DOCUMENT = 2000

#: 블록 앵커의 사람이 읽는 이름을 만들 때 쓰는 길이.
_LABEL_CHARS = 40


@dataclass(frozen=True)
class IndexVersions:
    """지금 색인이 「최신」이라고 부르는 판 셋."""

    parser: str
    embedding_model: str
    embedding_version: str


def current_versions(gateway: contract.Gateway) -> IndexVersions:
    """모델이 없으면 임베딩 판은 빈 문자열이다 — 그 상태의 chunk 도 최신이다.

    이것이 이 함수의 요점이다. 모델이 없는 설치에서 「임베딩 판이 안 맞는다」로
    매 tick 마다 전 문서를 다시 색인하면, 아무 벡터도 안 만들면서 CPU 만 태운다.
    """
    cap = gateway.capabilities().embed
    if not cap.available:
        return IndexVersions(parser=catalog.PARSER_VERSION, embedding_model="", embedding_version="")
    return IndexVersions(
        parser=catalog.PARSER_VERSION,
        embedding_model=cap.model,
        embedding_version=catalog.EMBEDDING_VERSION,
    )


# ── 신호 ─────────────────────────────────────────────────────────────────────


def enqueue(db: Session, document_id: str, *, now: datetime | None = None) -> AiIndexState:
    """이 문서를 다시 색인해야 한다고 적는다. **문서를 저장한 트랜잭션 안에서 부른다.**

    행 하나를 쓰는 것이 전부라 저장 경로에 얹어도 무겁지 않다. 그리고 같은
    트랜잭션이라 「저장은 됐는데 색인 신호는 안 갔다」가 생기지 않는다.
    """
    now = now or utcnow()
    state = db.execute(
        select(AiIndexState).where(AiIndexState.document_id == document_id)
    ).scalar_one_or_none()
    if state is None:
        state = AiIndexState(document_id=document_id, queued_at=now, status=STATE_PENDING)
        db.add(state)
        # 🔴 여기서 flush 한다. 이 저장소의 세션은 `autoflush=False` 다
        # (`app/core/db.py::make_session_factory`) — 안 하면 바로 다음 `select` 이 이 행을
        # 못 보고, 같은 문서에 상태 행을 **두 개** 만든다. 그 둘은 부분 유니크가 커밋
        # 시점에 거절하므로, 실패가 이 자리가 아니라 저 멀리 커밋에서 터진다.
        db.flush()
        return state
    state.status = STATE_PENDING
    state.queued_at = now
    # 다시 신호가 왔다는 것은 내용이 바뀌었다는 뜻이다. 옛 실패의 대기 시간을 그대로
    # 두면 방금 고친 문서를 한 시간 뒤에야 본다.
    state.next_attempt_at = None
    state.attempts = 0
    state.last_error = ""
    return state


def enqueue_all(db: Session, *, now: datetime | None = None) -> int:
    """전 문서를 `pending` 으로. 모델을 바꿨을 때 부르는 그 함수다 (D-203 재생성 경로)."""
    now = now or utcnow()
    ids = list(db.execute(select(Document.id)).scalars().all())
    for document_id in ids:
        enqueue(db, document_id, now=now)
    return len(ids)


# ── 훑기 ─────────────────────────────────────────────────────────────────────


def sweep_stale(
    db: Session, *, versions: IndexVersions, now: datetime | None = None, limit: int = 200
) -> int:
    """낡은 상태 행을 `pending` 으로 되돌린다. **신호를 빠뜨린 문서의 안전망이다.**

    낡음의 정의 넷:
      * 상태 행이 아예 없다(새 문서 · 이관 직후)
      * 색인한 판이 문서의 현재 판과 다르다
      * 파서·임베딩 모델·임베딩 판이 지금 것과 다르다
      * 첨부 집합의 지문이 다르다(본문은 그대로인데 파일이 붙거나 떨어졌다)
    """
    now = now or utcnow()
    touched = 0

    # 상태 행이 없는 문서.
    missing = db.execute(
        select(Document.id)
        .outerjoin(AiIndexState, AiIndexState.document_id == Document.id)
        .where(AiIndexState.id.is_(None))
        .limit(limit)
    ).scalars().all()
    for document_id in missing:
        enqueue(db, document_id, now=now)
        touched += 1

    if touched >= limit:
        return touched

    rows = db.execute(
        select(AiIndexState, Document.current_version_id)
        .join(Document, Document.id == AiIndexState.document_id)
        .where(AiIndexState.status == STATE_OK)
    ).all()
    # 🔴 지문을 **한 질의로 한꺼번에** 만든다. 문서마다 따로 물으면 문서 1,238건에
    # 질의가 1,238번이고, 그것이 매 tick 마다 돈다. 훑기는 안전망이지 부하가 아니다.
    fingerprints = attachment_fingerprints(db, [state.document_id for state, _ in rows])
    for state, current_version_id in rows:
        if touched >= limit:
            break
        if _is_current(
            state, current_version_id, versions, fingerprints.get(state.document_id, _EMPTY_FINGERPRINT)
        ):
            continue
        enqueue(db, state.document_id, now=now)
        touched += 1
    return touched


def _is_current(
    state: AiIndexState, current_version_id, versions: IndexVersions, fingerprint: str
) -> bool:
    return (
        state.indexed_version_id == current_version_id
        and state.parser_version == versions.parser
        and state.embedding_model == versions.embedding_model
        and state.embedding_version == versions.embedding_version
        and state.attachment_fingerprint == fingerprint
    )


def _fingerprint_of(pairs) -> str:
    """`(파일 id, 체크섬)` 목록 → 지문. **id 와 체크섬을 함께** 넣는다.

    id 만 넣으면 같은 자리의 파일을 바꿔 끼웠을 때 지문이 안 바뀐다. 체크섬만 넣으면
    같은 내용의 파일 둘을 서로 바꿔 단 것을 못 잡는다. 둘 다 넣고 정렬한다.
    """
    joined = "|".join(sorted(f"{file_id}:{checksum}" for file_id, checksum in pairs))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


#: 첨부가 하나도 없는 문서의 지문. 「없다」도 값이라 빈 문자열로 두지 않는다 — 그러면
#: 「아직 안 재 봤다」와 구별되지 않는다.
_EMPTY_FINGERPRINT = _fingerprint_of(())


def attachment_fingerprints(db: Session, document_ids) -> dict[str, str]:
    """문서 여러 건의 첨부 지문을 **한 질의로**.

    `sweep_stale` 이 매 tick 마다 부르는 자리라 문서마다 따로 묻지 않는다. 지문을 만드는
    규칙은 `_fingerprint_of` 하나뿐이다 — SQL 로 같은 해시를 다시 만들면 구현이 두 벌이
    되고, 그 둘은 언젠가 갈린다.
    """
    ids = list(dict.fromkeys(document_ids))
    if not ids:
        return {}
    rows = db.execute(
        select(DocumentAttachment.document_id, File.id, File.checksum_sha256)
        .join(File, File.id == DocumentAttachment.file_id)
        .where(DocumentAttachment.document_id.in_(ids))
    ).all()
    grouped: dict[str, list] = {}
    for document_id, file_id, checksum in rows:
        grouped.setdefault(document_id, []).append((file_id, checksum))
    return {document_id: _fingerprint_of(grouped.get(document_id, ())) for document_id in ids}


def _attachment_fingerprint(db: Session, document_id: str) -> str:
    return attachment_fingerprints(db, [document_id]).get(document_id, _EMPTY_FINGERPRINT)


# ── 작업 잡기 ────────────────────────────────────────────────────────────────


def claim(db: Session, *, now: datetime | None = None, limit: int = 20) -> list[AiIndexState]:
    """지금 할 일. `SKIP LOCKED` 로 잡는다 — 레인이 둘 뜨는 순간에도 같은 문서를
    두 번 색인하지 않는다(리스가 그것을 막지만, 리스 교대의 좁은 창이 있다)."""
    now = now or utcnow()
    return list(
        db.execute(
            select(AiIndexState)
            .where(
                AiIndexState.status.in_((STATE_PENDING, STATE_FAILED)),
                (AiIndexState.next_attempt_at.is_(None))
                | (AiIndexState.next_attempt_at <= now),
            )
            .order_by(AiIndexState.queued_at, AiIndexState.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars().all()
    )


# ── 파이프라인 ───────────────────────────────────────────────────────────────


def index_one(
    db: Session,
    state: AiIndexState,
    *,
    gateway: contract.Gateway,
    versions: IndexVersions,
    now: datetime | None = None,
) -> bool:
    """문서 하나를 색인한다. `True` 면 성공이다. **예외를 올리지 않는다.**"""
    now = now or utcnow()
    state.attempts += 1
    document = db.get(Document, state.document_id)
    if document is None:
        # 문서가 사라졌다. 상태 행은 FK CASCADE 로 함께 사라질 것이고, 그 전에 본
        # 이번 tick 은 그냥 넘어간다.
        db.delete(state)
        return True
    try:
        units = _collect_units(db, document)
    except StorageUnavailableError:
        # 저장소가 안 붙었다. **결함이 아니라 상태**다 — 다시 시도한다.
        return _fail(state, "저장소에 지금 접근할 수 없습니다.", now=now)
    except Exception:  # noqa: BLE001 - 문서 하나 때문에 레인이 죽지 않는다
        logger.exception("문서를 읽지 못했다 document_id=%s", state.document_id)
        return _fail(state, "문서를 읽지 못했습니다.", now=now)

    chunks = _build_chunks(units)
    reusable = _existing_vectors(db, state.document_id, versions)
    # 🔴 문서 하나의 쓰기를 SAVEPOINT 로 감싼다. 한 문서의 chunk 하나가 제약을 어기면
    # 그 문서만 실패해야 한다 — 안 감싸면 그 실패가 **커밋 시점에** 터지고, 같은 tick 에
    # 멀쩡히 색인된 나머지 열아홉 건이 함께 되감긴다. 그리고 다음 tick 이 같은 문서를
    # 다시 잡아 같은 자리에서 또 죽는다.
    try:
        with db.begin_nested():
            db.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == state.document_id)
            )
            embedded = _write_chunks(
                db, document, chunks, reusable=reusable, gateway=gateway,
                versions=versions, now=now,
            )
            # 여기서 flush 한다. 안 하면 제약 위반이 이 문서의 실패가 아니라 tick 전체의
            # 실패로 나타난다.
            db.flush()
    except SQLAlchemyError:
        logger.exception("chunk 를 저장하지 못했다 document_id=%s", state.document_id)
        return _fail(state, "색인 결과를 저장하지 못했습니다.", now=now)

    state.status = STATE_OK
    state.indexed_version_id = document.current_version_id
    state.parser_version = versions.parser
    state.embedding_model = versions.embedding_model
    state.embedding_version = versions.embedding_version
    state.attachment_fingerprint = _attachment_fingerprint(db, state.document_id)
    state.chunk_count = len(chunks)
    state.embedded_count = embedded
    state.indexed_at = now
    state.next_attempt_at = None
    state.last_error = ""
    return True


def _fail(state: AiIndexState, message: str, *, now: datetime) -> bool:
    state.status = STATE_FAILED
    state.last_error = message[:300]
    delay = min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2 ** min(state.attempts, 6)))
    state.next_attempt_at = now + timedelta(seconds=delay)
    return False


# ── 단위 모으기 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Unit:
    """`ParsedUnit` + 출처. 파일에서 온 것인지 본문에서 온 것인지를 함께 든다."""

    source_kind: str
    file_id: str | None
    unit: ParsedUnit


def _collect_units(db: Session, document: Document) -> list[_Unit]:
    out: list[_Unit] = []
    out.extend(_document_units(db, document))
    out.extend(_attachment_units(db, document))
    return out


def _document_units(db: Session, document: Document) -> list[_Unit]:
    """본문 블록 → 단위. 앵커는 **블록 id** 다 (D-198)."""
    if not document.current_version_id:
        return []
    version = db.get(DocumentVersion, document.current_version_id)
    if version is None:
        return []
    out: list[_Unit] = []
    title = (document.title or "").strip()
    for ordinal, (block_id, _kind, text) in enumerate(blocks.iter_block_text(version.body or {})):
        if not text.strip():
            continue
        # 첫 블록에만 제목을 얹는다. 전 chunk 에 얹으면 같은 문장이 chunk 수만큼
        # 반복되어 검색에서 제목만으로도 문서 전체가 뜬다.
        body = f"{title}\n{text}" if (ordinal == 0 and title) else text
        out.append(
            _Unit(
                source_kind=SOURCE_DOCUMENT,
                file_id=None,
                unit=ParsedUnit(
                    anchor_kind=ANCHOR_BLOCK,
                    anchor_ref=block_id,
                    anchor_label=_label_of(text),
                    text=body,
                    ordinal=ordinal,
                ),
            )
        )
    return out


def _attachment_units(db: Session, document: Document) -> list[_Unit]:
    """첨부 → 단위. 글자를 못 뽑는 형식은 **건너뛴다**(결함이 아니다)."""
    rows = db.execute(
        select(File)
        .join(DocumentAttachment, DocumentAttachment.file_id == File.id)
        .where(DocumentAttachment.document_id == document.id)
        .order_by(DocumentAttachment.sort_order, File.id)
    ).scalars().all()
    out: list[_Unit] = []
    for file_row in rows:
        if not parsers.can_parse(file_row.mime_type):
            continue
        # 🔴 바이트를 전부 메모리에 올리지 않는다. `read_bytes` 는 첨부 하나가 10MB 라
        # 괜찮지만, 색인이 전량을 훑을 때는 아니다.
        from app.storage import service as storage_service

        try:
            path = storage_service.file_path(db, file_row)
        except NotFoundError:
            # 행은 있는데 바이트가 없다. 이 문서 하나를 실패로 만들지 않는다 —
            # `verify_files()` 가 그 사실을 따로 보고한다.
            logger.warning("첨부의 바이트가 없어 건너뛴다 file_id=%s", file_row.id)
            continue
        result = parsers.parse_file(path, mime_type=file_row.mime_type)
        if result.status == PARSE_UNSUPPORTED:
            continue
        if result.status != PARSE_OK:
            logger.info(
                "첨부를 읽지 못해 건너뛴다 file_id=%s status=%s", file_row.id, result.status
            )
            continue
        for unit in result.units:
            out.append(_Unit(source_kind=SOURCE_FILE, file_id=file_row.id, unit=unit))
    return out


def _label_of(text: str) -> str:
    line = (text or "").strip().split("\n", 1)[0].strip()
    return line[:_LABEL_CHARS] if line else ""


# ── chunk 만들기 ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _PreparedChunk:
    source_kind: str
    file_id: str | None
    chunk: chunking.Chunk


def _build_chunks(units: list[_Unit]) -> list[_PreparedChunk]:
    """출처별로 나눠 chunk 를 만든다.

    **본문은 앵커를 넘어 합치고, 파일은 안 합친다.** 이유는
    `app/ai/chunking.py::chunk_units` 의 docstring 에 있다 — 블록은 같은 화면 안의
    이어진 문단이고, 쪽과 슬라이드는 사용자가 각각 찾아가는 다른 자리다.
    """
    out: list[_PreparedChunk] = []
    body = [u.unit for u in units if u.source_kind == SOURCE_DOCUMENT]
    for chunk in chunking.chunk_units(body, merge_anchors=True):
        out.append(_PreparedChunk(source_kind=SOURCE_DOCUMENT, file_id=None, chunk=chunk))

    by_file: dict[str, list[ParsedUnit]] = {}
    order: list[str] = []
    for item in units:
        if item.source_kind != SOURCE_FILE or item.file_id is None:
            continue
        if item.file_id not in by_file:
            by_file[item.file_id] = []
            order.append(item.file_id)
        by_file[item.file_id].append(item.unit)
    for file_id in order:
        for chunk in chunking.chunk_units(by_file[file_id], merge_anchors=False):
            out.append(_PreparedChunk(source_kind=SOURCE_FILE, file_id=file_id, chunk=chunk))
    return out[:MAX_CHUNKS_PER_DOCUMENT]


def _existing_vectors(db: Session, document_id: str, versions: IndexVersions) -> dict:
    """글 지문 → 벡터. **모델과 판이 같은 것만** 담는다.

    다르면 그 벡터는 다른 공간의 값이라 비교할 수 없다. 재사용은 비용을 아끼는
    일이지 정확도를 깎을 일이 아니다.
    """
    if not versions.embedding_model:
        return {}
    rows = db.execute(
        select(DocumentChunk.text_sha256, DocumentChunk.embedding)
        .where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.embedding.isnot(None),
            DocumentChunk.embedding_model == versions.embedding_model,
            DocumentChunk.embedding_version == versions.embedding_version,
        )
    ).all()
    return {sha: vector for sha, vector in rows if vector}


def _write_chunks(
    db: Session,
    document: Document,
    prepared: list[_PreparedChunk],
    *,
    reusable: dict,
    gateway: contract.Gateway,
    versions: IndexVersions,
    now: datetime,
) -> int:
    """chunk 를 넣고 벡터를 채운다. 채운 개수를 돌려준다."""
    rows: list[DocumentChunk] = []
    need: list[int] = []
    for ordinal, item in enumerate(prepared):
        chunk = item.chunk
        sha = chunk.sha256
        row = DocumentChunk(
            source_kind=item.source_kind,
            document_id=document.id,
            file_id=item.file_id,
            version_id=document.current_version_id,
            ordinal=ordinal,
            anchor_kind=chunk.anchor_kind,
            anchor_ref=chunk.anchor_ref[:160],
            anchor_label=chunk.anchor_label[:200],
            text_body=chunk.text,
            text_sha256=sha,
            token_estimate=chunk.token_estimate,
            parser_version=versions.parser,
            indexed_at=now,
        )
        vector = reusable.get(sha)
        if vector is not None:
            _set_vector(row, vector, versions=versions, now=now)
        else:
            need.append(ordinal)
        rows.append(row)
        db.add(row)

    if need and versions.embedding_model:
        _embed_missing(rows, need, gateway=gateway, versions=versions, now=now)
    return sum(1 for row in rows if row.embedding is not None)


def _embed_missing(rows, need, *, gateway, versions: IndexVersions, now: datetime) -> None:
    result = gateway.embed([rows[i].text_body for i in need], kind=catalog.KIND_PASSAGE)
    if not result.ok:
        # 벡터 없이 chunk 만 남는다. **그 상태가 정상**이다 — 키워드 검색은 이미 되고,
        # `embedding IS NULL` 인 chunk 를 나중에 채우는 경로가 따로 있다.
        logger.info("임베딩을 만들지 못해 chunk 만 저장한다 status=%s", result.status)
        return
    for index, vector in zip(need, result.vectors):
        _set_vector(rows[index], vector, versions=versions, now=now)


def _set_vector(row: DocumentChunk, vector, *, versions: IndexVersions, now: datetime) -> None:
    row.embedding = tuple(vector)
    row.embedding_model = versions.embedding_model
    row.embedding_version = versions.embedding_version
    row.embedded_at = now


# ── 나중에 벡터만 채우기 ─────────────────────────────────────────────────────


def embed_pending(
    db: Session,
    *,
    gateway: contract.Gateway,
    versions: IndexVersions,
    now: datetime | None = None,
    limit: int = 200,
) -> int:
    """벡터가 비어 있는 chunk 를 채운다. **모델이 나중에 생긴 설치의 따라잡기 경로다.**

    다시 파싱하지 않는다 — 글은 이미 표에 있고 바뀐 것은 모델이 생겼다는 사실뿐이다.
    """
    now = now or utcnow()
    if not versions.embedding_model or not gateway.can(contract.CAP_EMBED):
        return 0
    rows = list(
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.embedding.is_(None))
            .order_by(DocumentChunk.document_id, DocumentChunk.ordinal)
            .limit(limit)
        ).scalars().all()
    )
    if not rows:
        return 0
    result = gateway.embed([row.text_body for row in rows], kind=catalog.KIND_PASSAGE)
    if not result.ok:
        return 0
    for row, vector in zip(rows, result.vectors):
        _set_vector(row, vector, versions=versions, now=now)
    # 세지 **전에** 쓴다. 세션이 `autoflush=False` 라 안 하면 방금 채운 벡터를 못 보고
    # 상태 행이 「하나도 안 붙었다」로 남는다.
    db.flush()
    _bump_embedded_counts(db, {row.document_id for row in rows})
    return len(rows)


def _bump_embedded_counts(db: Session, document_ids) -> None:
    for document_id in document_ids:
        state = db.execute(
            select(AiIndexState).where(AiIndexState.document_id == document_id)
        ).scalar_one_or_none()
        if state is None:
            continue
        state.embedded_count = int(
            db.execute(
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.embedding.isnot(None),
                )
            ).scalar_one()
        )


# ── 한 tick ──────────────────────────────────────────────────────────────────


def run_once(
    db: Session, *, gateway: contract.Gateway, now: datetime | None = None, limit: int = 20
) -> int:
    """훑기 → 잡기 → 색인 → 따라잡기. 처리한 문서 수를 돌려준다.

    커밋은 부르는 쪽이 한다. 한 tick 을 한 트랜잭션으로 두는 것이 요점이다 —
    중간에 죽으면 상태 행이 `pending` 그대로라 다음 tick 이 처음부터 다시 한다.
    """
    now = now or utcnow()
    versions = current_versions(gateway)
    sweep_stale(db, versions=versions, now=now, limit=limit * 5)
    states = claim(db, now=now, limit=limit)
    for state in states:
        index_one(db, state, gateway=gateway, versions=versions, now=now)
    if not states:
        # 색인할 문서가 없을 때만 따라잡기를 돈다. 둘을 같은 tick 에 하면 모델이
        # 막 생긴 설치에서 한 tick 이 지나치게 길어진다.
        embed_pending(db, gateway=gateway, versions=versions, now=now)
    # 상태 행의 변경을 내보낸다. 세션이 `autoflush=False` 라 이것을 안 하면 같은
    # 트랜잭션 안에서 상태를 읽는 쪽(대시보드·CLI·시험)이 옛 값을 본다.
    db.flush()
    return len(states)


# ── 상태 보고 ────────────────────────────────────────────────────────────────


def index_health(db: Session) -> dict:
    """`/readyz` · 대시보드 · `ai_cli status` 가 함께 쓰는 한 벌."""
    chunk_count = int(db.execute(select(func.count()).select_from(DocumentChunk)).scalar_one())
    embedded = int(
        db.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.embedding.isnot(None))
        ).scalar_one()
    )
    by_status = dict(
        db.execute(
            select(AiIndexState.status, func.count()).group_by(AiIndexState.status)
        ).all()
    )
    return {
        "chunks": chunk_count,
        "embedded": embedded,
        "pending_embedding": chunk_count - embedded,
        "documents": {
            "pending": int(by_status.get(STATE_PENDING, 0)),
            "ok": int(by_status.get(STATE_OK, 0)),
            "failed": int(by_status.get(STATE_FAILED, 0)),
        },
        # D-210 의 임계. 넘었다는 사실을 말한다 — 조용히 느려지는 것이 이 저장소가
        # 가장 싫어하는 종류의 사고다.
        "vector_index_recommended": embedded >= VECTOR_INDEX_THRESHOLD,
    }
