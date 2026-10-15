"""AI 연결 · 채팅 실측 (기능 개선 회차 P3 ⑥) — 랩이든 로컬이든 **같은 API** 로 「인증 · 모델 조회 · 모델 선택 · 일반 대화 · 문서 검색」을 각각 따로 잰다.

- 아무것도 고치지 않는다. 설정을 바꾸지 않고, 만든 대화는 끝에 지운다(`--keep` 이면 남긴다).
- 비밀은 명령행에 받지 않는다. QA 계정 비밀번호는 환경 변수 `UI_QA_PASSWORD`(이메일은 `UI_QA_EMAIL`, 기본 ui-qa@goodmit.co.kr)다.
  결과 파일에 토큰 · 키 · 비밀번호 · 이메일 주소를 적지 않는다(이메일은 가린다).
- TLS 는 검증한다. 신뢰 기준점은 `--cacert` → `UI_QA_TLS_CA` → `dist/ops/<DNS 이름>.crt` → 시스템 기준점 순서다. `--insecure` 는
  검증을 끄고 그 사실을 결과에 적는다.
- 「자격 저장」 · 「모델 목록」 · 「실제 답」 · 「문서 검색」 을 섞지 않는다(계획 4절) — 각 줄이 따로 PASS · FAIL · 미측정이다.
- 대체 모드는 실패다(A9): 답이 `mode == search_only`(도구 없이 서버가 먼저 찾은 자료로만 답함)이면 그 질문은 FAIL 이고, 연결 면의
  `capabilities.tools == unsupported`(모델이 도구를 거절함)도 FAIL 줄이다. 요약 줄에 대체 모드 답의 수를 함께 찍는다.
- 로그인 · 질문 보내기 · 답 기다리기는 `ai_lab_common.py` 와 진실 하네스(`ai_truth_e2e.py`)가 함께 쓴다.

    UI_QA_PASSWORD=… python -m scripts.ui_qa.ai_lab_e2e                      # 랩(기본 대상은 `capture.DEFAULT_BASE_URL`)
    UI_QA_PASSWORD=… python -m scripts.ui_qa.ai_lab_e2e --base http://127.0.0.1:8765 --label local
    … --skip-chat    # 연결 상태만 본다(채팅을 보내지 않는다)

결과: dist/ui-qa/ai-lab-e2e/<label>.json · <label>.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
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
    resolve_verify,
    utf8_console,
)
from scripts.ui_qa.capture import DEFAULT_BASE_URL as DEFAULT_BASE  # noqa: E402 - 대상 호스트는 한 곳이 정한다

OUT_DIR = ROOT / "dist" / "ui-qa" / "ai-lab-e2e"

#: 채팅 열한 가지(지난 계획 A1 표). 다섯째는 실제 티켓 키로 바꿔 묻는다.
QUESTIONS = [
    ("hello", "안녕"),
    ("date", "오늘 날짜가 뭐야?"),
    ("sla", "SLA 가 뭐야?"),
    ("my_due", "이번 주 마감인 내 티켓을 알려 줘"),
    ("ticket_status", "{ticket} 지금 어떻게 됐어?"),
    ("project", "내 프로젝트 진행 상황을 알려 줘"),
    ("approvals", "내가 결재할 거 있어?"),
    ("docs_changed", "이번 주에 바뀐 문서가 뭐야?"),
    ("team_members", "플랫폼개발팀에 누가 있어?"),
    ("leave_howto", "연차 신청은 어떻게 하나요?"),
    ("missing_doc", "2031년 우주 출장 규정을 알려 줘"),
]

#: 대체 모드(도구 없이 답함). 이 모드의 답은 실패다(A9).
MODE_SEARCH_ONLY = "search_only"


class Run:
    def __init__(self, base: str, label: str) -> None:
        self.base = base
        self.label = label
        self.started = datetime.now(timezone.utc)
        self.rows: list[dict] = []
        self.chat: list[dict] = []
        self.notes: list[str] = []

    def row(self, key: str, verdict: str, detail) -> None:
        self.rows.append({"key": key, "verdict": verdict, "detail": detail})
        log(f"[{verdict:^8}] {key}: {json.dumps(detail, ensure_ascii=False)[:300]}")

    @property
    def fallback_answers(self) -> int:
        """대체 모드로 끝난 답의 수."""
        return sum(1 for c in self.chat if c.get("mode") == MODE_SEARCH_ONLY)


# 옛 이름 — 이 파일 안의 호출부가 쓰던 이름을 그대로 둔다.
_json = json_of


def _public_overview(body: dict) -> dict:
    """화면이 받는 값에서 결과 파일에 적을 것만 — 비밀 끝자리 · 계정 주소는 뺀다."""
    state = body.get("state") or {}
    providers = []
    for p in body.get("providers") or []:
        providers.append({"key": p.get("key"),
                          "auth_methods": [{"key": m.get("key"), "ready": m.get("ready")} for m in p.get("auth_methods") or []]})
    creds = dict(body.get("credentials") or {})
    creds.pop("account_label", None)
    return {
        "config": {k: (body.get("config") or {}).get(k) for k in ("generation_enabled", "provider", "auth_method", "model")},
        "state": state.get("state"),
        "display": state.get("display"),
        "verifying": state.get("verifying"),
        "credentials": creds,
        "facts": [f.get("key") for f in body.get("facts") or []],
        "next": body.get("next"),
        "login_open": (body.get("login") or {}).get("open"),
        "providers": providers,
        "capabilities": body.get("capabilities"),
        "index": body.get("index"),
    }


def tools_verdict(capabilities) -> str:
    """연결 면의 도구 호출 능력 → 판정. 모델이 도구를 거절하면(`unsupported`) 실패다(A9), 아직 안 쟀으면 미측정이다."""
    tools = (capabilities or {}).get("tools") if isinstance(capabilities, dict) else None
    if tools == "ok":
        return "PASS"
    if tools == "unsupported":
        return "FAIL"
    return "SKIPPED"


def chat_verdict(user_message: dict, structured: dict) -> str:
    """질문 하나의 판정. 처리 실패 · 오류 안내 · 대체 모드(`search_only`)는 실패다."""
    if (user_message or {}).get("processing_status") != "done":
        return "FAIL"
    st = structured or {}
    if st.get("error_notice"):
        return "FAIL"
    if st.get("mode") == MODE_SEARCH_ONLY:
        return "FAIL"
    return "PASS"


def measure_connection(client: httpx.Client, headers: dict, run: Run) -> dict:
    r = client.get("/api/admin/ai", headers=headers)
    if r.status_code != 200:
        run.row("overview", "FAIL", {"status": r.status_code})
        return {}
    body = _json(r)
    shown = _public_overview(body)
    run.row("overview", "PASS", shown)
    creds = shown["credentials"]
    display = (shown.get("display") or {}).get("key")
    run.row("auth.credentials", "PASS" if creds.get("ready") else "FAIL",
            {"ready": creds.get("ready"), "method": creds.get("method"), "display": display, "next": shown.get("next")})
    # 모델 조회는 자격이 있을 때만 뜻이 있다 — 없으면 미측정이다.
    config = shown["config"]
    if creds.get("ready") and config.get("provider") and config.get("auth_method"):
        m = client.get("/api/admin/ai/models", params={"provider": config["provider"], "auth_method": config["auth_method"]},
                       headers=headers, timeout=120)
        mbody = _json(m)
        ids = [x.get("id") for x in (mbody.get("models") or [])] if isinstance(mbody, dict) else []
        run.row("models.list", "PASS" if m.status_code == 200 and ids else "FAIL",
                {"status": m.status_code, "count": len(ids), "recommended": mbody.get("recommended_id") if isinstance(mbody, dict) else None,
                 "chosen_in_list": config.get("model") in ids, "error": None if m.status_code == 200 else mbody})
    else:
        run.row("models.list", "SKIPPED", {"why": "자격이 없다"})
    run.row("model.chosen", "PASS" if config.get("model") else "FAIL", {"model": config.get("model")})
    run.row("state", "PASS" if display in ("ok", "unverified", "verifying") else ("FAIL" if display else "SKIPPED"),
            {"display": shown.get("display"), "generation_enabled": config.get("generation_enabled")})
    # 도구 호출 능력(A9) — 거절하면 도우미는 대체 모드로만 답한다.
    caps = shown.get("capabilities") or {}
    run.row("capabilities.tools", tools_verdict(caps),
            {"tools": caps.get("tools") if isinstance(caps, dict) else None,
             "checked_at": caps.get("checked_at") if isinstance(caps, dict) else None})
    return shown


def _first_ticket_key(client: httpx.Client, headers: dict) -> str:
    try:
        r = client.get("/api/tickets", params={"limit": 5}, headers=headers)
        body = _json(r)
        items = body.get("items") if isinstance(body, dict) else None
        for item in items or []:
            key = item.get("key") or item.get("canonical_key")
            if key:
                return str(key)
    except Exception:  # noqa: BLE001 - 티켓이 없으면 가짜 키로 묻는다(「찾지 못함」 갈래)
        pass
    return "ABC-1"


def measure_chat(client: httpx.Client, headers: dict, run: Run, *, timeout: float, keep: bool) -> None:
    s = client.get("/api/ai/status", headers=headers)
    status = _json(s)
    assistant = status.get("assistant") if isinstance(status, dict) else None
    run.row("assistant.status", "PASS" if assistant and assistant.get("available") else "FAIL",
            {"status": s.status_code, "assistant": assistant})
    if not (assistant and assistant.get("available")):
        run.row("chat", "SKIPPED", {"why": "도우미를 쓸 수 없다", "reason": (assistant or {}).get("reason")})
        return
    ticket = _first_ticket_key(client, headers)
    conversation_id, created = create_conversation(client, headers, f"AI 실측 {run.started:%m-%d %H:%M}")
    if conversation_id is None:
        run.row("chat", "FAIL", {"create_status": created.get("status"), "body": created.get("body")})
        return
    try:
        for key, template in QUESTIONS:
            question = template.format(ticket=ticket)
            status_code, posted = post_question(client, headers, conversation_id, question, prefix="ailab-")
            if status_code != 202:
                run.chat.append({"key": key, "question": question, "verdict": "FAIL", "post_status": status_code, "body": posted})
                log(f"[  FAIL  ] chat.{key}: POST {status_code}")
                continue
            user_message_id = posted["message"]["message_id"]
            got = await_reply(client, headers, conversation_id, user_message_id, timeout=timeout)
            if got.get("timeout"):
                run.chat.append({"key": key, "question": question, "verdict": "FAIL", "timeout_seconds": got["seconds"], "last": got.get("last")})
                log(f"[  FAIL  ] chat.{key}: {got['seconds']}초 안에 답이 없다")
                continue
            reply = got["reply"]
            st = reply.get("structured") or {}
            entry = {
                "key": key, "question": question, "verdict": chat_verdict(got["user"], st),
                "seconds": got["seconds"], "status": st.get("status"), "mode": st.get("mode"), "notice": st.get("notice"),
                "rounds": st.get("rounds"), "elapsed_ms": st.get("elapsed_ms"), "model": st.get("model"),
                "sources": len(st.get("sources") or []), "tools": [t.get("name") for t in st.get("tools") or []],
                "error_code": got["user"].get("error_code"),
                "answer_head": mask_emails((reply.get("content") or "")[:240]),
            }
            if st.get("mode") == MODE_SEARCH_ONLY:
                entry["why"] = "도구 없이 대체 모드로 답했습니다."
            run.chat.append(entry)
            log(f"[{entry['verdict']:^8}] chat.{key}: {entry['seconds']}s mode={entry['mode']} notice={entry['notice']} "
                f"sources={entry['sources']} → {entry['answer_head'][:80]!r}")
    finally:
        if not keep:
            run.notes.append(f"대화 삭제 {delete_conversation(client, headers, conversation_id)}")
        else:
            run.notes.append(f"대화 남김 {conversation_id}")


def write_results(run: Run, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"base": run.base, "label": run.label, "started_at": run.started.isoformat(), "rows": run.rows, "chat": run.chat,
            "fallback_answers": run.fallback_answers, "notes": run.notes}
    (out_dir / f"{run.label}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    lines = [f"# AI 실측 — {run.label} ({run.base})", "", f"시작: {run.started:%Y-%m-%d %H:%M} UTC", "",
             "| 항목 | 판정 | 내용 |", "|---|---|---|"]
    for r in run.rows:
        lines.append(f"| {r['key']} | {r['verdict']} | {json.dumps(r['detail'], ensure_ascii=False)[:200].replace('|', '/')} |")
    if run.chat:
        lines += ["", "| 질문 | 판정 | 초 | mode | notice | 출처 | 도구 | 답(앞부분) |", "|---|---|---|---|---|---|---|---|"]
        for c in run.chat:
            lines.append(f"| {c['question']} | {c['verdict']} | {c.get('seconds', '')} | {c.get('mode', '')} | {c.get('notice') or ''} | "
                         f"{c.get('sources', '')} | {','.join(c.get('tools') or [])} | {(c.get('answer_head') or '').replace('|', '/').replace(chr(10), ' ')[:120]} |")
        lines += ["", f"대체 모드(search_only) 답: {run.fallback_answers}건"]
    if run.notes:
        lines += ["", *[f"- {n}" for n in run.notes]]
    path = out_dir / f"{run.label}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--label", default=None, help="결과 파일 이름(기본: 호스트 이름)")
    parser.add_argument("--timeout", type=float, default=150.0, help="질문 하나의 답을 기다리는 초")
    parser.add_argument("--skip-chat", action="store_true")
    parser.add_argument("--keep", action="store_true", help="만든 대화를 지우지 않는다")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--cacert", default=None, help="TLS 기준점 파일(자가 서명 인증서)")
    parser.add_argument("--insecure", action="store_true", help="TLS 검증을 끈다(결과에 그 사실을 적는다)")
    args = parser.parse_args(argv)

    password = os.environ.get("UI_QA_PASSWORD")
    if not password:
        print("UI_QA_PASSWORD 가 없습니다(환경 변수로만 받는다).", file=sys.stderr)
        return 2
    email = os.environ.get("UI_QA_EMAIL", "ui-qa@goodmit.co.kr")
    label = args.label or (urlsplit(args.base).hostname or "lab").replace(".", "-")
    run = Run(args.base, label)
    if args.insecure:
        run.notes.append("TLS 검증을 끄고 쟀습니다(--insecure).")
    client = make_client(args.base, verify=resolve_verify(args.base, cacert=args.cacert, insecure=args.insecure))
    try:
        headers = login(client, email, password)
    except LoginError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    measure_connection(client, headers, run)
    if not args.skip_chat:
        measure_chat(client, headers, run, timeout=args.timeout, keep=args.keep)
    path = write_results(run, Path(args.out))
    failed = [r for r in run.rows if r["verdict"] == "FAIL"] + [c for c in run.chat if c["verdict"] == "FAIL"]
    log(f"AI_LAB_E2E {'OK' if not failed else 'FAILED'} rows={len(run.rows)} chat={len(run.chat)} failed={len(failed)} "
        f"fallback={run.fallback_answers} → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
