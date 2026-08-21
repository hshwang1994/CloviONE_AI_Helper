"""Backup records (spec §21.20)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, UUIDPrimaryKeyMixin, utcnow

STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_VERIFIED = "verified"
STATUS_FAILED = "failed"

# 덤프 형식. 옛 `sqlite` 행은 운영 DB 에 남아 있을 수 있다(S13 이 이관할 때 본다).
BACKUP_TYPE_PG_DUMP = "pg_dump"


class Backup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "backups"

    # 덤프 **형식**이다. 되돌릴 때 어떤 도구로 여는지가 이 값에 달렸다 —
    # `pg_dump` custom format 은 `pg_restore` 로만 열린다.
    #
    # 기본값이 `sqlite` 로 남아 있었다. 쓰는 쪽(`run_backup`)은 이미 `pg_dump` 를 넣지만,
    # 기본값을 그대로 두면 다른 경로로 만들어진 행이 **틀린 형식으로 이름표를 달고**
    # 목록에 선다 — 그리고 그 사실은 되돌리려는 날에야 드러난다.
    backup_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=BACKUP_TYPE_PG_DUMP
    )
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_RUNNING)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)


class RestoreRehearsal(UUIDPrimaryKeyMixin, Base):
    """복구 리허설 결과 (0033, PLAN Phase 6).

    **백업은 복원해 본 적이 없으면 백업이 아니다.** `scripts/restore_rehearsal.py` 가 이미
    그 증명을 만든다(백업 → 검증 → 복원 → 무결성 → 행 수 대조 → alembic head → 실제 부팅).
    그런데 결과가 터미널에만 남아, 관리자 화면에서는 "마지막으로 복원을 시험한 게 언제인가"에
    답할 방법이 없었다. 이 표가 그 답이다.

    앱이 스스로 리허설을 돌리지는 **않는다**. 리허설은 별도 프로세스로 앱을 한 번 더 띄우므로
    워커 틱에 넣으면 운영 중 메모리·파일핸들을 두 배로 쓴다. 스크립트를 `--record` 로 돌리면
    이 표에 한 줄이 남고, 화면은 그것을 읽는다 — 하지 않은 일을 한 것처럼 보이지 않는다.
    """

    __tablename__ = "restore_rehearsals"

    source_label: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failures_json: Mapped[str | None] = mapped_column(JsonText)
    summary_json: Mapped[str | None] = mapped_column(JsonText)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
