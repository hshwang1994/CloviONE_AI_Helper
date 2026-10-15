"""AI 도우미 진실 하네스 (A10, D-570) — 실데이터에서 도우미가 말한 **수 · 제목 · 경로**가 화면 API 와 같은가를 잰다.

질문마다 (a) 같은 사용자로 화면 API 를 불러 진실을 구하고 (b) 새 대화에서 도우미에게 묻고 (c) 쓴 도구(`structured.tools`),
모드(`mode == tools`), 오류 여부를 보고 (d) 답 글과 출처(`structured.sources`)를 진실과 맞춘다. 황금 질문은 열여덟이다(`QUESTIONS`).
랩 고유 값(프로젝트 코드 · 문구 · 남의 부서 문서 제목 · 이름이 겹치는 프로젝트)은 저장소에 적지 않고 인자나 환경 변수로 받는다 —
그 값이 없으면 그 질문은 SKIP 이다.

## 지키는 것

- 비밀은 명령행에 받지 않는다. 계정은 환경 변수 `AI_TRUTH_EMAIL` · `AI_TRUTH_PASSWORD` 이고, `--env-file <경로>` 를 주면 그 파일에서
  **이 두 키와 선택 키 둘**(`AI_TRUTH_OTHER_TITLE` · `AI_TRUTH_AMBIGUOUS_PROJECT`)만 읽는다. 값은 어디에도 찍지 않는다.
- 아무것도 고치지 않는다. 질문마다 만든 대화는 끝에 지운다(`--keep` 이면 남긴다). 사용자의 프로필 · 설정 · 기존 자료는 건드리지 않는다.
  예외는 `--with-index-probe` 하나다 — 「[AI검증] 색인 반영 확인 <시각>」 문서 하나를 조직 공통 공간에 만들고, 끝에 보관 · 영구 삭제로 걷는다.
- 결과 파일의 글은 이메일을 가리고(`a****b@도메인`), 답은 앞 400자만 싣는다. 토큰 · 비밀번호는 싣지 않는다.
- TLS 는 검증한다(`--cacert` → `UI_QA_TLS_CA` → `dist/ops/<호스트>.crt` → 시스템 기준점). `--insecure` 는 검증을 끄고 결과에 적는다.

## 쓰는 법

    python -m scripts.ui_qa.ai_truth_e2e --env-file dist/ops/qa.env --cacert dist/ops/<호스트>.crt --label lab-a10 \\
        --project-code <코드> --phrase "<문구>" --ambiguous-project "<겹치는 이름>" [--with-index-probe]
    … --only q01 q08      # 고른 질문만
    … --keep              # 만든 대화를 남긴다

결과: `dist/ui-qa/ai-truth-e2e/<label>.json` · `<label>.md`. 요약 줄은 `AI_TRUTH_E2E OK|FAILED pass=… fail=… skip=…` 이고,
FAIL 이 하나라도 있으면 종료 코드 1, 로그인 · 설정 오류는 2 다.

## 진실을 구하는 자리(코드에서 확인한 것)

- 내 문서: `GET /api/knowledge/documents?mine=true` — `created_by == 나` 만이다(`app/knowledge/router.py::list_documents`).
- 내 티켓: `GET /api/tickets/mine` 의 `total` 은 완료 · 취소를 **포함**한다(라우터가 `active_only` 없이 `build_filters` 를 부른다).
  도우미의 `my_work` 는 완료 · 취소를 빼므로 쪽을 넘겨 가며 상태가 완료 · 취소가 아닌 것을 센다(상태가 비면 미완료다).
- 내 프로젝트: `GET /api/projects?mine=true`(구성원이거나 담당). 안 읽은 알림: `GET /api/notifications/unread-count` 의 `unread`.
- 회차 회의: `GET /api/work/sprints`(기본 팀) → `GET /api/work/sprints/{id}/meeting` 의 `decisions`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_qa.ai_lab_common import (  # noqa: E402 - 저장소 뿌리를 path 에 넣은 뒤에 읽는다
    LoginError,
    await_reply,
    create_conversation,
    delete_conversation,
    json_of,
    log,
    login,
    make_client,
    mask_emails,
    post_question,
    read_env_file,
    resolve_verify,
    utf8_console,
)
from scripts.ui_qa.capture import DEFAULT_BASE_URL as DEFAULT_BASE  # noqa: E402 - 대상 호스트는 한 곳이 정한다

OUT_DIR = ROOT / "dist" / "ui-qa" / "ai-truth-e2e"

ENV_EMAIL = "AI_TRUTH_EMAIL"
ENV_PASSWORD = "AI_TRUTH_PASSWORD"
ENV_OTHER_TITLE = "AI_TRUTH_OTHER_TITLE"
ENV_AMBIGUOUS = "AI_TRUTH_AMBIGUOUS_PROJECT"
ENV_KEYS = (ENV_EMAIL, ENV_PASSWORD, ENV_OTHER_TITLE, ENV_AMBIGUOUS)

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
MODE_TOOLS = "tools"
NOTICE_NO_RESULTS = "no_results"
#: 끝난 상태(`app/work/workflow.py`). 이 둘이 아니면 미완료다.
TERMINAL_STATUSES = frozenset({"완료", "취소"})
#: 결과 파일에 싣는 답의 길이.
EXCERPT_CHARS = 400
#: 색인 반영을 기다리는 상한(초)과 다시 묻는 간격.
INDEX_PROBE_SECONDS = 60.0
INDEX_PROBE_INTERVAL = 3.0
#: 쪽을 넘겨 셀 때의 쪽 크기와 상한(`app/core/pagination.py::MAX_PAGE_SIZE`).
PAGE_SIZE = 100
MAX_PAGES = 30


# ── 순수 판정 (tests/unit/test_ai_truth_harness.py) ─────────────────────────────


def norm(text) -> str:
    """대조용 꼴 — NFKC · 소문자 · 연속 공백 한 칸."""
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return " ".join(value.split())


def number_in(text: str, n: int) -> bool:
    """글 안에 수 `n` 이 **그 수로** 있는가. 「1,234」 도 1234 로 받고, 「12345」 · 「1,234」 의 234 · 「12.5」 의 12 는 아니다."""
    forms = {str(int(n))}
    if abs(int(n)) >= 1000:
        forms.add(f"{int(n):,}")
    for form in forms:
        if re.search(r"(?<![\d.,])" + re.escape(form) + r"(?![\d]|[.,]\d)", text or ""):
            return True
    return False


def tools_satisfied(called, alternatives) -> bool:
    """대안 묶음 중 하나라도 실제로 부른 도구의 부분집합이면 참이다. 대안이 없으면 따지지 않는다."""
    names = set(called or ())
    alts = [tuple(a) for a in (alternatives or ()) if a]
    if not alts:
        return True
    return any(set(alt) <= names for alt in alts)


def titles_mentioned(answer: str, sources, titles) -> list[str]:
    """진실 쪽 제목 중 답 글이나 출처 제목에 나온 것(두 글자 이상만)."""
    body = norm(answer)
    source_titles = {norm(s.get("title")) for s in (sources or []) if isinstance(s, dict)}
    out: list[str] = []
    for title in titles or ():
        key = norm(title)
        if len(key) < 2 or title in out:
            continue
        if key in body or key in source_titles:
            out.append(title)
    return out


def route_id(route: str | None, prefix: str) -> str | None:
    """`/knowledge/<id>?block=…` → `<id>`. 접두가 다르면 None."""
    if not isinstance(route, str) or not route.startswith(prefix):
        return None
    rest = route[len(prefix):]
    for stop in ("?", "#", "/"):
        rest = rest.split(stop, 1)[0]
    return rest or None


def source_ids(sources, prefix: str = "/knowledge/") -> set[str]:
    """출처에서 그 접두의 id 들."""
    out: set[str] = set()
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        found = route_id(s.get("route"), prefix)
        if found:
            out.add(found)
    return out


def has_route(sources, prefix: str) -> bool:
    return any(isinstance(s, dict) and isinstance(s.get("route"), str) and s["route"].startswith(prefix)
               for s in sources or [])


def keys_mentioned(answer: str, keys) -> list[str]:
    """티켓 키(`ABCDEF-12`) 중 답 글에 그 모양 그대로(앞뒤가 다른 글자 · 숫자가 아닌 자리) 나온 것."""
    out: list[str] = []
    for key in keys or ():
        if not key or key in out:
            continue
        if re.search(r"(?<![A-Za-z0-9-])" + re.escape(str(key)) + r"(?![A-Za-z0-9])", answer or "", re.IGNORECASE):
            out.append(key)
    return out


def asks_which(answer: str) -> bool:
    """어느 것인지 되묻는가(「어느 프로젝트」 · 「어떤 것」)."""
    return bool(re.search(r"(어느|어떤)\s*(프로젝트|것|쪽)", answer or ""))


def searched_phrase(answer: str) -> bool:
    """무엇을 찾아봤는지 말하는가(「찾아본」 · 「찾아봤」 · 「검색해 봤」)."""
    return bool(re.search(r"찾아\s?(본|봤|보았|보니)|검색(해\s?(본|봤|보았)|했)", answer or ""))


def not_found_phrase(answer: str) -> bool:
    """찾지 못했다 · 볼 수 없다는 말이 있는가."""
    return bool(re.search(r"찾지\s?못|찾을\s?수\s?없|없습니다|없어요|없네요|볼\s?수\s?없|권한", answer or ""))


def says_none(answer: str) -> bool:
    """「없습니다」 갈래(수가 0 일 때 받아 준다)."""
    return bool(re.search(r"없|0\s*(건|개|명)", answer or ""))


def count_not_done(items) -> int:
    """완료 · 취소가 아닌 티켓 수(상태가 비면 미완료다)."""
    return sum(1 for t in items or () if isinstance(t, dict) and (t.get("status") or "") not in TERMINAL_STATUSES)


def percent_or_count(answer: str) -> bool:
    """진행률(「42%」)이나 끝낸 수(「완료 12건」 · 「12건 완료」)를 말하는가."""
    text = answer or ""
    return bool(re.search(r"\d+(\.\d+)?\s*%|퍼센트", text)
                or re.search(r"완료[^\n]{0,12}?\d+|\d+\s*(건|개)[^\n]{0,8}?(완료|끝)", text))


def parse_only(values) -> set[str] | None:
    """`--only q01 8 q15` → {"q01", "q08", "q15"}. 비면 None(전부)."""
    if not values:
        return None
    out: set[str] = set()
    for raw in values:
        for part in str(raw).replace(",", " ").split():
            digits = part.lower().lstrip("q")
            if digits.isdigit():
                out.add(f"q{int(digits):02d}")
            elif part:
                out.add(part.lower())
    return out


# ── 진실 API ─────────────────────────────────────────────────────────────────


class TruthError(RuntimeError):
    """진실을 구하는 화면 API 가 200 이 아니다 — 그 질문은 판정할 수 없어 실패로 적는다."""

    def __init__(self, path: str, status: int) -> None:
        super().__init__(f"진실 API {path} 가 상태 {status} 를 돌려줬습니다.")
        self.path = path
        self.status = status


class Api:
    """같은 사용자의 세션으로 화면 API 를 읽는다."""

    def __init__(self, client: httpx.Client, headers: dict) -> None:
        self.client = client
        self.headers = headers

    def get(self, path: str, **params) -> tuple[int, object]:
        clean = {k: v for k, v in params.items() if v is not None}
        r = self.client.get(path, params=clean, headers=self.headers)
        return r.status_code, json_of(r)

    def get_ok(self, path: str, **params) -> dict:
        status, body = self.get(path, **params)
        if status != 200 or not isinstance(body, dict):
            raise TruthError(path, status)
        return body

    def pages(self, path: str, **params) -> tuple[list[dict], int, bool]:
        """`page`/`page_size` 목록을 끝까지. (항목, 서버 total, 상한에 걸려 덜 읽었는가)."""
        items: list[dict] = []
        total = 0
        for page in range(1, MAX_PAGES + 1):
            body = self.get_ok(path, page=page, page_size=PAGE_SIZE, **params)
            chunk = body.get("items")
            if chunk is None:
                chunk = body.get("tickets")
            chunk = [c for c in (chunk or []) if isinstance(c, dict)]
            total = int(body.get("total") or 0)
            items.extend(chunk)
            if len(chunk) < PAGE_SIZE or len(items) >= total:
                return items, total, False
        return items, total, len(items) < total


@dataclass(frozen=True)
class Options:
    phrase: str | None = None
    project_code: str | None = None
    ambiguous: str | None = None
    other_title: str | None = None

    def values(self) -> dict:
        return {"phrase": self.phrase or "", "project_code": self.project_code or "",
                "ambiguous": self.ambiguous or "", "other_title": self.other_title or ""}


def truth_my_documents(api: Api, opts: Options) -> dict:
    body = api.get_ok("/api/knowledge/documents", mine="true", limit=50)
    items = body.get("items") or []
    return {"total": int(body.get("total") or 0), "titles": [i.get("title") for i in items if i.get("title")]}


def _doc_union(api: Api, words) -> dict:
    ids: dict[str, str] = {}
    for word in words:
        body = api.get_ok("/api/knowledge/documents", q=word, limit=50)
        for item in body.get("items") or []:
            if item.get("id"):
                ids[item["id"]] = item.get("title") or ""
    return {"words": list(words), "ids": sorted(ids), "titles": [ids[i] for i in sorted(ids)]}


def truth_vmware(api: Api, opts: Options) -> dict:
    return _doc_union(api, ("vmware", "네트워크", "nsx"))


def truth_phrase(api: Api, opts: Options) -> dict:
    return _doc_union(api, (opts.phrase,))


def truth_ambiguous(api: Api, opts: Options) -> dict:
    items, total, _partial = api.pages("/api/projects", q=opts.ambiguous)
    return {"total": total, "projects": [{"code": p.get("code"), "name": p.get("name")} for p in items]}


def _project_by_code(api: Api, code: str) -> dict | None:
    items, _total, _partial = api.pages("/api/projects", q=code)
    exact = [p for p in items if (p.get("code") or "").lower() == (code or "").lower()]
    return exact[0] if exact else None


def truth_project(api: Api, opts: Options) -> dict:
    project = _project_by_code(api, opts.project_code)
    if project is None:
        return {"skip": f"코드 {opts.project_code} 인 프로젝트가 이 사용자에게 보이지 않아 건너뜁니다."}
    return {"id": project.get("id"), "code": project.get("code"), "name": project.get("name"),
            "progress_pct": project.get("progress_pct")}


def truth_project_with_counts(api: Api, opts: Options) -> dict:
    found = truth_project(api, opts)
    if found.get("skip"):
        return found
    docs = api.get_ok("/api/knowledge/documents", project_id=found["id"], limit=1)
    team = api.get_ok("/api/tickets/team", project_id=found["id"], active="true", page=1, page_size=1)
    found["documents_total"] = int(docs.get("total") or 0)
    found["active_tickets_total"] = int(team.get("total") or 0)
    return found


def truth_my_projects(api: Api, opts: Options) -> dict:
    items, total, _partial = api.pages("/api/projects", mine="true")
    return {"total": total, "names": [p.get("name") for p in items if p.get("name")],
            "codes": [p.get("code") for p in items if p.get("code")]}


def _my_tickets(api: Api, *, due: str | None = None) -> dict:
    items, total_all, partial = api.pages("/api/tickets/mine", due=due)
    open_items = [t for t in items if (t.get("status") or "") not in TERMINAL_STATUSES]
    return {"total_all": total_all, "not_done": len(open_items), "partial": partial,
            "keys": [t.get("key") for t in open_items if t.get("key")]}


def truth_open_tickets(api: Api, opts: Options) -> dict:
    return _my_tickets(api)


def truth_due_this_week(api: Api, opts: Options) -> dict:
    return _my_tickets(api, due="this_week")


def truth_unread(api: Api, opts: Options) -> dict:
    body = api.get_ok("/api/notifications/unread-count")
    return {"unread": int(body.get("unread") or 0)}


def truth_sprint(api: Api, opts: Options) -> dict:
    body = api.get_ok("/api/work/sprints")
    sprints = [s for s in body.get("sprints") or [] if isinstance(s, dict)]
    if not sprints:
        return {"sprints": 0}
    picked = next((s for s in sprints if s.get("active")), None) or sprints[0]
    meeting = api.get_ok(f"/api/work/sprints/{picked['id']}/meeting")
    decisions = [d for d in meeting.get("decisions") or [] if isinstance(d, dict)]
    fragments = []
    for d in decisions:
        text = " ".join(str(d.get("body") or "").split())
        if len(text) >= 4:
            fragments.append(text[:12])
    return {"sprints": len(sprints), "name": picked.get("name"), "id": picked.get("id"),
            "decisions": len(decisions), "fragments": fragments}


def truth_other_title(api: Api, opts: Options) -> dict:
    body = api.get_ok("/api/knowledge/documents", q=opts.other_title, limit=50)
    visible = any(norm(i.get("title")) == norm(opts.other_title) for i in body.get("items") or [])
    if visible:
        return {"skip": "이 사용자가 볼 수 있는 제목이라 권한 확인이 되지 않아 건너뜁니다. 다른 제목을 주세요."}
    return {"visible_to_persona": False}


# ── 답 판정 ───────────────────────────────────────────────────────────────────


@dataclass
class Answer:
    text: str
    structured: dict

    @property
    def tools(self) -> list[dict]:
        return [t for t in (self.structured.get("tools") or []) if isinstance(t, dict)]

    @property
    def tool_names(self) -> list[str]:
        return [str(t.get("name")) for t in self.tools if t.get("name")]

    @property
    def sources(self) -> list[dict]:
        return [s for s in (self.structured.get("sources") or []) if isinstance(s, dict)]

    @property
    def mode(self):
        return self.structured.get("mode")

    @property
    def notice(self):
        return self.structured.get("notice")


def check_q01(a: Answer, truth: dict) -> list[str]:
    need = min(3, int(truth.get("total") or 0))
    found = titles_mentioned(a.text, a.sources, truth.get("titles"))
    if len(found) < need:
        return [f"내 문서 첫 쪽 제목이 {need}개 이상 보여야 하는데 {len(found)}개만 보였습니다."]
    return []


def check_q02(a: Answer, truth: dict) -> list[str]:
    total = int(truth.get("total") or 0)
    if total == 0:
        return [] if says_none(a.text) or number_in(a.text, 0) else ["내 문서가 0건인데 답이 그 사실을 말하지 않았습니다."]
    return [] if number_in(a.text, total) else [f"내 문서 수 {total}을 답에서 찾지 못했습니다."]


def _check_overlap(a: Answer, truth: dict) -> list[str]:
    ids = set(truth.get("ids") or ())
    if not ids:
        if a.notice != NOTICE_NO_RESULTS:
            return ["화면 검색에 맞는 문서가 없는데 도우미가 「찾지 못함」으로 끝내지 않았습니다."]
        return []
    hit = source_ids(a.sources) & ids
    mentioned = titles_mentioned(a.text, a.sources, truth.get("titles"))
    if not hit and not mentioned:
        return ["화면 검색이 찾은 문서와 겹치는 출처나 제목이 하나도 없습니다."]
    return []


def check_q05(a: Answer, truth: dict) -> list[str]:
    projects = truth.get("projects") or []
    if len(projects) >= 2:
        names = {norm(p.get("name")) for p in projects if p.get("name")}
        codes = {norm(p.get("code")) for p in projects if p.get("code")}
        body = norm(a.text)
        mentioned = {p for p in names | codes if p and p in body}
        if len(mentioned) >= 2 or asks_which(a.text):
            return []
        if re.search(r"찾지\s?못|찾을\s?수\s?없|없는\s?프로젝트", a.text or ""):
            return ["이름이 여럿에 걸리는 프로젝트를 「찾지 못함」으로 답했습니다."]
        return ["이름이 같은 프로젝트 후보를 둘 이상 말하거나 어느 것인지 되묻지 않았습니다."]
    if len(projects) == 1:
        if not tools_satisfied(a.tool_names, (("project_activity",), ("get_project_summary",))):
            return ["프로젝트가 하나뿐인데 진행 현황 도구를 쓰지 않았습니다."]
        return []
    return [] if not_found_phrase(a.text) else ["화면에 맞는 프로젝트가 없는데 답이 그 사실을 말하지 않았습니다."]


def check_q06(a: Answer, truth: dict) -> list[str]:
    failures = []
    body = norm(a.text)
    if not any(norm(v) and norm(v) in body for v in (truth.get("name"), truth.get("code"))):
        failures.append("답에 프로젝트 이름이나 코드가 없습니다.")
    if not percent_or_count(a.text):
        failures.append("답에 진행률이나 끝낸 수가 없습니다.")
    return failures


def check_q07(a: Answer, truth: dict) -> list[str]:
    if int(truth.get("total") or 0) == 0:
        if not any(t.get("ok") for t in a.tools):
            return ["내 프로젝트가 없는데 도구가 하나도 성공하지 않았습니다."]
        return [] if says_none(a.text) else ["내 프로젝트가 없는데 답이 그 사실을 말하지 않았습니다."]
    body = norm(a.text)
    if any(norm(v) and norm(v) in body for v in (truth.get("names") or []) + (truth.get("codes") or [])):
        return []
    return ["내 프로젝트 이름이나 코드가 답에 하나도 없습니다."]


def _check_open_tickets(a: Answer, truth: dict, *, need_keys: bool) -> list[str]:
    n = int(truth.get("not_done") or 0)
    if n == 0:
        return [] if says_none(a.text) or number_in(a.text, 0) else ["미완료 티켓이 0건인데 답이 그 사실을 말하지 않았습니다."]
    failures = []
    if not number_in(a.text, n):
        failures.append(f"미완료 티켓 수 {n}을 답에서 찾지 못했습니다.")
    if need_keys:
        want = min(2, n)
        got = keys_mentioned(a.text, truth.get("keys"))
        if len(got) < want:
            failures.append(f"티켓 키가 {want}개 이상 보여야 하는데 {len(got)}개만 보였습니다.")
    if not has_route(a.sources, "/tickets/"):
        failures.append("출처에 티켓이 없습니다.")
    return failures


def check_q08(a: Answer, truth: dict) -> list[str]:
    return _check_open_tickets(a, truth, need_keys=True)


def check_q09(a: Answer, truth: dict) -> list[str]:
    return _check_open_tickets(a, truth, need_keys=False)


def check_q10(a: Answer, truth: dict) -> list[str]:
    if int(truth.get("total") or 0) > 0 and not has_route(a.sources, "/projects/"):
        return ["참여한 프로젝트가 있는데 출처에 프로젝트가 없습니다."]
    return []


def check_q11(a: Answer, truth: dict) -> list[str]:
    failures = []
    if int(truth.get("documents_total") or 0) > 0 and not has_route(a.sources, "/knowledge/"):
        failures.append("프로젝트 문서가 있는데 출처에 문서가 없습니다.")
    if int(truth.get("active_tickets_total") or 0) > 0 and not has_route(a.sources, "/tickets/"):
        failures.append("진행 중인 티켓이 있는데 출처에 티켓이 없습니다.")
    return failures


def check_q13(a: Answer, truth: dict) -> list[str]:
    n = int(truth.get("unread") or 0)
    if n == 0:
        return [] if says_none(a.text) or number_in(a.text, 0) else ["안 읽은 알림이 0건인데 답이 그 사실을 말하지 않았습니다."]
    return [] if number_in(a.text, n) else [f"안 읽은 알림 수 {n}을 답에서 찾지 못했습니다."]


def check_q14(a: Answer, truth: dict) -> list[str]:
    if int(truth.get("sprints") or 0) == 0:
        return [] if not_found_phrase(a.text) else ["볼 수 있는 회차가 없는데 답이 그 사실을 말하지 않았습니다."]
    body = norm(a.text)
    named = bool(truth.get("name")) and norm(truth.get("name")) in body
    if not (has_route(a.sources, "/sprint") or named):
        return ["회차 출처가 없고 답에 회차 이름도 없습니다."]
    decisions = int(truth.get("decisions") or 0)
    if decisions > 0:
        fragment = any(norm(f) and norm(f) in body for f in truth.get("fragments") or [])
        if not (fragment or number_in(a.text, decisions) or named):
            return ["회의에서 정한 것이 있는데 답에 그 내용이나 수가 없습니다."]
    return []


def check_q15(a: Answer, truth: dict, *, title: str) -> list[str]:
    failures = []
    key = norm(title)
    if any(norm(s.get("title")) == key for s in a.sources):
        failures.append("볼 수 없어야 할 문서가 출처에 나왔습니다.")
    if key and key in norm(a.text) and not not_found_phrase(a.text):
        failures.append("볼 수 없어야 할 문서를 찾지 못했다는 말 없이 그 제목으로 답했습니다.")
    return failures


def check_q16(a: Answer, truth: dict) -> list[str]:
    """없는 자료 — 「찾지 못함」 표시(no_results)가 서거나, 답이 찾지 · 확인하지 못했다고 말해야 한다.

    의미 검색이 켜진 설치에서는 뜻이 가장 가까운 문서가 언제나 몇 건 돌아오므로 도구가 no_results 를 내지 않는다(랩 실측
    2026-10-15 — 「결과 28건 중 8건, 세 낱말을 모두 포함한 문서는 0건」이라고 정직하게 답했는데 표시만 보고 실패로 셌다).
    요구는 표시가 아니라 답의 정직함이다: 찾아본 범위를 말하고, 찾지 못했다고 말하고, 없다고 단정하지 않는다."""
    failures = []
    says_not_found = bool(re.search(r"찾지\s?못|확인하지\s?못|찾을\s?수\s?없", a.text or ""))
    if a.notice != NOTICE_NO_RESULTS and not says_not_found:
        failures.append(f"찾지 못했다는 표시(no_results)도, 찾지 못했다는 말도 없습니다(notice={a.notice}).")
    if not searched_phrase(a.text):
        failures.append("무엇을 찾아봤는지 말하지 않았습니다.")
    if "존재하지 않" in (a.text or ""):
        failures.append("자료가 없다고 단정했습니다(「존재하지 않」).")
    return failures


# ── 황금 질문 열여덟 ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Question:
    qid: str
    template: str
    #: 대안 묶음 — 하나라도 실제 도구의 부분집합이면 통과다.
    expected: tuple[tuple[str, ...], ...] = ()
    #: 잡담 — 도구를 쓰면 실패다.
    chat: bool = False
    #: 이 값이 없으면 SKIP(`Options` 의 이름).
    needs: tuple[str, ...] = ()
    truth: Callable | None = None
    check: Callable | None = None


DOC_SEARCH = (("search_documents",), ("search_workspace",))

QUESTIONS: tuple[Question, ...] = (
    Question("q01", "내가 작성한 문서를 보여줘", (("my_documents",),), truth=truth_my_documents, check=check_q01),
    Question("q02", "내가 작성한 문서는 총 몇 개야?", (("my_documents",),), truth=truth_my_documents, check=check_q02),
    Question("q03", "VMware 네트워크 자동화 관련 문서를 찾아줘", DOC_SEARCH, truth=truth_vmware, check=_check_overlap),
    Question("q04", "\"{phrase}\"가 들어간 문서 목록을 알려줘", DOC_SEARCH, needs=("phrase",), truth=truth_phrase,
             check=_check_overlap),
    Question("q05", "{ambiguous} 프로젝트에서 지금까지 진행된 작업을 알려줘", needs=("ambiguous",), truth=truth_ambiguous,
             check=check_q05),
    Question("q06", "{project_code} 프로젝트 현재 진행 상황을 알려줘", (("project_activity",), ("get_project_summary",)),
             needs=("project_code",), truth=truth_project, check=check_q06),
    Question("q07", "내 프로젝트 진행 상황을 알려줘", (("search_projects",), ("project_activity",)), truth=truth_my_projects,
             check=check_q07),
    Question("q08", "내가 담당하는 미완료 티켓을 알려줘", (("my_work",),), truth=truth_open_tickets, check=check_q08),
    Question("q09", "이번 주 마감인 내 티켓을 알려줘", (("my_work",),), truth=truth_due_this_week, check=check_q09),
    Question("q10", "내가 참여한 프로젝트와 관련 자료를 알려줘", (("search_projects",),), truth=truth_my_projects,
             check=check_q10),
    Question("q11", "{project_code} 프로젝트의 문서와 진행 중인 티켓을 같이 보여줘",
             (("project_activity",), ("search_documents", "search_tickets"), ("search_workspace",)),
             needs=("project_code",), truth=truth_project_with_counts, check=check_q11),
    Question("q12", "내가 최근에 한 일을 알려줘", (("my_activity",),)),
    Question("q13", "안 읽은 알림이 있어?", (("my_notifications",),), truth=truth_unread, check=check_q13),
    Question("q14", "이번 스프린트 회의에서 정한 것을 알려줘", (("sprint_meetings",),), truth=truth_sprint, check=check_q14),
    Question("q15", "\"{other_title}\" 문서 내용을 알려줘", needs=("other_title",), truth=truth_other_title),
    Question("q16", "2031년 우주 출장 규정을 알려줘", DOC_SEARCH, check=check_q16),
    Question("q17", "안녕, 오늘 기분 어때?", chat=True),
    Question("q18", "SLA 가 뭐야?"),
)


# ── 실행 ─────────────────────────────────────────────────────────────────────


@dataclass
class TruthRun:
    base: str
    label: str
    persona: str
    started: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    results: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)

    def counts(self) -> dict:
        out = {PASS: 0, FAIL: 0, SKIP: 0}
        for r in self.results:
            out[r["verdict"]] = out.get(r["verdict"], 0) + 1
        return out


def _tool_view(a: Answer) -> list[dict]:
    return [{k: t.get(k) for k in ("name", "ok", "count", "total", "query") if k in t} for t in a.tools]


def _source_view(a: Answer) -> list[dict]:
    return [{"type": s.get("type"), "title": (s.get("title") or "")[:80], "route": s.get("route")} for s in a.sources[:12]]


def ask(client: httpx.Client, headers: dict, question: str, *, timeout: float, keep: bool, title: str,
        notes: list[str]) -> tuple[Answer | None, dict]:
    """새 대화에서 한 번 묻는다. (답 또는 None, 실행 정보 — 실패 사유 · 걸린 초 · 처리 상태)."""
    meta: dict = {"failures": []}
    conversation_id, created = create_conversation(client, headers, title)
    if conversation_id is None:
        meta["failures"].append(f"대화를 만들지 못했습니다(상태 {created.get('status')}).")
        return None, meta
    try:
        status, posted = post_question(client, headers, conversation_id, question, prefix="aitruth-")
        if status != 202:
            meta["failures"].append(f"질문을 보내지 못했습니다(상태 {status}).")
            meta["post_body"] = posted
            return None, meta
        user_message_id = posted["message"]["message_id"]
        got = await_reply(client, headers, conversation_id, user_message_id, timeout=timeout)
        meta["seconds"] = got.get("seconds")
        if got.get("timeout"):
            meta["failures"].append(f"{got.get('seconds')}초 안에 답이 오지 않았습니다.")
            meta["last"] = got.get("last")
            return None, meta
        user = got["user"]
        reply = got["reply"]
        meta["processing_status"] = user.get("processing_status")
        meta["error_code"] = user.get("error_code")
        return Answer(text=reply.get("content") or "", structured=reply.get("structured") or {}), meta
    finally:
        if keep:
            notes.append(f"대화를 남겼습니다({conversation_id}).")
        else:
            try:
                delete_conversation(client, headers, conversation_id)
            except httpx.HTTPError as exc:
                notes.append(f"대화({conversation_id})를 지우지 못했습니다({type(exc).__name__}).")


def evaluate(q: Question, a: Answer, meta: dict, truth: dict, opts: Options) -> list[str]:
    """한 질문의 실패 사유 목록(비면 통과)."""
    failures = list(meta.get("failures") or [])
    if meta.get("processing_status") != "done":
        failures.append(f"처리가 끝나지 않았거나 실패했습니다(상태 {meta.get('processing_status')}).")
    if a.structured.get("error_notice"):
        failures.append("오류 안내 답이 나왔습니다.")
    if a.mode != MODE_TOOLS:
        failures.append(f"도구 모드가 아닙니다(mode={a.mode}).")
    if q.chat and a.tool_names:
        failures.append(f"잡담인데 도구를 썼습니다({', '.join(a.tool_names)}).")
    if not tools_satisfied(a.tool_names, q.expected):
        expected = " 또는 ".join("+".join(alt) for alt in q.expected)
        failures.append(f"기대한 도구를 쓰지 않았습니다(기대 {expected}, 실제 {', '.join(a.tool_names) or '없음'}).")
    if not (a.text or "").strip():
        failures.append("답이 비어 있습니다.")
    if q.qid == "q15":
        failures += check_q15(a, truth, title=opts.other_title or "")
    elif q.check is not None:
        failures += q.check(a, truth)
    return failures


def run_question(client: httpx.Client, headers: dict, api: Api, q: Question, opts: Options, *, timeout: float,
                 keep: bool, stamp: str, notes: list[str]) -> dict:
    values = opts.values()
    missing = [name for name in q.needs if not values.get(name)]
    out = {"id": q.qid, "question": q.template, "expected": [list(a) for a in q.expected], "chat": q.chat}
    if missing:
        out.update(verdict=SKIP, why=f"{', '.join(missing)} 값이 없어 건너뜁니다.")
        log(f"[  SKIP  ] {q.qid}: {out['why']}")
        return out
    question = q.template.format(**values)
    out["question"] = question
    truth: dict = {}
    if q.truth is not None:
        try:
            truth = q.truth(api, opts)
        except TruthError as exc:
            out.update(verdict=FAIL, failures=[str(exc)])
            log(f"[  FAIL  ] {q.qid}: {exc}")
            return out
        if truth.get("skip"):
            out.update(verdict=SKIP, why=truth["skip"])
            log(f"[  SKIP  ] {q.qid}: {truth['skip']}")
            return out
    out["truth"] = _truth_view(truth)
    answer, meta = ask(client, headers, question, timeout=timeout, keep=keep, title=f"AI 진실 하네스 {q.qid} {stamp}",
                       notes=notes)
    out["seconds"] = meta.get("seconds")
    if answer is None:
        out.update(verdict=FAIL, failures=meta.get("failures") or ["답을 받지 못했습니다."])
        log(f"[  FAIL  ] {q.qid}: {out['failures'][0]}")
        return out
    failures = evaluate(q, answer, meta, truth, opts)
    out.update(
        verdict=FAIL if failures else PASS, failures=failures, mode=answer.mode, notice=answer.notice,
        tools=_tool_view(answer), sources=_source_view(answer), sources_count=len(answer.sources),
        answer_excerpt=mask_emails((answer.text or "")[:EXCERPT_CHARS]),
    )
    log(f"[{out['verdict']:^8}] {q.qid}: tools={','.join(answer.tool_names) or '-'} mode={answer.mode} "
        f"notice={answer.notice} sources={len(answer.sources)}" + (f" → {failures[0]}" if failures else ""))
    return out


def _truth_view(truth: dict) -> dict:
    """결과 파일에 적을 진실 — 목록은 앞 열 개만."""
    out = {}
    for key, value in (truth or {}).items():
        out[key] = value[:10] if isinstance(value, list) else value
    return out


def _probe_body(text: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def run_index_probe(client: httpx.Client, headers: dict, *, timeout: float, keep: bool, stamp: str,
                    notes: list[str]) -> dict:
    """색인 반영 확인 — 만들고 → AI 검색에 뜨는지 → 도우미가 찾는지 → 보관 → 다시 물어 안 보이는지. 문서는 끝에 걷는다."""
    title = f"[AI검증] 색인 반영 확인 {stamp}"
    out: dict = {"id": "probe", "question": f"\"{title}\" 문서를 찾아줘", "steps": []}
    failures: list[str] = []
    document_id = None
    archived = purged = False
    try:
        r = client.post("/api/knowledge/documents", headers=headers, json={
            "title": title, "body": _probe_body(f"AI 도우미의 색인 반영을 확인하는 임시 문서입니다. 확인 표식은 probe{stamp} 입니다."),
        })
        if r.status_code == 403:
            out.update(verdict=SKIP, why="이 계정은 문서를 만들 수 없어 색인 확인을 건너뜁니다.")
            return out
        body = json_of(r)
        if r.status_code != 200 or not isinstance(body, dict) or not body.get("id"):
            out.update(verdict=FAIL, failures=[f"확인 문서를 만들지 못했습니다(상태 {r.status_code})."])
            return out
        document_id = body["id"]
        out["steps"].append("확인 문서를 조직 공통 공간에 만들었습니다.")
        started = time.monotonic()
        seen_after = None
        while time.monotonic() - started < INDEX_PROBE_SECONDS:
            s = client.get("/api/ai/search", params={"q": title, "limit": 20}, headers=headers)
            found = json_of(s) if s.status_code == 200 else {}
            if any(c.get("document_id") == document_id for c in (found.get("citations") or []) if isinstance(c, dict)):
                seen_after = round(time.monotonic() - started, 1)
                break
            time.sleep(INDEX_PROBE_INTERVAL)
        if seen_after is None:
            failures.append(f"{int(INDEX_PROBE_SECONDS)}초 안에 AI 검색에 새 문서가 나오지 않았습니다.")
        else:
            out["steps"].append(f"AI 검색에 {seen_after}초 만에 나왔습니다.")
            out["indexed_after_seconds"] = seen_after
        answer, meta = ask(client, headers, out["question"], timeout=timeout, keep=keep,
                           title=f"AI 진실 하네스 색인 확인 {stamp}", notes=notes)
        if answer is None:
            failures += meta.get("failures") or ["답을 받지 못했습니다."]
        else:
            if not tools_satisfied(answer.tool_names, DOC_SEARCH):
                failures.append("문서 검색 도구를 쓰지 않았습니다.")
            if document_id not in source_ids(answer.sources):
                failures.append("도우미의 출처에 새 문서가 없습니다.")
            out["first_answer"] = {"tools": _tool_view(answer), "sources_count": len(answer.sources),
                                   "excerpt": mask_emails((answer.text or "")[:EXCERPT_CHARS])}
        d = client.delete(f"/api/knowledge/documents/{document_id}", headers=headers)
        archived = d.status_code == 200
        out["steps"].append(f"확인 문서를 보관했습니다(상태 {d.status_code}).")
        if archived:
            again, meta = ask(client, headers, out["question"], timeout=timeout, keep=keep,
                              title=f"AI 진실 하네스 색인 확인 재질문 {stamp}", notes=notes)
            if again is None:
                failures += meta.get("failures") or ["다시 물은 답을 받지 못했습니다."]
            else:
                if document_id in source_ids(again.sources):
                    failures.append("보관한 문서가 여전히 도우미의 출처에 나왔습니다.")
                out["second_answer"] = {"tools": _tool_view(again), "sources_count": len(again.sources),
                                        "notice": again.notice, "excerpt": mask_emails((again.text or "")[:EXCERPT_CHARS])}
        else:
            failures.append("확인 문서를 보관하지 못했습니다.")
    finally:
        if document_id:
            try:
                if not archived:
                    d = client.delete(f"/api/knowledge/documents/{document_id}", headers=headers)
                    archived = d.status_code == 200
                p = client.post(f"/api/knowledge/documents/{document_id}/purge", headers=headers)
                purged = p.status_code == 200
                out["steps"].append(f"확인 문서를 휴지통에서 영구 삭제했습니다(상태 {p.status_code})." if purged
                                    else f"확인 문서를 영구 삭제하지 못했습니다(상태 {p.status_code}). 휴지통에서 직접 지워 주세요.")
            except httpx.HTTPError as exc:
                out["steps"].append(f"확인 문서를 걷다가 연결이 끊겼습니다({type(exc).__name__}).")
            if not purged:
                notes.append(f"확인 문서({document_id})가 남았습니다. 문서 화면이나 휴지통에서 직접 지워 주세요.")
    if "verdict" not in out:
        out.update(verdict=FAIL if failures else PASS, failures=failures)
    log(f"[{out['verdict']:^8}] probe: " + (out.get("why") or (failures[0] if failures else " · ".join(out["steps"]))))
    return out


def _admin_index(api: Api) -> dict | None:
    """시스템 관리자면 AI 연결 화면의 색인 · 도구 사실을 함께 적는다(정보용). 아니면 None."""
    status, body = api.get("/api/admin/ai")
    if status != 200 or not isinstance(body, dict):
        return None
    index = body.get("index") or {}
    return {
        "embed_status": index.get("embed_status"), "embed_status_label": index.get("embed_status_label"),
        "pending_embedding": index.get("pending_embedding"), "chunks": index.get("chunks"),
        "embedded": index.get("embedded"), "tools": (body.get("capabilities") or {}).get("tools"),
    }


def resolve_credentials(env_file: str | None) -> dict[str, str]:
    """환경 변수 → `--env-file`(있으면 그 파일의 값이 이긴다). 넷만 읽는다."""
    values = {k: os.environ.get(k) or "" for k in ENV_KEYS}
    if env_file:
        for key, value in read_env_file(env_file, ENV_KEYS).items():
            if value:
                values[key] = value
    return values


def write_results(run: TruthRun, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = run.counts()
    data = {"base": run.base, "label": run.label, "persona": run.persona, "started_at": run.started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(), "context": run.context, "counts": counts,
            "results": run.results, "notes": run.notes}
    json_path = out_dir / f"{run.label}.json"
    json_path.write_text(mask_emails(json.dumps(data, ensure_ascii=False, indent=1)), encoding="utf-8", newline="\n")
    lines = [f"# AI 진실 하네스 — {run.label}", "",
             f"- 대상: {run.base}", f"- 사용자: {run.persona}", f"- 시작: {run.started:%Y-%m-%d %H:%M} UTC",
             f"- 결과: PASS {counts[PASS]} · FAIL {counts[FAIL]} · SKIP {counts[SKIP]}"]
    if run.context.get("admin_index"):
        lines.append(f"- 색인 · 도구(관리 화면): `{json.dumps(run.context['admin_index'], ensure_ascii=False)}`")
    lines += ["", "| id | 질문 | 판정 | 도구 | 출처 | mode / notice | 실패 사유 · 건너뛴 까닭 | 답(앞부분) |",
              "|---|---|---|---|---|---|---|---|"]
    for r in run.results:
        tools = ",".join(t.get("name") or "" for t in r.get("tools") or []) or "-"
        reasons = " / ".join(r.get("failures") or []) or (r.get("why") or "")
        excerpt = (r.get("answer_excerpt") or (r.get("first_answer") or {}).get("excerpt") or "")
        cells = [r["id"], r.get("question", ""), r["verdict"], tools, str(r.get("sources_count", "")),
                 f"{r.get('mode') or ''} / {r.get('notice') or ''}", reasons, excerpt[:160]]
        lines.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in cells) + " |")
    if run.notes:
        lines += ["", *[f"- {n}" for n in run.notes]]
    md_path = out_dir / f"{run.label}.md"
    md_path.write_text(mask_emails("\n".join(lines) + "\n"), encoding="utf-8", newline="\n")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base", default=DEFAULT_BASE, help="대상 주소(기본: capture.DEFAULT_BASE_URL)")
    parser.add_argument("--env-file", default=None, help="AI_TRUTH_EMAIL · AI_TRUTH_PASSWORD 를 읽을 파일(그 두 키와 선택 키 둘만 읽는다)")
    parser.add_argument("--cacert", default=None, help="TLS 기준점 파일(자가 서명 인증서)")
    parser.add_argument("--insecure", action="store_true", help="TLS 검증을 끈다(결과에 그 사실을 적는다)")
    parser.add_argument("--label", default=None, help="결과 파일 이름(기본: 호스트-시각)")
    parser.add_argument("--only", nargs="+", default=None, help="고른 질문만(q01 · 8 · q15 …)")
    parser.add_argument("--timeout", type=float, default=180.0, help="질문 하나의 답을 기다리는 초")
    parser.add_argument("--keep", action="store_true", help="만든 대화를 지우지 않는다")
    parser.add_argument("--project-code", default=None, help="⑥ · ⑪ 에 쓸 프로젝트 코드")
    parser.add_argument("--phrase", default=None, help="④ 에 쓸 문서 문구")
    parser.add_argument("--ambiguous-project", default=None, help="⑤ 에 쓸, 이름이 여러 프로젝트에 걸리는 낱말(환경 변수 AI_TRUTH_AMBIGUOUS_PROJECT)")
    parser.add_argument("--with-index-probe", action="store_true", help="확인 문서를 만들어 색인 반영을 재고 끝에 걷는다")
    parser.add_argument("--out", default=str(OUT_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    args = build_parser().parse_args(argv)
    try:
        creds = resolve_credentials(args.env_file)
    except OSError as exc:
        print(f"env 파일을 읽지 못했습니다({type(exc).__name__}).", file=sys.stderr)
        return 2
    email, password = creds[ENV_EMAIL], creds[ENV_PASSWORD]
    if not email or not password:
        print(f"{ENV_EMAIL} · {ENV_PASSWORD} 가 없습니다(환경 변수나 --env-file 로만 받는다).", file=sys.stderr)
        return 2
    opts = Options(phrase=args.phrase or None, project_code=args.project_code or None,
                   ambiguous=args.ambiguous_project or creds[ENV_AMBIGUOUS] or None,
                   other_title=creds[ENV_OTHER_TITLE] or None)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    host = (urlsplit(args.base).hostname or "lab").replace(".", "-")
    run = TruthRun(base=args.base, label=args.label or f"{host}-{stamp}", persona=mask_emails(email))
    if args.insecure:
        run.notes.append("TLS 검증을 끄고 쟀습니다(--insecure).")
    only = parse_only(args.only)
    client = make_client(args.base, verify=resolve_verify(args.base, cacert=args.cacert, insecure=args.insecure),
                         timeout=90.0)
    try:
        headers = login(client, email, password)
    except LoginError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except httpx.HTTPError as exc:
        print(f"서버에 연결하지 못했습니다({type(exc).__name__}).", file=sys.stderr)
        return 2
    api = Api(client, headers)
    status, body = api.get("/api/ai/status")
    assistant = (body or {}).get("assistant") if isinstance(body, dict) else None
    run.context["assistant"] = assistant
    admin_index = _admin_index(api)
    if admin_index is not None:
        run.context["admin_index"] = admin_index
    available = bool(assistant and assistant.get("available"))
    for q in QUESTIONS:
        if only is not None and q.qid not in only:
            continue
        if not available:
            run.results.append({"id": q.qid, "question": q.template, "verdict": FAIL,
                                "failures": [f"도우미를 쓸 수 없습니다(상태 {status}, 까닭 {(assistant or {}).get('reason')})."]})
            continue
        try:
            run.results.append(run_question(client, headers, api, q, opts, timeout=args.timeout, keep=args.keep,
                                            stamp=stamp, notes=run.notes))
        except httpx.HTTPError as exc:
            run.results.append({"id": q.qid, "question": q.template, "verdict": FAIL,
                                "failures": [f"서버와의 연결이 끊겼습니다({type(exc).__name__})."]})
    if args.with_index_probe:
        if available:
            try:
                run.results.append(run_index_probe(client, headers, timeout=args.timeout, keep=args.keep, stamp=stamp,
                                                   notes=run.notes))
            except httpx.HTTPError as exc:
                run.results.append({"id": "probe", "question": "색인 반영 확인", "verdict": FAIL,
                                    "failures": [f"서버와의 연결이 끊겼습니다({type(exc).__name__})."]})
        else:
            run.results.append({"id": "probe", "question": "색인 반영 확인", "verdict": FAIL,
                                "failures": ["도우미를 쓸 수 없어 색인 확인을 하지 못했습니다."]})
    json_path, md_path = write_results(run, Path(args.out))
    counts = run.counts()
    ok = counts[FAIL] == 0
    log(f"AI_TRUTH_E2E {'OK' if ok else 'FAILED'} pass={counts[PASS]} fail={counts[FAIL]} skip={counts[SKIP]} → {md_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
