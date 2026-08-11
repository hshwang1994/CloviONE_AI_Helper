"""알림 딥링크 목적지 표 (related_object_type → 화면 경로).

**표 하나만 고친다.** 예전엔 "이 알림을 누르면 어디로 가나"가 프런트 NotificationBell 의
`OBJ_ROUTE`/`OBJ_ID_PARAM` 두 개와 registry.js 에 흩어져 있었고, 새 유형이 생길 때마다
`if` 가 한 줄씩 늘었다. 목적지는 **어떤 객체가 어디에 사는지**에 대한 서버의 지식이므로
서버가 계산해서 응답에 실어 준다 — 프런트는 받은 경로로 이동만 한다.

경로는 **해시 라우터 경로**(`/chat-rooms/<id>`)다. 앞에 `#` 이 없는 것이 정상이며,
링크로 쓸 때만 `"#" + route` 로 붙인다(React Router 의 `navigate()` 는 `#` 없는 경로를 받는다).

새 유형을 추가할 때 지켜야 할 것:
- **그 화면이 실제로 그 id 를 소비해야 한다.** 소비하지 않는 화면으로 보내면 목록만 열리고
  사용자는 대상을 다시 찾아야 한다 — 그런 유형은 표에 넣지 않는다(정적 알림으로 남긴다).
- **경로는 권한과 무관하다.** 접근 통제는 서버 라우터가 한다. 프런트는 역할에 맞지 않는
  목적지를 감출 수 있지만 그건 UX 이지 경계가 아니다.
"""

from __future__ import annotations

# related_object_type → 경로 템플릿. `{id}` 가 related_object_id 자리다.
# id 가 없으면(템플릿에 `{id}` 가 있는데 값이 비었으면) 딥링크를 만들지 않는다.
RELATED_DESTINATIONS: dict[str, str] = {
    # 채팅 초대(chat_invited) — 초대된 방으로 바로 들어간다.
    "chat_room": "/chat-rooms/{id}",
    # @멘션(chat_mentioned) — 불린 그 방으로 들어간다. id 는 room_id 다.
    #
    # `chat_room` 과 경로가 같은데 왜 키를 나눴나: 목적지는 **관련 객체의 종류**로 정하는데,
    # 멘션이 가리키는 것은 '방'이 아니라 '그 방에서 나를 부른 말'이다. 한 칸으로 합치면
    # 나중에 메시지 앵커(`/chat-rooms/{id}?seq=…`)로 정밀해질 때 초대 알림까지 같이 끌려가고,
    # 그때 둘을 다시 떼려면 프런트에 유형 분기를 넣어야 한다 — 이 표를 만든 이유가 그걸
    # 없애는 것이었다. 지금 나누는 비용은 한 줄이고, 나중에 합치는 비용은 프런트 분기다.
    "chat_mention": "/chat-rooms/{id}",
    # 티켓(ticket_assigned, ticket_comment) — 티켓 상세로 바로 들어간다. id 는 Notion page id
    # 이고, `/tickets/:id` 가 그 값을 그대로 `GET /api/tickets/{page_id}` 에 쓴다
    # (frontend/src/screens/Ticket.jsx). 즉 위 첫 번째 규칙("그 화면이 실제로 그 id 를
    # 소비해야 한다")을 만족한다.
    #
    # 배정 알림을 만들면서 넣었지만 **댓글 알림(ticket_comment)도 같이 살아난다** — 그쪽은
    # related 를 이미 ("ticket", page_id) 로 싣고 있었는데 표에 칸이 없어 목적지가 늘 null
    # 이었다. 한 표만 고치면 둘 다 따라오는 것이 이 표를 만든 이유다.
    "ticket": "/tickets/{id}",
    # 팀 문서 댓글(document_comment) — 문서 상세로 바로 들어간다. id 는 Notion page id 이고
    # `/team-docs/:id` 가 그 값을 그대로 `GET /api/team-docs/{page_id}` 에 쓴다
    # (frontend/src/screens/TeamDoc.jsx). app/team_docs/service.py::_notify_document_comment 가
    # related=("document", doc.notion_page_id) 로 이미 이 유형을 보내고 있었는데 표에 칸이
    # 없어 related_route 가 늘 null 이었다 — 알림은 뜨는데 눌러도 아무 데도 안 갔다.
    #
    # 아래 document_ready 의 "document_generation" 과 이름이 비슷하지만 다른 자원이다 —
    # 이건 team_docs(§17, Notion "문서" DB 미러)이고 그건 관리 콘솔의 문서 생성 작업이다.
    "document": "/team-docs/{id}",
    # 게시판 댓글(board_comment) / 제안 상태 변경(idea_status_changed) — 그 글로 바로
    # 들어간다. id 는 board_posts.id 이고 `/board/:id`(BoardPost.jsx)가 그 값을 그대로
    # `GET /api/board/posts/{post_id}` 에 쓴다. `app/board/service.py::_notify_post_comment`
    # 가 related=("board_post", post.id) 로 이미 이 유형을 보내고 있었는데, 바로 위
    # ticket/document 항목이 추가될 때 이 자리만 표에서 빠져 related_route 가 늘 null
    # 이었다 — ticket_comment·document_comment 가 겪었던 것과 같은 결함이다.
    "board_post": "/board/{id}",
    # 승인/스케줄/작업 큐/러너 — 넷 다 같은 모양의 결함이었다: 화면은 이미 `?id=`(작업 큐만
    # `?job_id=`) 딥링크(`onQuery`)를 지원하고 백엔드도 그 id를 실어 `related=(...)`로
    # 이미 보내고 있는데(각 서비스 코드에서 직접 확인), 이 표에만 칸이 없어 `related_route`가
    # 항상 null이었다 — 예전에 이 표를 처음 만들 때 "목록 화면이라 id 자리가 없다"고 적어
    # 둔 전제가, 그 뒤 각 화면이 onQuery를 갖추면서 낡아 버렸다(ticket/document/board_post가
    # 겪었던 것과 같은 부류: 화면은 준비됐는데 서버 쪽 표만 안 따라온 경우). 넷 다 프런트의
    # 로컬 표(NotificationBell.jsx의 자체 OBJ_ROUTE/OBJ_ID_PARAM, registry/shared.js)에는
    # 이미 등록돼 있어 그 경로로는 동작해 왔다 — 이 표를 채우는 것은 새 기능이 아니라, 이
    # 모듈의 docstring이 약속하는 대로("서버가 계산해서 응답에 실어 준다") 서버를 단일
    # 출처로 되돌리는 정리다.
    #
    # 승인(approval_requested, approval_decided) — id는 approvals.id, `/approvals`
    # (registry/governance.js)가 `onQuery: p.id ? {open:"select", id:p.id} : ...`.
    "approval": "/approvals?id={id}",
    # 스케줄(schedule_disabled 등) — id는 schedules.id, `/schedules`(registry/automation.js)가
    # `onQuery: p.id ? {open:"select", id:p.id} : ...`. schedule_run(개별 실행)은 그런 화면이
    # 없어 여전히 뺀다(아래 참고) — schedule 본체와는 다른 object_type이다.
    "schedule": "/schedules?id={id}",
    # 작업 큐(job_failed 등, app/jobs/worker.py) — id는 jobs.id인데 화면의 파라미터 이름은
    # `job_id`다(다른 셋과 다름, registry/automation.js의 jobs.onQuery: `p.job_id ? ... : ...`).
    "job": "/jobs?job_id={id}",
    # 러너(runner_unavailable, app/runners/service.py 서킷브레이커 degraded) — id는
    # runners.id, `/runners`(registry/integrations.js)가
    # `onQuery: p.id ? {open:"select", id:p.id} : ...`.
    "runner": "/runners?id={id}",
    # 사용자(account_locked 등, app/auth/router.py) — id는 users.id. Users.jsx는 registry
    # 기반이 아니라 수제 화면이라 다른 화면들의 onQuery 배선을 그대로 못 쓰는데, NOTI-04R로
    # 같은 계약(단건 GET, `?id=` 쿼리, 실패 시 이유 안내)을 직접 만들었다 — 그 전까지는
    # Users.jsx 자체에 id 딥링크가 없어서 이 표에 넣어도 무의미했다(아래 참고에서 옮겨옴).
    "user": "/users?id={id}",
}

