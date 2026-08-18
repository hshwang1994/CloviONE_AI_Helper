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
  * **공용 조회 헬퍼의 본문에서** 게이트가 빠지면 못 잡는다 — 호출부는 그대로 보이기 때문이다.
    (직접 시험해 봤다: `_get_post_or_404` 안의 `org_id=` 를 지워도 통과했다.)
    이 경우는 테스트가 잡는다(`tests/security/test_board_scope.py`) — 두 그물이 겹치는 자리다.
  * 두 단계까지만 호출을 따라간다. 더 깊은 것은 호출 한 줄에 드러나는 관용
    (행위자를 넘기는 `*_or_404(db, id, me)`)으로 인정하거나 `EXEMPT` 에 이유를 적는다.

반대로 **실제로 잡는 것을 확인한 결함**: `POST /api/tickets/trash-bulk`(일괄만 범위 없음),
`app/jobs` 의 상세·재시도·취소(게이트를 되돌리면 세 줄을 뱉는다).
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

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
    # 이 저장소의 관용: **조회 함수에 행위자를 넘기면** 그 조회가 범위를 안다.
    #   `_get_post_or_404(db, post_id, me)`  ← 범위 있음
    #   `_get_post_or_404(db, post_id)`      ← 범위 없음(예전의 결함 상태가 정확히 이것이었다)
    # 게이트가 세 단계 아래(`… → get_post(org_id=) → visible_posts(org_id)`)에 있어도
    # 이 신호는 호출 한 줄에 드러난다. 인자 유무로 갈리므로 결함 상태를 통과시키지 않는다.
    re.compile(r"_or_404\([^)]*\b(me|user|actor|principal|viewer)\b"),
)

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
}

ROUTE_RE = re.compile(
    r'@router\.(get|post|patch|put|delete)\(\s*[\'"]([^\'"]*)[\'"]',
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
            yield m.group(1), m.group(2), fn.group(1)


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


def _guarded(
    body: str, pools: list[dict[str, str]], depth: int = 2, *, loose: bool = False
) -> bool:
    code = _code_only(body)
    if any(g in code for g in GATES) or any(p.search(code) for p in GATE_PATTERNS):
        return True
    if loose and any(sig in code for sig in LOOSE_SIGNALS):
        return True
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


def main() -> int:
    offenders: list[str] = []
    checked = skipped_modules = 0

    for router in sorted(ROOT.glob("app/*/router.py")):
        rel = router.relative_to(ROOT).as_posix()
        module_dir = router.parent
        src = router.read_text(encoding="utf-8")
        pools = [_bodies(src)]
        for sibling in ("service.py", "repository.py"):
            f = module_dir / sibling
            if f.exists():
                pools.append(_bodies(f.read_text(encoding="utf-8")))

        routes = list(_routes(src))
        # ① 이 모듈이 범위 축을 갖는가 — 목록(경로 파라미터 없는 라우트)이 판정을 지나는가.
        listy = [n for _, p, n in routes if not HAS_PARAM.search(p)]
        module_scoped = any(_guarded(pools[0].get(n, ""), pools, loose=True) for n in listy)
        if not module_scoped:
            skipped_modules += 1
            continue

        # ② 범위가 있는 모듈에서만, **id 를 받는** 경로를 본다.
        #    경로 파라미터가 있거나(단건) 본문으로 id 목록을 받거나(일괄).
        for verb, path, name in routes:
            body = pools[0].get(name, "")
            if not (HAS_PARAM.search(path) or BULK_HINT.search(body)):
                continue
            key = f"{rel}::{name}"
            checked += 1
            if key in EXEMPT:
                continue
            if not _guarded(body, pools):
                offenders.append(f"{key}  ({verb.upper()} {path})")

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
        f"SCOPE_GATES_OK (범위 있는 모듈에서 id 를 받는 경로 {checked}개 확인, "
        f"면제 {len(EXEMPT)}개, 범위 축 없는 모듈 {skipped_modules}개 건너뜀)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
