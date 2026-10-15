"""AI 도우미 대화 하네스 — 한 대화 안에서 이어지는 질문을 실데이터와 맞춘다(AI 채팅 개선 회차).

`ai_truth_e2e.py` 는 질문마다 새 대화다. 이 하네스는 **같은 대화의 여러 차례**를 묻는다 — 「다음 10개」 「그중 VMware」
「첫 번째 문서」처럼 앞 목록을 가리키는 질문이 그 목록을 정말 이어 쓰는가를 본다. 진실은 매번 그 시각의 화면 API 다
(고정 숫자를 쓰지 않는다).

## 지키는 것

- 비밀은 명령행에 받지 않는다. `--env-file`(기본 `dist/ops/user.env`)에서 `AI_TRUTH_EMAIL` · `AI_TRUTH_PASSWORD` 만 읽고
  값은 어디에도 찍지 않는다.
- 이 하네스가 만든 대화(제목 「[AI검증] …」)만 쓰고 끝에 지운다(`--keep` 이면 남긴다). 다른 대화 · 자료 · 설정은 건드리지 않는다.
- 결과 파일의 글은 이메일을 가리고 답은 앞 600자만 싣는다.

## 쓰는 법

    python -m scripts.ui_qa.ai_chat_e2e --label lab-chat-before --project-code <코드> --ambiguous-project <겹치는 이름>
    … --only A D       # 고른 대화만
    … --capture        # 대화 A 를 남겨 화면을 찍고(1920 · 1366 · 1024 · 390 · 125% × 밝음 · 어둠) 끝에 지운다

결과: `dist/ui-qa/ai-chat-e2e/<label>.json` · `.md`, 요약 줄 `AI_CHAT_E2E OK|FAILED pass=… fail=… na=…`.
판정은 셋이다 — PASS · FAIL · NA(이 빌드에 아직 없는 기능: 결과 블록 · 쪽 넘기기). FAIL 이 있으면 종료 코드 1, 로그인 · 설정 오류는 2.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
from scripts.ui_qa.ai_truth_e2e import (  # noqa: E402
    TERMINAL_STATUSES,
    Api,
    TruthError,
    asks_which,
    keys_mentioned,
    norm,
    not_found_phrase,
    number_in,
    says_none,
    searched_phrase,
)
from scripts.ui_qa.capture import DEFAULT_BASE_URL as DEFAULT_BASE  # noqa: E402

OUT_DIR = ROOT / "dist" / "ui-qa" / "ai-chat-e2e"
LAB_SHOTS = ROOT / "dist" / "ui-qa-lab"
ENV_KEYS = ("AI_TRUTH_EMAIL", "AI_TRUTH_PASSWORD")
PASS, FAIL, NA = "PASS", "FAIL", "NA"
EXCERPT_CHARS = 600
PAGE = 10
#: VMware 주제로 볼 낱말(저장소 동의어 묶음과 같은 갈래, `app/core/search_synonyms.py`).
VMWARE_WORDS = ("vmware", "vsphere", "esxi", "vcenter", "vcf", "nsx", "vsan", "브이엠웨어")
KST = timezone(timedelta(hours=9))
#: 도우미 도구 이름 — 답 글에 이 이름이 나오면 내부 이름이 사용자에게 샌 것이다.
TOOL_NAMES = ("my_documents", "search_documents", "get_document", "search_workspace", "my_work", "get_ticket",
              "search_tickets", "search_projects", "get_project_summary", "project_activity", "my_approvals",
              "find_people", "recent_changes", "work_summary", "my_notifications", "my_activity", "sprint_meetings")
KEY_RE = re.compile(r"(?<![A-Za-z0-9-])[A-Z][A-Z0-9]{1,9}-\d{1,6}(?![A-Za-z0-9])")
#: 캡처 크기 — (폭, 높이, 배율). 125% 는 1920 화면을 125% 로 본 것과 같은 CSS 폭이다.
SHOT_SIZES = ((1920, 1080, 1), (1366, 768, 1), (1024, 768, 1), (390, 844, 1), (1536, 864, 1.25))


# ── 판정 조각(순수) ─────────────────────────────────────────────────────────────


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


def check(name: str, ok: bool, detail: str = "") -> Check:
    return Check(name, PASS if ok else FAIL, detail)


def na(name: str, detail: str = "이 빌드에 아직 없는 기능입니다.") -> Check:
    return Check(name, NA, detail)


def first_sentence(text: str) -> str:
    """첫 문장 — 「다.」 「요.」 「니다」 · 줄바꿈 중 먼저 오는 자리까지."""
    value = (text or "").strip()
    m = re.search(r"(다\.|요\.|\?|\n)", value)
    return value[: m.end()] if m else value


def relisted(text: str, titles) -> int:
    """제목(네 글자 이상) 중 답 글에 그대로 다시 나온 수."""
    body = norm(text)
    return sum(1 for t in titles or () if len(norm(t)) >= 4 and norm(t) in body)


def repeated_meta_lines(text: str) -> int:
    """「…, 2026-09-04」 처럼 같은 「이름, 날짜」 꼬리가 되풀이되는 줄의 가장 큰 묶음 수."""
    tails: dict[str, int] = {}
    for line in (text or "").splitlines():
        m = re.search(r"([^\s,()\[\]]{2,12}),\s*\d{4}-\d{2}-\d{2}\s*$", line.strip())
        if m:
            tails[m.group(1)] = tails.get(m.group(1), 0) + 1
    return max(tails.values()) if tails else 0


def week_start_utc(now: datetime) -> datetime:
    """이번 주 월요일 0시(KST)를 Z 없는 UTC 로 — 서버 시각과 같은 꼴로 견준다."""
    local = now.astimezone(KST)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(timezone.utc).replace(tzinfo=None)


def parse_naive(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None


def vmware_like(text: str) -> bool:
    value = norm(text)
    return any(w in value for w in VMWARE_WORDS)


# ── 답 ────────────────────────────────────────────────────────────────────────


@dataclass
class Reply:
    text: str
    structured: dict
    message_id: str | None
    seconds: float | None
    failed: bool = False

    @property
    def tools(self) -> list[dict]:
        return [t for t in (self.structured.get("tools") or []) if isinstance(t, dict)]

    @property
    def tool_names(self) -> list[str]:
        return [str(t.get("name")) for t in self.tools]

    @property
    def has_blocks_feature(self) -> bool:
        return "results" in self.structured

    @property
    def blocks(self) -> list[dict]:
        return [b for b in (self.structured.get("results") or []) if isinstance(b, dict)]

    def shown(self, tool: str | None = None) -> list[dict]:
        return [b for b in self.blocks if b.get("shown") and (tool is None or b.get("tool") == tool)]

    @property
    def sources(self) -> list[dict]:
        return [s for s in (self.structured.get("sources") or []) if isinstance(s, dict)]


def block_titles(block: dict | None) -> list[str]:
    return [str(i.get("title") or "") for i in (block or {}).get("items") or [] if isinstance(i, dict)]


def cited_ticket_keys(r: Reply) -> list[str]:
    """답 글이 인용한 티켓 출처의 키 — 서버가 경로 · 키 · 제목이 글에 있을 때 `cited` 를 단다."""
    return [str(s.get("key")) for s in r.sources if s.get("type") == "ticket" and s.get("cited") and s.get("key")]


def shown_ticket_keys(r: Reply) -> list[str]:
    return [str(i.get("key")) for b in r.shown() if b.get("kind") == "ticket"
            for i in b.get("items") or [] if isinstance(i, dict) and i.get("key")]


def leaked_tool_names(text: str) -> list[str]:
    return [name for name in TOOL_NAMES if name in (text or "")]


def block_ids(block: dict | None) -> list[str]:
    return [str(i.get("id") or i.get("ref") or "") for i in (block or {}).get("items") or [] if isinstance(i, dict)]


# ── 문맥 ──────────────────────────────────────────────────────────────────────


@dataclass
class Ctx:
    api: Api
    me: str
    project_code: str | None
    ambiguous: str | None
    replies: list[Reply] = field(default_factory=list)
    memo: dict = field(default_factory=dict)

    @property
    def last(self) -> Reply | None:
        return self.replies[-1] if self.replies else None


def my_docs_page(ctx: Ctx, offset: int) -> tuple[int, list[dict]]:
    body = ctx.api.get_ok("/api/knowledge/documents", mine="true", sort="recent", limit=PAGE, offset=offset)
    items = [i for i in body.get("items") or [] if isinstance(i, dict)]
    return int(body.get("total") or 0), items


def doc_detail(ctx: Ctx, doc_id: str) -> dict | None:
    status, body = ctx.api.get(f"/api/knowledge/documents/{doc_id}")
    if status != 200 or not isinstance(body, dict):
        return None
    return body.get("document") if isinstance(body.get("document"), dict) else body


def my_tickets(ctx: Ctx) -> list[dict]:
    items, _total, _partial = ctx.api.pages("/api/tickets/mine")
    return items


def project_by_code(ctx: Ctx, code: str | None) -> dict | None:
    if not code:
        return None
    items, _total, _partial = ctx.api.pages("/api/projects", q=code)
    exact = [p for p in items if (p.get("code") or "").lower() == code.lower()]
    return exact[0] if exact else None


# ── 시나리오 ──────────────────────────────────────────────────────────────────


@dataclass
class Turn:
    question: str | Callable[[Ctx], str | None]
    judge: Callable[[Ctx, Reply], list[Check]]


@dataclass
class Scenario:
    key: str
    title: str
    turns: list[Turn]


def judge_a1(ctx: Ctx, r: Reply) -> list[Check]:
    total, page1 = my_docs_page(ctx, 0)
    titles = [i.get("title") or "" for i in page1]
    ctx.memo["docs_total"] = total
    out = [
        check("내 문서 도구", "my_documents" in r.tool_names, ",".join(r.tool_names)),
        check("답에 전체 수", number_in(r.text, total), f"진실 {total}"),
        check("첫 문장에 전체 수", number_in(first_sentence(r.text), total), first_sentence(r.text)[:80]),
        check("같은 「이름, 날짜」 줄이 셋 미만", repeated_meta_lines(r.text) < 3, f"최대 {repeated_meta_lines(r.text)}줄"),
    ]
    if not r.has_blocks_feature:
        out += [na("보인 목록 블록"), na("블록 제목을 다시 나열하지 않음"), na("쪽 넘기기 = 둘째 쪽")]
        return out
    block = next(iter(r.shown("my_documents")), None)
    out.append(check("보인 목록 블록", block is not None))
    if block is None:
        return out
    out.append(check("블록 total = 화면", int(block.get("total") or -1) == total, f"블록 {block.get('total')} 진실 {total}"))
    out.append(check("블록 제목 = 화면 첫 쪽", block_titles(block) == titles,
                     f"블록 {block_titles(block)[:3]} 진실 {titles[:3]}"))
    out.append(check("블록 제목을 다시 나열하지 않음", relisted(r.text, titles) <= 2, f"{relisted(r.text, titles)}개"))
    if r.message_id and block.get("id"):
        status, body = ctx.api.get(f"/api/messages/{r.message_id}/results/{block['id']}", offset=PAGE)
        _total2, page2 = my_docs_page(ctx, PAGE)
        got = page_titles(body)
        out.append(check("쪽 넘기기 = 둘째 쪽", status == 200 and got == [i.get("title") or "" for i in page2],
                         f"상태 {status}, {got[:2]}"))
    return out


def judge_a2(ctx: Ctx, r: Reply) -> list[Check]:
    total = ctx.memo.get("docs_total")
    if total is None:
        total, _ = my_docs_page(ctx, 0)
    return [check("답에 전체 수", number_in(r.text, total), f"진실 {total}"),
            check("짧은 답", len(r.text) <= 400, f"{len(r.text)}자")]


def judge_a3(ctx: Ctx, r: Reply) -> list[Check]:
    _total, page2 = my_docs_page(ctx, PAGE)
    titles = [i.get("title") or "" for i in page2]
    if not r.has_blocks_feature:
        hit = relisted(r.text, titles)
        return [check("둘째 쪽 제목을 말함(글)", hit >= 5, f"{hit}/{len(titles)}"),
                na("블록 offset 10"), na("블록 = 화면 둘째 쪽")]
    block = next(iter(r.shown("my_documents")), None)
    out = [check("보인 목록 블록", block is not None)]
    if block is None:
        return out
    out.append(check("블록 offset 10", int(block.get("offset") or 0) == PAGE, f"offset {block.get('offset')}"))
    out.append(check("블록 = 화면 둘째 쪽", block_titles(block) == titles, f"{block_titles(block)[:2]} / {titles[:2]}"))
    return out


def page_titles(body) -> list[str]:
    """쪽 넘기기 응답(`{"block": {...items}}`)의 제목들."""
    block = body.get("block") if isinstance(body, dict) and isinstance(body.get("block"), dict) else body
    items = block.get("items") if isinstance(block, dict) else None
    return [str(i.get("title") or "") for i in items or [] if isinstance(i, dict)]


def _doc_items_of(r: Reply) -> list[tuple[str, str]]:
    """(id, 제목) — 보인 문서 블록(또는 보인 프로젝트 카드의 연결 문서)이 있으면 그 항목, 없으면 인용된 문서 출처.

    블록 항목의 id 칸은 `ref` 다(서버 `blocks.FIELDS`). 예전에는 `id` 를 읽어 빈 id 로 문서를 찾았고, 「내 문서 중 VMware」의
    항목이 모두 남의 문서처럼 세어졌다(랩 2026-10-15 r22-chat-after B④ 0/8)."""
    out: list[tuple[str, str]] = []
    for block in r.shown():
        rows = []
        if block.get("kind") == "document":
            rows = block.get("items") or []
        elif block.get("kind") == "project_summary":
            for card in block.get("items") or []:
                rows += ((card.get("documents") or {}).get("items") or []) if isinstance(card, dict) else []
        out += [(str(i.get("ref") or i.get("id") or ""), str(i.get("title") or "")) for i in rows if isinstance(i, dict)]
    if out:
        return out
    for s in r.sources:
        route = str(s.get("route") or "")
        if route.startswith("/knowledge/") and (s.get("cited") or s.get("shown")):
            out.append((route.split("/knowledge/", 1)[1].split("?", 1)[0], str(s.get("title") or "")))
    return out


def judge_b4(ctx: Ctx, r: Reply) -> list[Check]:
    names = r.tool_names
    out = [check("작성자 조건 + 주제 검색", "my_documents" in names or "search_documents" in names, ",".join(names))]
    items = _doc_items_of(r)
    ctx.memo["b4_items"] = items
    if not items:
        out.append(check("0건이면 정직하게", not_found_phrase(r.text), r.text[:80]))
        return out
    mine, topical, details = 0, 0, []
    for doc_id, title in items[:10]:
        detail = doc_detail(ctx, doc_id) or {}
        details.append(detail)
        if str(detail.get("created_by") or "") == ctx.me:
            mine += 1
        if vmware_like(title) or vmware_like(str((detail.get("current") or {}).get("body_markdown") or "")[:4000]):
            topical += 1
    ctx.memo["b4_details"] = [(d.get("id"), d.get("title"), d.get("updated_at")) for d in details if d]
    out.append(check("항목이 모두 내 문서", mine == min(len(items), 10), f"{mine}/{min(len(items), 10)}"))
    out.append(check("VMware 계열 낱말이 있다", topical >= 1, f"{topical}건"))
    return out


def judge_b5(ctx: Ctx, r: Reply) -> list[Check]:
    details = [d for d in ctx.memo.get("b4_details") or [] if d and d[2]]
    if not details:
        return [na("가장 최근 문서 요약", "앞 차례에 문서가 없었습니다.")]
    latest = max(details, key=lambda d: d[2])
    title = str(latest[1] or "")
    cited = any(str(s.get("route") or "").startswith(f"/knowledge/{latest[0]}") for s in r.sources)
    return [check("문서를 읽었다", "get_document" in r.tool_names, ",".join(r.tool_names)),
            check("가장 최근 문서를 골랐다", cited or norm(title) in norm(r.text), title[:40]),
            check("요약이 있다", len(r.text) >= 80, f"{len(r.text)}자")]


def judge_c6(ctx: Ctx, r: Reply) -> list[Check]:
    items = my_tickets(ctx)
    open_items = [t for t in items if (t.get("status") or "") not in TERMINAL_STATUSES]
    n = len(open_items)
    out = [check("내 업무 도구", "my_work" in r.tool_names, ",".join(r.tool_names)),
           check("미완료 수", number_in(r.text, n) or (n == 0 and says_none(r.text)), f"진실 {n}")]
    if r.has_blocks_feature and n:
        block = next(iter(r.shown("my_work")), None)
        out.append(check("블록 total = 화면", block is not None and int(block.get("total") or -1) == n,
                         f"블록 {(block or {}).get('total')} 진실 {n}"))
    return out


def judge_c7(ctx: Ctx, r: Reply) -> list[Check]:
    start = week_start_utc(datetime.now(timezone.utc))
    done = [t for t in my_tickets(ctx) if (t.get("status") or "") == "완료"
            and (parse_naive(t.get("completed_at")) or datetime.min) >= start]
    keys = [t.get("key") for t in done if t.get("key")]
    n = len(done)
    out = [check("이번 주 완료 수", number_in(r.text, n) or (n == 0 and says_none(r.text)), f"진실 {n} {keys[:5]}")]
    if keys:
        out.append(check("키를 말함(글 또는 보인 목록)", bool(keys_mentioned(r.text, keys)) or bool(set(shown_ticket_keys(r)) & set(keys)),
                         f"{keys[:5]}"))
    return out


def question_d8b(ctx: Ctx) -> str | None:
    last = ctx.last
    if last is None or not ctx.project_code:
        return None
    return f"{ctx.project_code} 프로젝트로 알려줘." if asks_which(last.text) else None


def judge_d8(ctx: Ctx, r: Reply) -> list[Check]:
    items, total, _p = ctx.api.pages("/api/projects", q=ctx.ambiguous) if ctx.ambiguous else ([], 0, False)
    names = [p.get("name") for p in items if p.get("name")]
    out = [check("현황 도구", any(n in r.tool_names for n in ("project_activity", "get_project_summary", "search_projects")),
                 ",".join(r.tool_names))]
    if total >= 2:
        both = sum(1 for n in names if norm(n) in norm(r.text))
        out.append(check("이름이 여럿이면 되묻거나 둘을 보인다", asks_which(r.text) or both >= 2, f"후보 {total}"))
    return out


def judge_project_card(ctx: Ctx, r: Reply) -> list[Check]:
    project = project_by_code(ctx, ctx.project_code)
    if project is None:
        return [na("프로젝트 현황", "프로젝트 코드가 없거나 보이지 않습니다.")]
    ctx.memo["project"] = project
    pct = project.get("progress_pct")
    shown = f"{round(float(pct))}" if isinstance(pct, (int, float)) else None
    out = [check("진행률을 말함", shown is not None and (shown in r.text or f"{float(pct):.1f}" in r.text), f"진실 {pct}")]
    if r.has_blocks_feature:
        card = next(iter(b for b in r.shown() if b.get("kind") == "project_summary"), None)
        out.append(check("프로젝트 카드", card is not None))
    return out


def judge_d9(ctx: Ctx, r: Reply) -> list[Check]:
    project = ctx.memo.get("project") or project_by_code(ctx, ctx.project_code)
    if project is None:
        return [na("최근 해결한 문제", "프로젝트가 없습니다.")]
    items, _t, _p = ctx.api.pages("/api/tickets/team", project_id=project.get("id"), active="false", status="완료")
    keys = [t.get("key") for t in items if t.get("key")]
    mentioned = keys_mentioned(r.text, keys) + [k for k in shown_ticket_keys(r) + cited_ticket_keys(r) if k in keys]
    others = [k for k in KEY_RE.findall(r.text) + shown_ticket_keys(r) if k not in keys]
    # 「해결한 문제」는 제목이 아니라 내용을 묻는다 — 티켓 본문을 하나 이상 읽어야 한다(지시서 5.1 · 5.4).
    return [check("티켓 본문을 읽음", "get_ticket" in r.tool_names, ",".join(r.tool_names)),
            check("말한 키가 그 프로젝트의 완료 티켓", bool(mentioned) and not others,
                  f"맞음 {mentioned[:4]} 다름 {others[:4]}")]


def judge_d10(ctx: Ctx, r: Reply) -> list[Check]:
    items = _doc_items_of(r)
    out = [check("문서 검색", "search_documents" in r.tool_names, ",".join(r.tool_names))]
    out.append(check("문서가 있거나 정직하게 없음", bool(items) or not_found_phrase(r.text), f"{len(items)}건"))
    return out


def judge_e11(ctx: Ctx, r: Reply) -> list[Check]:
    project = project_by_code(ctx, ctx.project_code)
    if project is None:
        return [na("문서 + 진행 중 티켓", "프로젝트가 없습니다.")]
    docs = ctx.api.get_ok("/api/knowledge/documents", project_id=project.get("id"), limit=1)
    team = ctx.api.get_ok("/api/tickets/team", project_id=project.get("id"), active="true", page=1, page_size=1)
    n_docs, n_open = int(docs.get("total") or 0), int(team.get("total") or 0)
    ctx.memo["e11_items"] = _doc_items_of(r)
    out = [check("문서와 티켓 둘 다 찾음", "search_tickets" in r.tool_names and
                 any(n in r.tool_names for n in ("search_documents", "project_activity", "my_documents")),
                 ",".join(r.tool_names)),
           check("문서 수", number_in(r.text, n_docs) or (n_docs == 0 and says_none(r.text)) or bool(r.shown()),
                 f"진실 {n_docs}"),
           check("진행 중 티켓 수", number_in(r.text, n_open) or (n_open == 0 and says_none(r.text)) or bool(r.shown()),
                 f"진실 {n_open}")]
    if r.has_blocks_feature:
        kinds = {b.get("kind") for b in r.shown()}
        out.append(check("블록 둘(문서 · 티켓)", {"document", "ticket"} <= kinds, f"{sorted(k for k in kinds if k)}"))
    return out


def judge_e12(ctx: Ctx, r: Reply) -> list[Check]:
    items = ctx.memo.get("e11_items") or []
    if not items:
        return [na("첫 번째 문서", "앞 차례에 문서가 없었습니다.")]
    doc_id, title = items[0]
    linked = f"/knowledge/{doc_id}" in r.text or any(
        str(s.get("route") or "").startswith(f"/knowledge/{doc_id}") and (s.get("cited") or s.get("shown")) for s in r.sources)
    return [check("첫 번째 문서를 가리킴", linked or norm(title) in norm(r.text), title[:40])]


def judge_f13(ctx: Ctx, r: Reply) -> list[Check]:
    return [check("도구 없음", not r.tool_names, ",".join(r.tool_names)),
            check("블록 없음", not r.shown())]


def judge_g14(ctx: Ctx, r: Reply) -> list[Check]:
    return [check("보인 블록 없음", not r.shown()),
            check("찾지 못했다고 말함", not_found_phrase(r.text), r.text[:80]),
            check("찾아본 범위를 말함", searched_phrase(r.text) or bool(r.tool_names), ",".join(r.tool_names)),
            check("없다고 단정하지 않음", "존재하지 않" not in r.text)]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("A", "내 문서 · 다음 쪽", [
        Turn("내가 만든 문서", judge_a1),
        Turn("내가 작성한 문서는 몇 개야?", judge_a2),
        Turn("다음 10개 보여줘.", judge_a3),
    ]),
    Scenario("B", "내 문서 중 VMware", [
        Turn("내가 만든 문서 중 VMware 관련 문서 찾아줘.", judge_b4),
        Turn("그중 가장 최근 문서 내용을 요약해줘.", judge_b5),
    ]),
    Scenario("C", "내 티켓", [
        Turn("내가 담당하는 미완료 티켓 보여줘.", judge_c6),
        Turn("이번 주에 완료한 티켓은?", judge_c7),
    ]),
    Scenario("D", "프로젝트 현황 · 해결한 문제", [
        Turn(lambda ctx: f"{ctx.ambiguous} 프로젝트 진행 상황 알려줘." if ctx.ambiguous else None, judge_d8),
        Turn(question_d8b, judge_project_card),
        Turn("그 프로젝트에서 최근 해결한 문제는?", judge_d9),
        Turn("이 내용이 포함된 문서 리스트 찾아줘.", judge_d10),
    ]),
    Scenario("E", "프로젝트 문서와 티켓 · 첫 번째 문서", [
        Turn(lambda ctx: f"{ctx.project_code} 프로젝트의 문서와 진행 중인 티켓 함께 보여줘." if ctx.project_code else None,
             judge_e11),
        Turn("방금 찾은 문서 중 첫 번째 문서 열어줘.", judge_e12),
    ]),
    Scenario("F", "인사", [Turn("안녕.", judge_f13)]),
    Scenario("G", "자료로 확인할 수 없는 질문", [Turn("2031년 우주 출장 규정을 알려줘.", judge_g14)]),
)


# ── 실행 ──────────────────────────────────────────────────────────────────────


def reply_of(got: dict) -> Reply:
    if got.get("timeout"):
        return Reply(text="", structured={}, message_id=None, seconds=got.get("seconds"), failed=True)
    reply = got.get("reply") or {}
    st = reply.get("structured") if isinstance(reply.get("structured"), dict) else {}
    failed = (got.get("user") or {}).get("processing_status") == "failed" or bool(st.get("error_notice"))
    return Reply(text=str(reply.get("content") or ""), structured=st, message_id=reply.get("id"),
                 seconds=got.get("seconds"), failed=failed)


def turn_record(question: str, r: Reply, checks: list[Check]) -> dict:
    return {
        "question": question,
        "seconds": r.seconds,
        "failed": r.failed,
        "mode": r.structured.get("mode"),
        "notice": r.structured.get("notice"),
        "tools": [{k: t.get(k) for k in ("name", "count", "total", "query")} for t in r.tools],
        "blocks": [{"tool": b.get("tool"), "kind": b.get("kind"), "shown": b.get("shown"), "args": b.get("args"),
                    "total": b.get("total"), "offset": b.get("offset"), "returned": b.get("returned"),
                    "titles": block_titles(b)[:3]} for b in r.blocks],
        "sources": {"all": len(r.sources), "cited": sum(1 for s in r.sources if s.get("cited")),
                    "shown": sum(1 for s in r.sources if s.get("shown"))},
        "first_sentence": mask_emails(first_sentence(r.text))[:200],
        "answer": mask_emails(r.text[:EXCERPT_CHARS]),
        "length": len(r.text),
        "checks": [{"name": c.name, "status": c.status, "detail": mask_emails(c.detail)} for c in checks],
    }


def run_scenario(client, headers, ctx: Ctx, scenario: Scenario, *, stamp: str, timeout: float) -> dict:
    title = f"[AI검증] {scenario.key} {scenario.title} {stamp}"
    cid, body = create_conversation(client, headers, title)
    out = {"key": scenario.key, "title": scenario.title, "conversation": bool(cid), "turns": []}
    if not cid:
        out["error"] = f"대화를 만들지 못했습니다: {body.get('status')}"
        return out
    out["conversation_id"] = cid
    ctx.replies = []
    for turn in scenario.turns:
        question = turn.question(ctx) if callable(turn.question) else turn.question
        if not question:
            continue
        status, posted = post_question(client, headers, cid, question, prefix="aichat-")
        user_mid = ((posted or {}).get("message") or {}).get("message_id") if isinstance(posted, dict) else None
        if status != 202 or not user_mid:
            out["turns"].append({"question": question, "post_status": status,
                                 "checks": [{"name": "질문 보내기", "status": FAIL, "detail": f"상태 {status}"}]})
            break
        r = reply_of(await_reply(client, headers, cid, user_mid, timeout=timeout))
        ctx.replies.append(r)
        base = [check("답이 왔다", not r.failed and bool(r.text), f"{r.seconds}초"),
                check("도구 이름을 드러내지 않음", not leaked_tool_names(r.text), ",".join(leaked_tool_names(r.text)))]
        if r.tool_names:
            base.append(check("도구 모드", r.structured.get("mode") == "tools", str(r.structured.get("mode"))))
        try:
            checks = base + (turn.judge(ctx, r) if not r.failed else [])
        except TruthError as exc:
            checks = base + [Check("진실 API", FAIL, str(exc))]
        out["turns"].append(turn_record(question, r, checks))
        log(f"  {scenario.key} · {question} → " + " ".join(f"{c.status}" for c in checks))
    return out


def capture(base: str, verify, creds: dict, me: str, conversation_id: str, title: str, label: str) -> list[str]:
    """그 대화를 크기 · 테마마다 찍는다. 테마는 이 브라우저의 저장소에만 둔다(계정 설정은 건드리지 않는다)."""
    from playwright.sync_api import sync_playwright

    from scripts.ui_qa.capture import theme_init_script

    out_dir = LAB_SHOTS / label
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for theme in ("light", "dark"):
                for width, height, scale in SHOT_SIZES:
                    # 브라우저는 랩의 자체 서명 인증서를 모른다 — 화면만 찍는 쪽이라 검증을 끈다(API 쪽은 그대로 검증한다).
                    ctx = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=scale,
                                              ignore_https_errors=True, locale="ko-KR",
                                              timezone_id="Asia/Seoul", color_scheme=theme)
                    try:
                        ctx.add_init_script(theme_init_script(theme, me))
                        r = ctx.request.post(f"{base}/login", data={"email": creds["AI_TRUTH_EMAIL"],
                                                                    "password": creds["AI_TRUTH_PASSWORD"]})
                        if r.status != 200:
                            raise LoginError(r.status)
                        page = ctx.new_page()
                        page.goto(f"{base}/#/chat/{conversation_id}", wait_until="domcontentloaded")
                        page.wait_for_timeout(2500)
                        if not page.locator("main h2", has_text=title[:20]).count():
                            page.goto(f"{base}/#/chat", wait_until="domcontentloaded")
                            page.wait_for_timeout(1500)
                            opener = page.locator('[aria-label="대화 목록 열기"]:visible')
                            if opener.count():
                                opener.first.click()
                                page.wait_for_timeout(500)
                            page.get_by_text(title[:20]).first.click()
                        page.wait_for_timeout(3000)
                        name = f"chat-{width}x{height}{'@125' if scale != 1 else ''}-{theme}.png"
                        page.screenshot(path=str(out_dir / name))
                        saved.append(name)
                    finally:
                        ctx.close()
        finally:
            browser.close()
    return saved


RENDER_LEAKS = ("](/", "**", "](#")


def render_check(base: str, creds: dict, me: str, conversations: list[tuple[str, str]]) -> dict:
    """그린 화면에 마크다운 글자가 새지 않는가 — 대화마다 스레드의 글에 `](/` · `**` 가 없어야 한다(D-582).

    API 의 답 글에는 마크다운이 있는 것이 맞다. 화면이 그것을 링크 · 굵게 · 목록으로 그렸는지를 실브라우저에서 본다."""
    from playwright.sync_api import sync_playwright

    from scripts.ui_qa.capture import theme_init_script

    checks = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, ignore_https_errors=True, locale="ko-KR",
                                      timezone_id="Asia/Seoul")
            ctx.add_init_script(theme_init_script("light", me))
            r = ctx.request.post(f"{base}/login", data={"email": creds["AI_TRUTH_EMAIL"], "password": creds["AI_TRUTH_PASSWORD"]})
            if r.status != 200:
                raise LoginError(r.status)
            page = ctx.new_page()
            for key, conversation_id in conversations:
                page.goto(f"{base}/#/chat/{conversation_id}", wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                text = page.evaluate("() => (document.querySelector('section[aria-label=\"대화\"]') || document.body).innerText")
                leaks = [m for m in RENDER_LEAKS if m in text]
                links = page.locator('section[aria-label="대화"] [data-message-role="assistant"] a[href^="#/"]').count()
                c = check(f"{key} 그린 화면에 마크다운 글자가 없다", not leaks, f"새어 나온 표시 {leaks} · 답 안 링크 {links}개")
                checks.append({"name": c.name, "status": c.status, "detail": c.detail})
            ctx.close()
        finally:
            browser.close()
    return {"key": "R", "title": "그린 화면", "turns": [{"question": "(화면 확인)", "checks": checks}]}


def render_md(report: dict) -> str:
    lines = [f"# AI 도우미 대화 하네스 — {report['label']}", "",
             f"- 대상: {report['base']} · 시각 {report['started']} · {report['summary']}", ""]
    for sc in report["scenarios"]:
        lines.append(f"## {sc['key']} {sc['title']}")
        for t in sc.get("turns", []):
            lines.append(f"- **{t['question']}** ({t.get('seconds')}초, 도구 {[x['name'] for x in t.get('tools', [])]})")
            lines.append(f"  - 첫 문장: {t.get('first_sentence', '')}")
            for c in t.get("checks", []):
                lines.append(f"  - {c['status']} {c['name']} — {c['detail']}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    utf8_console()
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--env-file", default=str(ROOT / "dist" / "ops" / "user.env"))
    ap.add_argument("--cacert")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--label", default="chat")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--project-code")
    ap.add_argument("--ambiguous-project")
    args = ap.parse_args(argv)

    creds = read_env_file(args.env_file, ENV_KEYS)
    if not all(creds.get(k) for k in ENV_KEYS):
        log("자격이 없습니다 — env 파일에 AI_TRUTH_EMAIL · AI_TRUTH_PASSWORD 가 있어야 합니다.")
        return 2
    verify = resolve_verify(args.base, cacert=args.cacert, insecure=args.insecure)
    client = make_client(args.base, verify=verify, timeout=120)
    try:
        headers = login(client, creds["AI_TRUTH_EMAIL"], creds["AI_TRUTH_PASSWORD"])
    except LoginError as exc:
        log(str(exc))
        return 2
    me = ((json_of(client.get("/api/me", headers=headers)) or {}).get("user") or {}).get("id") or ""
    api = Api(client, headers)
    only = {s.upper() for s in (args.only or [])}
    stamp = datetime.now(KST).strftime("%m%d-%H%M")
    report = {"label": args.label, "base": args.base, "started": datetime.now(KST).isoformat(timespec="seconds"),
              "scenarios": []}
    made: list[str] = []
    shots: list[str] = []
    try:
        for scenario in SCENARIOS:
            if only and scenario.key not in only:
                continue
            ctx = Ctx(api=api, me=str(me), project_code=args.project_code, ambiguous=args.ambiguous_project)
            log(f"{scenario.key} {scenario.title}")
            result = run_scenario(client, headers, ctx, scenario, stamp=stamp, timeout=args.timeout)
            report["scenarios"].append(result)
            if result.get("conversation_id"):
                made.append(result["conversation_id"])
        if args.capture:
            first = next((s for s in report["scenarios"] if s.get("conversation_id")), None)
            if first:
                title = f"[AI검증] {first['key']} {first['title']} {stamp}"
                try:
                    shots = capture(args.base, verify, creds, str(me), first["conversation_id"], title, args.label)
                except Exception as exc:  # noqa: BLE001 - 캡처가 실패해도 판정 기록은 남긴다
                    report["capture_error"] = str(exc).splitlines()[0][:300]
            pairs = [(s["key"], s["conversation_id"]) for s in report["scenarios"] if s.get("conversation_id")]
            if pairs:
                try:
                    report["scenarios"].append(render_check(args.base, creds, str(me), pairs))
                except Exception as exc:  # noqa: BLE001 - 화면 확인이 끊겨도 판정 기록은 남긴다
                    report["render_error"] = str(exc).splitlines()[0][:300]
    finally:
        if not args.keep:
            report["deleted"] = [delete_conversation(client, headers, cid) for cid in made]
        client.post("/logout", headers=headers)
    counts = {PASS: 0, FAIL: 0, NA: 0}
    for sc in report["scenarios"]:
        for t in sc.get("turns", []):
            for c in t.get("checks", []):
                counts[c["status"]] = counts.get(c["status"], 0) + 1
    report["shots"] = shots
    report["summary"] = f"pass={counts[PASS]} fail={counts[FAIL]} na={counts[NA]}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{args.label}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8",
                                                newline="\n")
    (OUT_DIR / f"{args.label}.md").write_text(render_md(report), encoding="utf-8", newline="\n")
    verdict = "OK" if counts[FAIL] == 0 else "FAILED"
    log(f"AI_CHAT_E2E {verdict} {report['summary']} → {OUT_DIR / (args.label + '.md')}")
    return 0 if counts[FAIL] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
