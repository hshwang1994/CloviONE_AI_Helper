"""id 경로에 범위 게이트가 걸려 있는지 확인한다 (§0-A 재발 방지).

## 왜 이 검사가 생겼는가

RBAC 작업 중 **네 번** 같은 실수를 했다: 목록 API 에는 범위를 걸었는데 **같은 모듈의
단건 조회·쓰기 경로에는 안 걸었다.**

  * 승인 — 큐 목록만 좁히고 `approve`/`reject` 는 그대로 → 범위 밖 **권한 부여를 실행**할 수 있었다
  * 잡 큐 — 목록만 좁히고 상세·재시도·취소는 그대로 → payload 열람 + n8n/Notion 쓰기 재실행
  * 게시판 — 목록만 좁히고 상세·댓글·첨부·쓰기는 그대로 → 조직 간 유출
  * 티켓 첨부 — 상세·댓글은 막았는데 첨부 원본만 열려 있었다

휴지통에서 *"단건만 막으면 소용없다"* 를 발견하고 고쳐 놓고도 다른 모듈에 적용하지 못했다.
**사람 기억에 맡기면 또 잊는다.**

## 규칙 (계획서 §0-A)

> 어떤 모듈이 **목록에 범위를 걸면**, 그 모듈의 **단건 조회·쓰기 경로도** 같은 판정을 지나야 한다.

그래서 검사는 두 단계다.

1. **모듈이 범위 축을 갖는가** — 경로 파라미터가 **없는** 라우트(= 목록·생성)에 범위 판정이
   보이면 그 모듈은 "범위가 있는 모듈" 이다. 러너·워크플로·스케줄·설정처럼 **포탈 전역 설정**
   모듈은 역할로만 막는 것이 옳고, 여기서 걸러진다(넓게 잡으면 소음이 되고, 소음이 나면
   아무도 안 본다 — 그게 검사를 죽이는 방법이다).
2. 범위가 있는 모듈에서만, **id 경로**가 판정을 지나는지 본다.

판정은 라우터 안에만 있지 않다 — 티켓은 `app/tickets/service.py` 의 `ensure_in_scope` 가 한다.
그래서 핸들러가 부르는 **같은 모듈의 헬퍼와 service/repository 함수까지 두 단계** 따라간다
(예: 라우터 `claim_ticket` → `service.claim_ticket` → `update_ticket` 의 `ensure_in_scope`).

## 한계 (일부러 적어 둔다)

정적 검사다. **증명이 아니라 "생각조차 안 한 곳" 을 잡는 그물**이다. 실제로 확인한 한계:

  * 게이트를 **부르지만 결과를 안 쓰는** 코드는 못 잡는다.
  * 두 단계까지만 호출을 따라간다. 더 깊은 것은 `EXEMPT` 에 이유를 적는다.
  * 행위자를 넘기는 `*_or_404` 헬퍼가 **다른 모듈에 살면** 그 본문을 못 본다. 같은 모듈에
    있으면 본문까지 따라간다(아래 참조).

반대로 **실제로 잡는 것을 확인한 결함**: `POST /api/tickets/trash-bulk`(일괄만 범위 없음),
`app/jobs` 의 상세·재시도·취소(게이트를 되돌리면 세 줄을 뱉는다).

## S1 에서 막은 사각 셋 (이 검사가 «안 보고 통과» 하던 자리)

1. **파일 이름이 `router.py` 가 아니면 통째로 안 봤다.** `app/*/router.py` 한 겹만 훑었다 —
   `app/admin/feature_flags.py` · `app/admin/rbac.py` · `app/auth/reset_router.py` ·
   `app/search/reindex_router.py` 가 검사 밖이었다. 이제 `app/**` 에서 **라우트를 선언하는
   모든 파일**을 찾아 모듈 디렉터리별로 묶는다.
2. **변수 이름이 `router` 가 아니면 안 봤다.** `@admin_router.get(...)` ·
   `@user_router.post(...)` · `@organizations_router...` · `@delegations_router...` ·
   `@personal_router...` 14건이 그랬고, `app/announcements/router.py` 는 **파일 전체가**
   0개 라우트로 읽혔다. 이제 `@<무엇이든>router.<verb>` 를 본다.
3. **공용 조회 헬퍼의 본문이 비어도 호출부 모양만으로 통과했다.** 위 「한계」에 «못 잡는다»
   고 적혀 있던 자리다(`_get_post_or_404` 안의 `org_id=` 를 지워도 통과). 이제 그 관용구는
   게이트가 아니라 **따라가야 할 호출**이다.

세 가지 다 「위반 0」으로 보였다. **검사가 위반을 못 찾은 것과 검사가 그 자리를 안 본 것은
다른 사실이다** — 그래서 OK 줄에 파일 수·모듈 수·경로 수를 함께 찍는다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 콘솔이 cp949 면 한글 문장부호(em dash 등)에서 죽는다 — 결과를 못 읽는 실패는 실패보다 나쁘다.
# 이 검사기만 이 preamble 이 없어서, GAP 줄을 찍는 순간 `UnicodeEncodeError` 로 전체
# `static_checks.sh` 가 빨개졌다(S1 에서 실측).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

# 범위/소유권 판정으로 인정하는 이름들.
#
# ⚠️ **권한 판정을 여기 넣으면 안 된다.** 한 번 그렇게 했다가 검사가 조용해졌다:
#   * `ensure_can_edit` — `MODERATOR_ROLES` 를 **무조건** 통과시키고 미할당 티켓은
#     누구나 통과시킨다. 다른 부서의 운영자가 그대로 지난다. 범위 판정이 아니다.
#   * `ensure_can_delete` / `ensure_can_delete_doc` — 작성자·운영자 판정이다. 같은 이유.
#   * `ensure_not_trashed` — 휴지통 여부만 본다. 범위와 무관하다.
# "누가 할 수 있는가"(권한)와 "무엇이 보이는가"(범위)는 다른 축이고, 둘을 섞으면
# **권한만 있고 범위는 없는 경로가 통과한다** — `POST /api/tickets/trash-bulk` 가 그랬다.
#
# 0060: `build_scope()` 하나가 `visibility_scope`/`management_scope` 둘로 갈라졌고
# `Principal.scope` 는 `.visibility`/`.management` 로 나뉘었다. 옛 이름만 두면 **이 검사가
# 조용해진다** — 실제로 게이트를 그대로 지나는 경로가 "게이트 없음" 으로 보고됐다.
GATES = (
    "ensure_in_scope", "get_scoped_", "visible_to", "scope_filter", "apply_user_scope",
    "visible_user_ids", "visibility_scope", "management_scope",
    "principal.visibility", "principal.management", "ensure_access",
    "ensure_can_manage", "ensure_member", "doc_in_scope", "any_assignee_visible",
    "get_owned_", "ensure_owner", "in_scope",
)

# 이름을 하나씩 등록하면 새 게이트가 생길 때마다 이 파일을 고쳐야 하고, 안 고치면 **오탐**이
# 나서 검사를 믿지 않게 된다(실제로 새 게이트 `ensure_comment_ticket_visible` 에서 한 번 겪었다).
# 그래서 이 저장소가 실제로 쓰는 작명 관용을 패턴으로 인정한다.
GATE_PATTERNS = (
    # `_?` — private 헬퍼(`_ensure_host`처럼 앞에 밑줄)도 인정한다. `\b`는 단어 경계라
    # 밑줄(단어 문자) 바로 뒤에서는 성립하지 않아 처음엔 `_ensure_*`를 전부 놓쳤다 — 실제로
    # `app/quotas/router.py::_ensure_target_in_scope`·`app/tickets/router.py::
    # _ensure_attachment_ticket_visible`도 이름에 scope/visible이 있는데 같은 이유로
    # 안 걸리고 있었다(2026-08-16 발견). "host"도 추가한다 — 게임방은 조직 범위가 아니라
    # **방장 소유권**이 게이트라 owner/member 동의어로는 안 걸렸다(`app/games/service.py::
    # _ensure_host`).
    re.compile(r"\b_?ensure_\w*(scope|visible|owner|member|host)\w*\s*\("),
    re.compile(r"\b_?require_(owner|member)\s*\("),
    # 채팅방은 멤버십 행을 직접 읽고 None/역할을 인라인으로 검사한다
    # (`repository.get_member(db, room.id, user.id)` → None 이면 403, owner 아니면 403).
    # 함수로 감싸지 않았을 뿐 판정은 있다.
    re.compile(r"\bget_member\s*\("),
    re.compile(r"\bget_\w*(scoped|in_scope|owned)\w*\s*\("),
    # `org_id` 를 **문자열로** 인정하면 너무 느슨하다 — `org_id=user.org_id` 처럼 값을 **넣는**
    # 코드까지 게이트로 세어 버린다. 실제로 그것 때문에 `app/documents` 가 '범위 있는 모듈'로
    # 분류됐는데 그 모듈의 목록은 전혀 안 좁히고 있었다(작업 중 발견). **비교**만 인정한다.
    re.compile(r"\.org_id\s*==|==\s*\w+\.org_id|org_id\s*!="),
)

# 이 저장소의 관용: **조회 함수에 행위자를 넘기면** 그 조회가 범위를 안다.
#   `_get_post_or_404(db, post_id, me)`  ← 범위 있음
#   `_get_post_or_404(db, post_id)`      ← 범위 없음(예전의 결함 상태가 정확히 이것이었다)
#
# 🔴 **이것만으로 게이트라고 인정하면 뚫린다.** 파일 상단 「한계」에 적혀 있던 그대로다 —
# `_get_post_or_404` **본문에서** `org_id=` 를 지워도 호출부 모양은 그대로라 통과했다(손으로
# 확인된 상태였다). 그래서 이제 이 관용구는 **게이트가 아니라 «따라가야 할 호출»** 로 다룬다:
# 호출된 헬퍼를 같은 모듈에서 찾을 수 있으면 **그 본문**이 실제로 게이트를 지나는지 본다.
# 못 찾으면(다른 모듈에 산다) 예전처럼 인정한다 — 그 한계는 아래 「한계」에 남는다.
ACTOR_OR_404_RE = re.compile(
    r"\b(\w*_or_404)\s*\([^)]*\b(?:me|user|actor|principal|viewer)\b")

# 범위를 안 거는 것이 **의도**인 경로. 반드시 이유를 적는다.
# 이유를 못 쓰겠으면 그건 의도가 아니라 결함이다.
# `serve_avatar` 가 여기 있었다. 이유는 "프로필 사진은 전 직원 대상이 의도다 — 이름·부서는
# 이미 디렉터리·게시판에 공개라 사진만 좁히면 이름 옆 사진이 뚫린 채로 보인다" 였는데,
# 디렉터리(`org_id` 로 좁힘)와 게시판이 조직 축을 갖게 되면서 **그 근거가 사실이 아니게 됐다**.
# 면제는 이유가 참일 때만 면제다 — 근거가 바뀌면 면제도 같이 없어져야 한다. 지금은 조직
# 판정을 지난다(`app/profiles/service.py::get_scoped_avatar_owner_or_404`, 범위 밖은 404).
EXEMPT: dict[str, str] = {
    # 전역 관리자 전용 경로(0060 진단 화면). `_require_global(principal)` 이 **관리 범위가
    # 전역이 아닌 사람을 전부 막는다** — 좁힐 범위가 남아 있지 않으므로 범위 게이트를 더
    # 걸 자리가 없다. 이 판정을 GATES 에 이름으로 넣지 않는 이유는 파일 상단 경고와 같다:
    # 권한 이름을 범위 게이트로 인정하기 시작하면 "권한만 있고 범위는 없는" 경로가 통과한다.
    "app/integrity/router.py::assign_membership":
        "전역 관리 범위만 통과한다(`_require_global`) — 좁힐 범위가 없다.",
    "app/integrity/router.py::assign_document_ownership":
        "전역 관리 범위만 통과한다(`_require_global`) — 좁힐 범위가 없다.",
    "app/profiles/router.py::revoke_one_session":
        "자기 세션만 다룬다 — 조회가 `user_id == me.id` 로 시작한다.",
    "app/profiles/router.py::delete_saved_view":
        "자기 저장된 뷰만 다룬다 — 소유자 판정이 곧 범위다.",
    "app/games/router.py::room_state":
        "비멤버 로비 미리보기는 설계다(`you.in_room` / `join(spectate=)`). 대화 이벤트만 "
        "가린다 — tests/security/test_game_room_chat_scope.py 가 그 결합을 고정한다.",
    # S1 이 이 검사의 눈을 넓히면서 처음 보인 경로. `@user_router` 라 예전에는 아예 안 봤다.
    "app/announcements/router.py::dismiss_announcement":
        "공지는 부서별로 좁혀 저장되지 않는다 — `all`/`admin` 둘 다 **포탈 전체**에 뜬다"
        "(`_ensure_may_touch_announcements` docstring, UB-01). 좁힐 범위가 없고, 닫기는 "
        "`(공지, 나)` 행 하나를 만드는 **자기 상태 변경**이다.",
}

# ── 알려진 미해결 gap ────────────────────────────────────────────────────────
#
# `EXEMPT` 와 **다른 것**이다. EXEMPT 는 「안 거는 것이 의도다」이고, 여기는 「결함인데 이
# Session 이 고칠 자리가 아니다」다. 둘을 한 통에 담으면 결함이 의도로 위장한다.
#
# 규칙 셋:
#   1. 반드시 **Owner Session** 과 원장 위치를 적는다. 주인 없는 항목은 영원히 남는다.
#   2. 출력에 `[GAP]` 로 **매번 크게 찍고 개수를 OK 줄에도 넣는다** — 조용한 면제가 아니다.
#   3. 여기 적힌 경로가 스캔에서 사라지면 **실패한다**(아래 staleness 검사). 고쳐졌거나
#      경로가 바뀌었으면 이 표를 함께 지워야 한다. 늙은 면제는 면제가 아니라 거짓말이다.
KNOWN_GAPS: dict[str, str] = {
    "app/approvals/router.py::revoke_delegation":
        "Owner **S5**(P-12/P-13) · 원장 docs/platform/BACKLOG.md. "
        "`/api/admin/approval-delegations` 표면 전체(`list`·`create`·`revoke`)가 "
        "`principal` 을 아예 안 받는다 — 같은 파일의 승인 큐는 "
        "`visible_user_ids(db, principal.management)` 로 좁히는데 이쪽만 전량이다. "
        "`CONSOLE_WRITE_ROLES = (admin, system_admin)` 이고 `admin` 은 **부서 범위일 수 "
        "있으므로**(`users.admin_scope`), 부서 admin 이 남의 부서 결재 대리를 만들고 "
        "취소할 수 있다. 공지(UB-01)·쿼터(`_ensure_may_touch_global`)에서 이미 두 번 "
        "고친 것과 같은 계열이다. **S1 은 제품 코드를 고치지 않는다** — 기록하고 넘긴다.",
}

# `@router.` 만 보면 **변수 이름이 다른 라우터가 통째로 사라진다.** 실제로
# `app/announcements/router.py` 는 `admin_router`/`user_router` 두 개만 써서 이 검사에
# 0개 라우트로 읽혔고, 그 사실이 「범위 축 없는 모듈」로 조용히 접혔다.
ROUTE_RE = re.compile(
    r'@(?P<router>\w*router)\.(?P<verb>get|post|patch|put|delete)\(\s*[\'"](?P<path>[^\'"]*)[\'"]',
)
DEF_RE = re.compile(r"^def (\w+)\(", re.M)
HAS_PARAM = re.compile(r"\{[a-zA-Z_]+\}")

# **일괄 경로**도 id 를 받는다 — 경로가 아니라 본문으로 받을 뿐이다.
#
# 이 검사의 첫 판은 `/{id}` 만 봐서 `POST /api/tickets/trash-bulk` 를 놓쳤다. 그건 목록·단건이
# 전부 `ensure_in_scope` 를 지나는데 **일괄만 안 지나던** 자리였고, 휴지통에서 똑같은 것을
# 이미 한 번 겪고도 반복한 자리다. 경로 모양이 아니라 **id 를 받는가**로 판단해야 한다.
BULK_HINT = re.compile(
    r"\b(payload|body)\.(ids|page_ids|user_ids)\b|\bids\s*:\s*list|_bulk\b"
)


def _bodies(src: str) -> dict[str, str]:
    out: dict[str, str] = {}
    marks = [(m.start(), m.group(1)) for m in DEF_RE.finditer(src)]
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(src)
        out[name] = src[pos:end]
    return out


def _routes(src: str):
    """(verb, path, handler_name) — 라우트 데코레이터 뒤 첫 def."""
    for m in ROUTE_RE.finditer(src):
        fn = DEF_RE.search(src[m.end():])
        if fn is not None:
            yield m.group("verb"), m.group("path"), fn.group(1)


DOCSTRING_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
COMMENT_RE = re.compile(r"#[^\n]*")


def _code_only(body: str) -> str:
    """주석과 docstring 을 뺀 실행 코드만.

    🔴 **이 검사가 스스로 뚫린 자리다.** `trash_tickets_bulk` 의 게이트를 떼고 돌렸는데
    검사가 통과했다 — docstring 에 "`ensure_in_scope` 를 지나는데" 라고 **적혀만** 있어서
    그 문자열이 매칭됐기 때문이다.

    이 저장소는 "왜" 를 길게 적는 것이 규칙이라 게이트 이름이 산문에 자주 나온다. 즉
    **설명만 하고 부르지 않는 코드**가 통과한다 — 검사가 막으려던 바로 그 상태다.
    """
    return COMMENT_RE.sub("", DOCSTRING_RE.sub("", body))


# 모듈 **분류**(①)에만 쓰는 느슨한 신호. 여기서 놓치면 그 모듈이 통째로 검사에서 빠지는데,
# 그건 이 검사가 낼 수 있는 가장 나쁜 결과다("조용히 안 본다"). 그래서 분류는 넓게 잡고,
# 실제 경로 판정(②)은 좁게 잡는다 — 두 단계의 오류 비용이 반대라 기준도 반대여야 한다.
#
# 실제로 한 번 겪었다: `org_id` 를 엄격하게 바꿨더니 게시판이 '범위 축 없는 모듈'로 분류돼
# 7개 경로가 통째로 검사에서 사라졌고, 결함을 재도입해도 검사가 조용했다.
LOOSE_SIGNALS = ("org_id", "scope", "visible", "principal")


def _lookup(name: str, pools: list[dict[str, str]]) -> str | None:
    for pool in pools:
        if name in pool:
            return pool[name]
    return None


def _guarded(
    body: str, pools: list[dict[str, str]], depth: int = 2, *, loose: bool = False
) -> bool:
    code = _code_only(body)
    if any(g in code for g in GATES) or any(p.search(code) for p in GATE_PATTERNS):
        return True
    if loose and any(sig in code for sig in LOOSE_SIGNALS):
        return True

    # 행위자를 넘기는 `*_or_404` 관용구 — **헬퍼 본문까지 따라간다.**
    for m in ACTOR_OR_404_RE.finditer(code):
        helper = _lookup(m.group(1), pools)
        if helper is None:
            return True  # 이 모듈에서 못 찾는다 = 다른 모듈 소유. 예전대로 인정한다(한계).
        if depth > 0 and _guarded(helper, pools, depth - 1, loose=loose):
            return True
        # 찾았는데 그 본문에 게이트가 없다 → 호출부 모양만 남은 상태다. 인정하지 않는다.

    if depth <= 0:
        return False
    for pool in pools:
        for name, helper in pool.items():
            if helper is body:
                continue
            if re.search(rf"\b{re.escape(name)}\s*\(", code) and _guarded(
                helper, pools, depth - 1, loose=loose
            ):
                return True
    return False


def scan_module(
    route_srcs: dict[str, str],
    helper_srcs: list[str],
    *,
    gaps: list[str] | None = None,
    seen: set[str] | None = None,
) -> tuple[list[str], int, bool]:
    """한 모듈을 본다 — `(offenders, checked, module_scoped)`.

    `route_srcs` 는 이 모듈에서 **라우트를 선언하는 모든 파일**이다(`router.py` 하나가 아니다).
    `gaps` 를 주면 `KNOWN_GAPS` 에 있는 것은 그쪽으로 빠진다(실패시키지 않되 크게 찍는다).
    `seen` 에는 실제로 **판정한** 경로 키가 쌓인다 — 늙은 면제를 잡는 데 쓴다.
    """
    gaps = [] if gaps is None else gaps
    seen = set() if seen is None else seen
    per_file = {rel: _bodies(src) for rel, src in route_srcs.items()}
    pools: list[dict[str, str]] = list(per_file.values()) + [_bodies(s) for s in helper_srcs]

    routes: list[tuple[str, str, str, str]] = []
    for rel, src in route_srcs.items():
        for verb, path, name in _routes(src):
            routes.append((verb, path, name, rel))

    # ① 이 모듈이 범위 축을 갖는가 — 목록(경로 파라미터 없는 라우트)이 판정을 지나는가.
    listy = [(n, rel) for _, p, n, rel in routes if not HAS_PARAM.search(p)]
    module_scoped = any(_guarded(per_file[rel].get(n, ""), pools, loose=True)
                        for n, rel in listy)
    if not module_scoped:
        return [], 0, False

    # ② 범위가 있는 모듈에서만, **id 를 받는** 경로를 본다.
    #    경로 파라미터가 있거나(단건) 본문으로 id 목록을 받거나(일괄).
    offenders: list[str] = []
    checked = 0
    for verb, path, name, rel in routes:
        body = per_file[rel].get(name, "")
        if not (HAS_PARAM.search(path) or BULK_HINT.search(body)):
            continue
        key = f"{rel}::{name}"
        checked += 1
        seen.add(key)
        if key in EXEMPT:
            continue
        if not _guarded(body, pools):
            (gaps if key in KNOWN_GAPS else offenders).append(f"{key}  ({verb.upper()} {path})")
    return offenders, checked, True


# ── 검사기 자신을 먼저 검사한다 ────────────────────────────────────────────────
# 이 검사는 **두 방향으로** 틀릴 수 있고 둘 다 겪었다: 넓게 잡아 위양성을 내면 사람이
# 검사를 끄고(`org_id` 문자열 인정), 좁게 잡으면 모듈이 통째로 분류에서 빠진다(게시판 7경로).
# 그래서 사례도 양방향으로 둔다.
_LISTY_SCOPED = '''
@router.get("/api/things")
def list_things(db, me):
    return repository.visible_things(db, org_id=me.org_id)
'''
_GOOD_ID = _LISTY_SCOPED + '''
@router.get("/api/things/{thing_id}")
def get_thing(db, thing_id, me):
    ensure_in_scope(db, thing_id, me)
    return repository.get(db, thing_id)
'''
_BAD_ID = _LISTY_SCOPED + '''
@router.get("/api/things/{thing_id}")
def get_thing(db, thing_id):
    return repository.get(db, thing_id)
'''
_DOCSTRING_ONLY = _LISTY_SCOPED + '''
@router.post("/api/things/trash-bulk")
def trash_bulk(db, payload, me):
    """ensure_in_scope 를 지나는데, 실제로는 부르지 않는다."""
    ids: list = payload.ids
    return repository.trash(db, ids)
'''
_OR404_HELPER_GUARDED = _LISTY_SCOPED + '''
@router.get("/api/things/{thing_id}")
def get_thing(db, thing_id, me):
    return _get_thing_or_404(db, thing_id, me)


def _get_thing_or_404(db, thing_id, me):
    row = repository.get(db, thing_id)
    if row.org_id != me.org_id:
        raise HTTPException(404)
    return row
'''
_OR404_HELPER_BLIND = _LISTY_SCOPED + '''
@router.get("/api/things/{thing_id}")
def get_thing(db, thing_id, me):
    return _get_thing_or_404(db, thing_id, me)


def _get_thing_or_404(db, thing_id, me):
    return repository.get(db, thing_id)
'''
_NOT_SCOPED_MODULE = '''
@router.get("/api/flags")
def list_flags(db, me):
    return repository.all_flags(db)


@router.patch("/api/flags/{flag_id}")
def set_flag(db, flag_id, me):
    return repository.set_flag(db, flag_id)
'''
_ALIASED_ROUTER = '''
@user_router.get("/api/notices")
def list_notices(db, me):
    return repository.visible_notices(db, org_id=me.org_id)


@admin_router.delete("/api/notices/{notice_id}")
def delete_notice(db, notice_id):
    return repository.delete(db, notice_id)
'''

SELF_TEST_CASES = [
    # (이름, 라우트 소스, 헬퍼 소스, 걸려야 하는가, 무엇을 지키는 사례인가)
    ("게이트가 있는 id 경로는 안 걸린다", _GOOD_ID, [], False,
     "위양성이면 사람이 이 검사를 끈다"),
    ("게이트가 없는 id 경로는 걸린다", _BAD_ID, [], True,
     "이 검사의 존재 이유 — 목록만 좁히고 단건은 열어 둔 상태"),
    ("docstring 에만 적힌 게이트는 안 쳐준다", _DOCSTRING_ONLY, [], True,
     "`trash-bulk` 가 실제로 이 모양으로 뚫렸다"),
    ("행위자를 넘기는 `_or_404` 헬퍼가 실제로 막으면 안 걸린다",
     _OR404_HELPER_GUARDED, [], False, "이 저장소의 정상 관용구"),
    ("같은 헬퍼의 **본문**이 비면 걸린다", _OR404_HELPER_BLIND, [], True,
     "파일 상단 「한계」에 «못 잡는다» 고 적혀 있던 자리 — 이제 잡는다"),
    ("범위 축이 없는 모듈은 통째로 건너뛴다", _NOT_SCOPED_MODULE, [], False,
     "전역 설정 모듈까지 잡으면 소음이 되고, 소음이 나면 아무도 안 본다"),
    ("`router` 가 아닌 이름의 라우터도 본다", _ALIASED_ROUTER, [], True,
     "`app/announcements/router.py` 가 `admin_router`/`user_router` 라 0개로 읽혔다"),
]


def self_test() -> int:
    bad = []
    for name, src, helpers, should_flag, why in SELF_TEST_CASES:
        offenders, _checked, _scoped = scan_module({"<self-test>.py": src}, helpers)
        if bool(offenders) != should_flag:
            bad.append("%s: 기대 %s / 실제 %s  (%s)"
                       % (name, "검출" if should_flag else "통과",
                          "검출" if offenders else "통과", why))
    if bad:
        print("[FAIL] 검사기 자체가 고장 났다 — 초록이 아무것도 증명하지 못한다:")
        for line in bad:
            print(f"  - {line}")
        return 1
    print(f"[OK ] SCOPE_GATES_SELF_TEST_OK (사례 {len(SELF_TEST_CASES)}개, 검출·위양성 양방향)")
    return 0


def route_files() -> dict[Path, dict[str, str]]:
    """라우트를 선언하는 **모든** 파일을 모듈 디렉터리별로 모은다.

    예전에는 `app/*/router.py` 한 겹만 봤다. 그래서 `app/admin/feature_flags.py` ·
    `app/admin/rbac.py` · `app/auth/reset_router.py` · `app/search/reindex_router.py` 가
    **통째로 검사 밖**이었다 — 파일 이름이 `router.py` 가 아니라는 이유 하나로.
    """
    out: dict[Path, dict[str, str]] = {}
    for path in sorted((ROOT / "app").rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        if not ROUTE_RE.search(src):
            continue
        out.setdefault(path.parent, {})[path.relative_to(ROOT).as_posix()] = src
    return out


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 1

    offenders: list[str] = []
    gaps: list[str] = []
    seen: set[str] = set()
    checked = skipped_modules = 0
    modules = route_files()
    files = sum(len(v) for v in modules.values())

    for module_dir, route_srcs in sorted(modules.items()):
        helpers = [(module_dir / s).read_text(encoding="utf-8")
                   for s in ("service.py", "repository.py")
                   if (module_dir / s).exists()]
        found, n, scoped = scan_module(route_srcs, helpers, gaps=gaps, seen=seen)
        offenders += found
        checked += n
        if not scoped:
            skipped_modules += 1

    # 늙은 면제를 잡는다 — 여기 적힌 경로가 스캔에 안 나타나면 표가 사실과 어긋난 것이다.
    stale = sorted(k for k in (set(EXEMPT) | set(KNOWN_GAPS)) if k not in seen)
    if stale:
        print("면제/GAP 표가 늙었다 — 이 경로들은 이제 검사 대상이 아니다:")
        for k in stale:
            print("  -", k)
        print("\n고쳐졌거나 경로가 바뀐 것이다. EXEMPT/KNOWN_GAPS 에서 함께 지워라 —\n"
              "  늙은 면제는 면제가 아니라 거짓말이다.")
        return 1

    if gaps:
        print(f"[GAP] 알려진 미해결 {len(gaps)}건 — 이 Session 이 고칠 자리가 아니다:")
        for g in gaps:
            print("  -", g)
            print("     ", KNOWN_GAPS[g.split("  (")[0]])

    if offenders:
        print("범위 있는 모듈인데 id 경로에 게이트가 안 보인다:")
        for o in offenders:
            print("  -", o)
        print(
            "\n각각 둘 중 하나를 해라:\n"
            "  1) 그 모듈의 목록이 쓰는 것과 **같은 판정**을 지나게 한다(범위 밖은 404).\n"
            "  2) 막지 않는 것이 의도라면 이 파일의 EXEMPT 에 **왜 그런지** 적는다.\n"
            "     이유를 못 쓰겠으면 그건 의도가 아니라 결함이다."
        )
        return 1

    print(
        f"SCOPE_GATES_OK (라우트 선언 파일 {files}개 · 모듈 {len(modules)}개에서 "
        f"id 를 받는 경로 {checked}개 확인, 면제 {len(EXEMPT)}개, "
        f"**미해결 GAP {len(gaps)}건**, 범위 축 없는 모듈 {skipped_modules}개 건너뜀)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
