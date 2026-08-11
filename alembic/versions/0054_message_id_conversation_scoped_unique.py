"""client_message_id 유일성을 대화 단위로 좁힌다 — 전역 유일이 존재-여부 오라클이었다 (UB-23)

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-11

## 무엇이 문제였나

`messages.message_id`는 클라이언트가 정하는 멱등성 키(중복 전송 방지, spec §13.4)인데
**전역** UNIQUE였다. `app/chat/service.py::post_user_message`의 존재 확인은
`WHERE message_id = :id` 하나뿐이라 소유자(대화) 필터가 없다 — 어느 사용자든 임의의
`client_message_id` 문자열을 POST해 보면, 201(새로 만들어짐)과 409(다른 대화에서 이미
쓰임)로 **그 문자열이 시스템 어딘가에 이미 존재하는지**를 알 수 있었다(다른 사용자의
대화에 속한 메시지라도).

거기 더해 워커가 만드는 파생 id(`f"a-{message.message_id}-fail-{job.id}"`,
`app/jobs/handlers/chat_message.py`)도 같은 전역 네임스페이스를 쓴다. 사용자 자신의
`client_message_id`가 우연히 이 패턴과 겹치면(자기 자신이 아니라 시스템 전체 다른 어떤
메시지의 실패-안내 id와) 전혀 새 메시지인데도 "이미 다른 대화에서 사용된 메시지
ID입니다"라는 뜻모를 409를 받는다.

## 고치는 법

유일성을 `(conversation_id, message_id)` 복합키로 좁힌다 — 멱등성 키는 원래
"이 대화 안에서" 중복 제출을 막으려는 것이었지 시스템 전체를 대상으로 한 적이 없다.
서비스 계층(`app/chat/service.py`, `app/jobs/handlers/chat_message.py`)의 조회도 함께
`conversation_id`로 좁힌다(별도 커밋).

## 기존 데이터는 안전하다

기존 제약이 이미 전역 유일이었으므로, 그보다 **약한**(대화로 좁힌) 제약을 기존 행이
위반할 수 없다 — 0053과 달리 배포 전 정리(dedup)가 필요 없다.

## SQLite에서 컬럼 UNIQUE를 복합 UNIQUE로 바꾸려면 표를 다시 만들어야 한다

실측(2026-08-11): `Column(unique=True)`로 선언한 이 컬럼은 SQLAlchemy 리플렉션에
**제약이 아니라 이름 있는 인덱스**(`uq_messages_message_id`, `get_indexes()`에서
`unique=1`)로 나타난다 - `get_unique_constraints()`는 빈 목록을 돌려준다. 그래서
`batch.drop_constraint()`가 아니라 `batch.drop_index()`로 지운다. `messages`를
가리키는 FK나 FTS 트리거는 없다(그런 것들이 있는 0050의 search_documents처럼 추가
처리가 필요 없다) - 확인함.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

_OLD_UNIQUE_NAME = "uq_messages_message_id"
_NEW_UNIQUE_NAME = "uq_messages_conversation_message_id"


def upgrade() -> None:
    bind = op.get_bind()
    if "messages" not in sa.inspect(bind).get_table_names():
        return
    indexes = {i["name"] for i in sa.inspect(bind).get_indexes("messages")}
    with op.batch_alter_table("messages", recreate="always") as batch:
        if _OLD_UNIQUE_NAME in indexes:
            batch.drop_index(_OLD_UNIQUE_NAME)
        batch.create_unique_constraint(_NEW_UNIQUE_NAME, ["conversation_id", "message_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if "messages" not in sa.inspect(bind).get_table_names():
        return
    with op.batch_alter_table("messages", recreate="always") as batch:
        batch.drop_constraint(_NEW_UNIQUE_NAME, type_="unique")
        # 이 시점 데이터에 대화가 다른 중복 message_id가 있으면(이 마이그레이션이 적용된
        # 뒤에만 생길 수 있다) 아래가 실패한다 — 의도적이다: 전역 유일을 되살리려면 그
        # 위반이 실제로 없어야 한다.
        batch.create_unique_constraint(_OLD_UNIQUE_NAME, ["message_id"])
