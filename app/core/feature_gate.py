"""기능 플래그 게이트 — 한 깃발이 **여러 라우터**를 막아야 할 때 두는 자리 (P-84).

## 왜 라우터 밖으로 나왔나

`team_docs_enabled` 는 원래 `app/team_docs/router.py` 안의 함수 하나가 지켰다. 그런데 문서의
정본 API 는 `/api/knowledge/*`(`app/knowledge/router.py`)이고, 그쪽에는 이 게이트가 없었다.
그래서 깃발을 끈 테넌트에서 사이드바 메뉴는 사라지는데(`/api/me` 의 `features` 와
`navConfig.js::NAV_FEATURE_FLAG`), 공유받은 `#/knowledge/<id>` 는 정상적으로 열렸다 —
운영자는 「문서를 껐다」고 믿고, 서버는 문서를 전부 내줬다. 두 층이 다른 말을 했다.

게이트가 라우터 파일 안에 있으면 두 번째 라우터는 그 파일을 import 하거나 같은 함수를
베껴야 한다. 베끼면 문구·기본값이 갈라지고, 한쪽만 고치는 날이 온다. 그래서 함수를 한 벌만
두고 두 라우터가 같은 것을 건다. **커버리지는 `tests/security/test_feature_flag_gate_coverage.py`
가 의존성 그래프로 지킨다** — 어느 라우터에 어떻게 걸었든, `/api/knowledge`·`/api/team-docs`
아래 라우트 전부가 이 함수를 지나야 한다.

다른 깃발(`board_enabled`·`games_enabled`·`team_chat_enabled`·`chat_enabled`)은 지금 라우터
하나씩만 막으므로 각자의 라우터에 그대로 있다. 두 번째 소비자가 생기면 그때 여기로 온다 —
미리 옮기면 「어디에 있나」만 두 벌이 된다.

## `/api/trash` 는 막지 않는다

휴지통은 티켓과 문서를 **한 목록에** 담는다(`app/trash/router.py`). 문서 깃발로 휴지통을
막으면 문서를 끈 테넌트가 티켓 휴지통까지 잃고, 문서 항목만 걸러 내려면 휴지통이 문서
깃발을 알아야 한다. 휴지통에 남은 문서 항목의 **복원 대상 화면**이 이 깃발로 닫혀 있는
것은 별개의 사실이고, 그 화면으로 가는 링크는 프런트가 같은 깃발로 감춘다.

## 응답은 404 다

꺼진 기능은 「없는 것」으로 답한다. 403 은 「있는데 당신은 안 된다」라서, 깃발을 끈 이유가
기능 자체를 숨기는 것이라면 맞지 않는다. 다른 깃발 게이트도 전부 404 다.
"""

from __future__ import annotations

from fastapi import Request

from app.core.errors import NotFoundError
from app.core.feature_flags import load_feature_flags


def require_team_docs_enabled(request: Request) -> None:
    """문서 기능 깃발. `/api/team-docs`(옛 미러)와 `/api/knowledge`(정본) 둘 다 이것을 건다.

    인증보다 먼저 판정한다 — 꺼진 기능은 로그인 여부와 무관하게 없는 것이어야 하고, 이것은
    옛 라우터가 처음부터 하던 순서다(라우터 의존성 목록에서 `block_if_maintenance` 앞).
    """
    flags = load_feature_flags(request.app.state.settings.config_dir)
    if not flags.get("team_docs_enabled", True):
        raise NotFoundError("문서 기능이 비활성화되어 있습니다.")