# 문서 생성 완료(document_ready)는 일부러 여기 없다. 관리 콘솔의 문서 화면은 목록 화면이라
# 경로가 `#/documents?id=…` 형태이고, 그 질의 파라미터 지식은 이미 프런트 표
# (frontend/src/screens/registry.js 의 OBJ_ROUTE/OBJ_ID_PARAM)가 `document_generation` 으로
# 들고 있다. 같은 지식을 여기 한 벌 더 쓰면 두 표가 어긋나는 날이 온다 — 그 화면이 단건
# 라우트(`/documents/{id}`)를 갖게 되면 그때 여기 한 줄 추가하고 프런트 쪽을 지운다.
# (related_object_type 은 "document_generation" 이라 위 team_docs 의 "document" 와 겹치지
# 않는다 — app/jobs/handlers/document_generate.py 참고.)

# 아직 표에 없는 관련 유형(schedule_run)은 **일부러** 비워 둔다. '#/schedules'로 보내도
# 특정 실행 한 건을 찾아 주는 딥링크가 없다(스케줄 자체와 달리 실행 이력에는 onQuery가 없다)
# — 위 docstring의 첫 번째 규칙("그 화면이 실제로 그 id를 소비해야 한다")에 걸린다. 그 화면이
# 단건 딥링크를 갖게 되는 날 여기 한 줄 추가하면 프런트는 손대지 않는다(approval/schedule/
# job/runner/user가 방금 그 경로를 그대로 밟았다).
#
# ⚠️ 이 표에 유형을 추가할 때 role도 함께 확인한다 — 대상 화면이 role 제한이 있으면(예:
# /jobs·/approvals·/users는 CONSOLE_READ_ROLES 이상만) 그 알림의 실제 수신자가 항상 그
# role 이상인지 확인해야 한다. job_failed(작업 소유자, 어떤 role이든 가능)·approval_decided
# (요청자, notify_approvers 문서에 위임받은 일반 사용자도 포함될 수 있다고 적혀 있다)처럼
# 수신자가 낮은 role일 수 있는 유형은 프런트가 role 게이트를 따로 건다(NotificationBell.jsx의
# ROUTE_ROLES, registry/notifications.js의 reachableAdminTarget) — 이 서버 표 자체는
# "경로는 권한과 무관하다"(위 docstring)는 원칙대로 role을 안 따진다.


def destination_for(related_object_type: str | None, related_object_id: str | None) -> str | None:
    """딥링크 경로 또는 None(목적지가 없거나 id 가 없으면)."""
    template = RELATED_DESTINATIONS.get(related_object_type or "")
    if not template:
        return None
    if "{id}" in template:
        if not related_object_id:
            return None
        # id 는 서버가 만든 UUID 다. 그래도 경로를 깨뜨릴 문자는 통과시키지 않는다.
        if any(ch in related_object_id for ch in "/?#\\ "):
            return None
        return template.replace("{id}", related_object_id)
    return template
