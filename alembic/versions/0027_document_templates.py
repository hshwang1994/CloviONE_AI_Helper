"""문서 템플릿 — 새 문서가 시작할 틀을 조직이 스스로 만들고 고친다.

Revision ID: 0027_document_templates
Revises: 0026_document_categories
Create Date: 2026-09-04

## 무엇이 문제였나

틀은 `app/knowledge/templates.py` 의 **모듈 상수 넷**이었다. 새 문서 대화상자는 그것을
고를 수 있었지만 만들거나 고칠 자리가 어디에도 없었다 — 어휘를 늘리려면 배포를 해야 했다.
분류와 태그는 이미 조직이 스스로 만드는데 틀만 코드에 얼어 있었다.

## 무엇을 하는가

1. `document_templates` 표를 만든다 — `document_categories` 와 같은 조직 스코프 규약.
2. 기존 틀 **셋**(회의록 · 요구사항 정의서 · 운영 가이드)을 조직마다 시드한다.

## 「빈 문서」는 시드하지 않는다

그것은 표의 행이 아니라 화면의 바탕이다(`templates.BLANK`). 행으로 넣으면 지울 수 있게
되고, 지워진 날 새 문서 대화상자의 **기본값**이 없는 틀을 가리킨다.

## `documents` 에 열을 더하지 않는다

「나중에 틀을 고치거나 지워도 이미 만든 문서는 안 바뀐다」가 요구다. 참조를 안 만들면 그
규칙이 코드가 아니라 **스키마**가 된다 — 본문은 문서를 만드는 순간 복사되고 그 뒤 남남이다.

## 본문 리터럴이 여기 박혀 있는 이유

마이그레이션은 app 코드를 import 하지 않는다(얼린 스키마 스냅숏이다). `templates.py` 를
읽어 시드하면 그 파일이 바뀐 날 과거 마이그레이션의 결과가 달라진다. 그래서 이관 시점의
본문을 **그대로 구워** 둔다. 두 벌이 갈라지는 것은 의도다 — 이 표가 생긴 뒤로 어휘의
정본은 표이고, 이 파일은 그때 무엇이 있었는지를 적은 기록이다.

## 시드가 멱등인 이유

`(org_id, name)` 유니크를 보고 없을 때만 INSERT 한다(0026 의 `_ensure_category` 와 같은
모양). 다시 돌려도 늘지 않고, 경합은 `uq_dtpl_name` 이 잡는다.

## 되돌리기

표 하나를 지운다. 문서는 틀을 참조하지 않으므로 **문서 쪽 손실이 없다** — 0027 이후
조직이 만든 틀만 사라진다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_document_templates"
down_revision = "0026_document_categories"
branch_labels = None
depends_on = None

_SORT_STEP = 1024

# 0027 시점의 `app/knowledge/templates.py` 본문. 위 「본문 리터럴」 절을 보라.
SEED: dict = {
        "meeting": {
            "name": "회의록",
            "help": "회의 목적과 참석자, 정한 것과 할 일을 남깁니다.",
            "body": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "회의 개요"
                            }
                        ]
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "일시와 장소"
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "참석자"
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "회의 목적"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "논의 내용"
                            }
                        ]
                    },
                    {
                        "type": "paragraph"
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "정한 것"
                            }
                        ]
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "무엇을 정했는지 한 줄로 적습니다."
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "할 일"
                            }
                        ]
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "누가 언제까지 무엇을 하는지 적습니다."
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        },
        "requirements": {
            "name": "요구사항 정의서",
            "help": "배경과 범위, 기능과 완료 기준을 정리합니다.",
            "body": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "배경과 목적"
                            }
                        ]
                    },
                    {
                        "type": "paragraph"
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "범위"
                            }
                        ]
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "이번에 하는 것"
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "이번에 하지 않는 것"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "기능 요구사항"
                            }
                        ]
                    },
                    {
                        "type": "paragraph"
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "비기능 요구사항"
                            }
                        ]
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "성능"
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "보안"
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "운영"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "완료 기준"
                            }
                        ]
                    },
                    {
                        "type": "paragraph"
                    }
                ]
            }
        },
        "ops-guide": {
            "name": "운영 가이드",
            "help": "절차와 점검 항목, 장애가 났을 때 할 일을 적습니다.",
            "body": {
                "type": "doc",
                "content": [
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "이 문서가 다루는 것"
                            }
                        ]
                    },
                    {
                        "type": "paragraph"
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "사전 준비"
                            }
                        ]
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "필요한 권한"
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "필요한 도구"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "절차"
                            }
                        ]
                    },
                    {
                        "type": "orderedList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "첫 단계를 적습니다."
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "점검"
                            }
                        ]
                    },
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": "무엇이 정상인지 적습니다."
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "heading",
                        "attrs": {
                            "level": 2
                        },
                        "content": [
                            {
                                "type": "text",
                                "text": "문제가 생기면"
                            }
                        ]
                    },
                    {
                        "type": "paragraph"
                    }
                ]
            }
        }
    }

# 시드 순서. 사전 순서에 기대지 않는다 — 사람이 보는 차례다.
SEED_ORDER = ("meeting", "requirements", "ops-guide")


def upgrade() -> None:
    op.create_table(
        "document_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("help", sa.Text(), nullable=False, server_default=""),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_dtpl_name_nonempty"),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name="document_templates_org_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="document_templates_created_by_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="document_templates_pkey"),
    )
    op.create_index(
        op.f("ix_document_templates_org_id"), "document_templates", ["org_id"]
    )
    op.create_index("uq_dtpl_name", "document_templates", ["org_id", "name"], unique=True)

    _seed(op.get_bind())


def _seed(conn) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    orgs = [row[0] for row in conn.execute(sa.text("SELECT id FROM organizations ORDER BY id")).all()]
    if not orgs:
        # 조직이 없는 설치(빈 개발 DB)에는 시드할 자리가 없다. 표만 만들고 끝낸다 —
        # `org_id` 가 NULL 인 행을 만들면 어느 조직에도 안 보이는 틀이 생긴다.
        return
    for org_id in orgs:
        for index, key in enumerate(SEED_ORDER, start=1):
            row = SEED[key]
            exists = conn.execute(sa.text(
                "SELECT id FROM document_templates WHERE org_id = :o AND name = :n"
            ), {"o": org_id, "n": row["name"]}).scalar()
            if exists:
                continue
            conn.execute(sa.text(
                "INSERT INTO document_templates"
                " (id, org_id, name, help, body, sort_order, created_by, created_at, updated_at)"
                " VALUES (:id, :o, :n, :h, CAST(:b AS jsonb), :s, NULL, :t, :t)"
            ), {
                "id": str(uuid.uuid4()), "o": org_id, "n": row["name"], "h": row["help"],
                "b": json.dumps(row["body"], ensure_ascii=False),
                "s": index * _SORT_STEP, "t": now,
            })


def downgrade() -> None:
    op.drop_index("uq_dtpl_name", table_name="document_templates")
    op.drop_index(op.f("ix_document_templates_org_id"), table_name="document_templates")
    op.drop_table("document_templates")
