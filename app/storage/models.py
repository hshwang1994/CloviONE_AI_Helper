"""File Storage 표 (S8) — 저장소 · 파일 metadata.

## Binary 는 DB 에 안 들어간다 (D-199)

DB 는 metadata 를 들고, 실체는 Provider 가 든다. 이유는 백업 크기도 성능도 아니라
**복구 가능성**이다: 파일이 DB 안에 있으면 「DB 는 살아 있는데 파일만 잃었다」와
「파일은 살아 있는데 DB 만 잃었다」를 나눌 수 없고, 둘을 나눌 수 없으면 부분 복구가
불가능하다.

## `files` 와 `storage_providers` 가 함께 서는 이유

S7 이 `document_attachments` 를 **일부러 안 만들었다.** 첨부는 `files` 를 가리키고
`files` 는 `storage_providers` 를 가리킨다. 저장소 없이 첨부 표만 만들면 그 컬럼이
무엇을 가리키는지 정하지 못한 채 굳는다. 그래서 셋이 같은 마이그레이션에서 선다.

## 경로를 `config` jsonb 에 묻지 않는다

D-199 의 초안은 `storage_providers(id, kind, config jsonb, role, enabled)` 다. 여기서
`base_path` 와 `mount_point` 를 **이름 있는 컬럼**으로 올렸다. 마운트 가드가 매 쓰기마다
그 값을 읽는데, jsonb 키 이름을 한 글자 틀리면 값이 `None` 이 되고 가드는 「경로가
없다」로 조용히 넘어간다. 컬럼이면 그 오타가 기동 시점에 드러난다.

`config` 는 남는다 — 마운트 소스(`nas:/export`)와 옵션처럼 **앱이 해석하지 않고
systemd 에 넘기기만 하는 값**이 그 자리다.

## 비밀번호는 여기 없다

SMB 자격증명은 `credentials_ref` 이름만 들고, 실제 값은 `secrets_dir/<ref>` 파일에
있다(CLAUDE.md §6.3). DB 를 덤프해도 자격증명은 안 나온다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import (
    Base,
    JsonText,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    utcnow,
)
from app.storage.adapters import KIND_LOCAL, KINDS, ROLE_OPERATIONAL, ROLES


def _in_list(column: str, values: tuple[str, ...]) -> str:
    """`col IN ('a','b')` — CHECK 제약을 상수 튜플에서 만든다.

    `app/knowledge/models.py` 와 같은 이유다. 손으로 다시 적으면 상수를 늘린 날 제약만
    옛 목록에 남고, 새 값이 조용히 거절된다.
    """
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class StorageProvider(TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """파일이 실제로 사는 곳 하나.

    ## 역할마다 켜진 것은 하나뿐이다

    부분 유니크 인덱스로 강제한다. 「업로드가 어디로 가는가」에 답이 둘이면 어제 올린
    파일과 오늘 올린 파일이 다른 장치에 있고, 그 사실은 백업을 복원할 때 처음 드러난다.

    ## `enabled` 를 끄는 것은 지우는 것이 아니다

    저장소를 지우면 그 위의 `files` 행이 무엇을 가리키는지 알 수 없게 된다. 그래서
    `files.storage_provider_id` 는 `RESTRICT` 이고, 옮겨 가려면 파일을 먼저 옮긴다.
    """

    __tablename__ = "storage_providers"

    #: 사람이 부르는 이름. 화면과 로그가 이것을 쓴다.
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=KIND_LOCAL, server_default=KIND_LOCAL, index=True
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ROLE_OPERATIONAL,
        server_default=ROLE_OPERATIONAL, index=True,
    )
    #: 앱이 실제로 쓰는 절대 경로. NFS/SMB 면 `mount_point` 아래여야 한다.
    base_path: Mapped[str] = mapped_column(Text, nullable=False)
    #: 마운트를 묻는 자리. LOCAL 은 NULL 이다.
    mount_point: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: systemd 에 그대로 넘기는 값들(`{"source": …, "options": …}`). 앱은 해석하지 않는다.
    config_json: Mapped[str] = mapped_column(
        JsonText, nullable=False, default="{}", server_default="{}"
    )
    #: `secrets_dir` 안의 파일 이름. **값이 아니라 이름이다.**
    credentials_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    __table_args__ = (
        CheckConstraint(_in_list("kind", KINDS), name="ck_sprov_kind"),
        CheckConstraint(_in_list("role", ROLES), name="ck_sprov_role"),
        CheckConstraint("length(btrim(name)) > 0", name="ck_sprov_name_nonempty"),
        # 절대 경로만 받는다. 상대 경로는 프로세스의 작업 디렉터리에 따라 다른 곳을
        # 가리키고, 워커와 웹은 작업 디렉터리가 같다는 보장이 없다.
        #
        # **드라이브 문자를 함께 허용한다**(`C:/…`). 제품이 도는 곳은 Ubuntu 뿐이고
        # 거기서는 첫 갈래만 쓰이지만, 개발·시험 머신은 Windows 다. POSIX 모양만
        # 받으면 저장소 도메인이 그 머신에서 **한 건도 시험되지 않는다** — 이 제약이
        # 막으려는 것은 「상대 경로」이지 「Windows」가 아니다.
        CheckConstraint(
            "base_path LIKE '/%' OR base_path ~ '^[A-Za-z]:/'",
            name="ck_sprov_base_absolute",
        ),
        CheckConstraint(
            "mount_point IS NULL OR mount_point LIKE '/%' "
            "OR mount_point ~ '^[A-Za-z]:/'",
            name="ck_sprov_mount_absolute",
        ),
        # 마운트가 필요한 종류에는 마운트포인트가 있고, LOCAL 에는 없다. 이 짝이
        # 어긋나면 가드가 물어야 할 자리를 모른다.
        CheckConstraint(
            "(kind = 'LOCAL') = (mount_point IS NULL)", name="ck_sprov_mount_pair"
        ),
        Index("uq_sprov_name", "name", unique=True),
        Index("ix_sprov_role_enabled", "role", "enabled"),
        # 역할마다 **켜진 것은 하나**. 부분 유니크라 꺼 둔 저장소는 몇 개든 남길 수
        # 있다 — 옮겨 가는 중에는 옛 저장소를 꺼서 남겨 둬야 파일을 마저 읽는다.
        Index(
            "uq_sprov_role_enabled", "role", unique=True,
            postgresql_where=text("enabled"),
        ),
    )


class File(UUIDPrimaryKeyMixin, Base):
    """저장된 파일 하나의 metadata. **바이트는 여기 없다.**

    `updated_at` 이 없다. 파일은 고쳐지지 않는다 — 내용이 바뀌면 그것은 **다른 파일**이고
    새 행이다. 그래야 `checksum_sha256` 이 영원히 그 행의 사실로 남는다.

    ## `storage_key` 는 서버가 만든다

    `ab/cd/<uuid32><ext>`. 사용자 파일명은 `filename` 에 표시용으로만 남고 경로가 되지
    않는다. `app/core/uploads.py` 가 옛 미러에서 같은 규칙을 쓰고 있고, 이유도 같다.
    """

    __tablename__ = "files"

    storage_provider_id: Mapped[str] = mapped_column(
        String(36),
        # 파일이 남아 있는 저장소는 못 지운다. 지울 수 있게 하면 그 행들이 어느 장치를
        # 가리켰는지 아무도 모르게 된다.
        ForeignKey("storage_providers.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(120), nullable=False)
    #: 사용자가 올린 이름. 살균해서 저장하고 표시에만 쓴다.
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: 「무엇에 딸린 파일인가」. `document:<id>` 처럼 적는다. 접근 판정은 이 값이 아니라
    #: **참조하는 표**가 한다(첨부는 문서의 가시성을 따른다).
    owner_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_file_size_positive"),
        CheckConstraint("length(checksum_sha256) = 64", name="ck_file_checksum_len"),
        CheckConstraint("length(btrim(filename)) > 0", name="ck_file_name_nonempty"),
        # 같은 저장소 안에서 키는 유일하다. 두 행이 한 파일을 가리키면 한쪽을 지울 때
        # 다른 쪽이 조용히 깨진다.
        Index("uq_file_provider_key", "storage_provider_id", "storage_key", unique=True),
        Index("ix_file_owner_ref", "owner_ref", "created_at"),
    )
