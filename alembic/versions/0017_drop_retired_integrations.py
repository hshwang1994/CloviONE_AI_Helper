"""걷어낸 런타임이 남긴 연동 등록 행을 지운다 (관리자 대시보드 · 실제 데이터).

Revision ID: 0017_drop_retired_integrations
Revises: 0016_document_axis_to_documents
Create Date: 2026-08-26

## 무엇이 문제였나

운영 설치의 `integrations` 표에 네 행이 남아 있다(2026-08-26 실측).

    n8n                        n8n           http://127.0.0.1:5678   enabled  down
    claude-ticket-runner       http_service  http://127.0.0.1:8787   enabled  down
    claude-request-interpreter http_service  http://127.0.0.1:8788   enabled  down
    clovirone-work-assistant   http_service  http://127.0.0.1:8789   enabled  down

넷 다 **S11 이 걷어낸 런타임**이다. 그 포트에는 아무도 안 듣고(WORK_STATE 「옛 포트
5678·5679·8787·8788·8789 청취 0건」), `app/runners/` 는 빈 디렉터리이며, 시드 목록
(`app/integrations/discovery.py::KNOWN_INTEGRATIONS`)도 비어 있어 다시 생기지 않는다.

그래서 워커의 자동 헬스 스윕(`run_all_integration_health_checks`)이 30초마다 넷을
`down` 으로 다시 적고, 관리자 대시보드는 그것을 **「중단 · 위험」 네 줄**로 맨 위에
올린다. 정상적으로 돌고 있는 제품이 매일 장애 상태로 보였다. 「서비스 정상 3 / 7」도
같은 자리에서 나온 값이다 — 필수 서비스 셋과 이 넷을 한 분모에 넣은 결과다.

`clovirone-work-assistant` 는 여기에 더해 **옛 제품 이름**을 관리자 화면에 그대로
띄우고 있었다(§10-13 Legacy Identity 잔존 없음). D-328 이 `env` 의 죽은 두 줄에서
같은 판단을 했다 — 설정 보존은 죽은 줄까지 보존하는 것이 아니다.

## 왜 화면이 아니라 데이터를 고치는가

이름을 화면에서 숨기면 대시보드만 조용해지고 데이터는 그대로다. 헬스 스윕은 계속
없는 주소로 나가고(30초마다 네 번), `/setup` 체크리스트와 진단 화면은 여전히 넷을
「응답하지 않는 연동」으로 센다. 죽은 등록 행은 UI 문제가 아니라 데이터 문제다.

**제품에는 연동을 지우는 경로가 없다** — `app/integrations/router.py` 에는 생성·수정·
활성/비활성·헬스체크·롤백만 있고 DELETE 가 없다. 그래서 운영자가 콘솔에서 이 넷을
치울 방법이 애초에 없었다(비활성으로 눕히는 것이 최선이었고, 그러면 「사용 안 함」
으로 영원히 목록에 남는다). 없는 화면을 새로 만들지 않고, 0015 가 죽은 `sync_status`
행에 한 것과 같은 방식으로 여기서 한 번 치운다.

## 아는 이름만 지운다

이름 하나만 보고 지우지 않는다 — 운영자가 우연히 같은 이름으로 **살아 있는** 연동을
등록했을 수 있다. 이름과 주소가 **둘 다** 맞을 때만 지운다. 주소는 그 런타임이 쓰던
루프백 포트라 지금 제품의 어떤 구성요소도 쓰지 않는다.

`config_versions` 의 스냅샷 행은 건드리지 않는다. 그 표는 이 회차의 문제(헬스 계산과
경고)에 아무것도 싣지 않고, 되돌리기·목록 두 경로 모두 부모 행을 먼저 찾으므로
(`get_integration_or_404`) 부모가 없어진 뒤에는 화면에 도달하지도 않는다.

## 되감기

**되감을 수 없다.** 지운 행의 `capabilities_json`·`secret_ref`·`description` 을 이
파일이 모른다. 조용히 통과하면 되감기를 돌린 사람이 원래 상태로 돌아왔다고 믿는다 —
0015 와 같은 이유로 로그에 그 사실을 남기고 지나간다.
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = '0017_drop_retired_integrations'
down_revision = '0016_document_axis_to_documents'
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

#: (등록 이름, 그 런타임이 쓰던 base_url). **둘 다** 맞아야 지운다.
#:
#: 이 목록에 걷어낸 엔진 이름이 글자로 남는 것은 **지우기 위해서**다 — 부르기 위해서가
#: 아니다(deploy/install.sh 의 죽은 env 키 목록과 같은 사정이고, 같은 `S11` 표식을 단다).
REMOVED_RUNTIME_INTEGRATIONS = (
    ("n8n", "http://127.0.0.1:5678"),                        # S11 이 걷어낸 엔진
    ("claude-ticket-runner", "http://127.0.0.1:8787"),       # S11 이 걷어낸 러너
    ("claude-request-interpreter", "http://127.0.0.1:8788"),  # S11 이 걷어낸 러너
    ("clovirone-work-assistant", "http://127.0.0.1:8789"),   # S11 이 걷어낸 러너
)


def delete_removed_runtime_integrations(bind) -> int:
    """걷어낸 런타임의 등록 행만 지우고 지운 수를 돌려준다.

    함수로 빼 둔 이유는 0015 와 같다 — 시험이 같은 문장을 그대로 돌려 봐야 「이 회차가
    무엇을 지우는가」를 재게 된다. 시험이 SQL 을 다시 적으면 시험이 무엇을 지우는지를
    재는 것이 된다.
    """
    statement = sa.text(
        "DELETE FROM integrations WHERE name = :name AND base_url = :base_url"
    )
    removed = 0
    for name, base_url in REMOVED_RUNTIME_INTEGRATIONS:
        result = bind.execute(statement, {"name": name, "base_url": base_url})
        removed += int(result.rowcount or 0)
    return removed


def upgrade() -> None:
    removed = delete_removed_runtime_integrations(op.get_bind())
    if removed:
        logger.info("걷어낸 런타임의 연동 등록 행 %d개를 지웠습니다.", removed)
    else:
        logger.info("걷어낸 런타임의 연동 등록 행이 없습니다.")


def downgrade() -> None:
    # 스키마를 하나도 안 바꾸므로 여기서 막지 않는다. 막으면 되돌릴 이유가 전혀 다른
    # 뒷 회차들까지 이 지점에서 함께 멈춘다(0015 와 같은 판단).
    logger.warning(
        "지운 연동 등록 행은 되돌릴 수 없습니다. 그 행의 인증 방식과 capabilities 를 "
        "이 회차가 갖고 있지 않고, 그 값을 만들던 런타임도 이미 없습니다."
    )
