"""AI 연결 · 채팅 실측 (기능 개선 회차 P3 ⑥) — 랩이든 로컬이든 **같은 API** 로 「인증 · 모델 조회 · 모델 선택 · 일반 대화 · 문서 검색」을 각각 따로 잰다.

- 아무것도 고치지 않는다. 설정을 바꾸지 않고, 만든 대화는 끝에 지운다(`--keep` 이면 남긴다).
- 비밀은 명령행에 받지 않는다. QA 계정 비밀번호는 환경 변수 `UI_QA_PASSWORD`(이메일은 `UI_QA_EMAIL`, 기본 ui-qa@goodmit.co.kr)다.
  결과 파일에 토큰 · 키 · 비밀번호 · 이메일 주소를 적지 않는다(이메일은 가린다).
- TLS 는 검증한다. 신뢰 기준점은 `UI_QA_TLS_CA`(없으면 `dist/ops/<DNS 이름>.crt`, 그것도 없으면 시스템 기준점)다.
- 「자격 저장」 · 「모델 목록」 · 「실제 답」 · 「문서 검색」 을 섞지 않는다(계획 4절) — 각 줄이 따로 PASS · FAIL · 미측정이다.

    UI_QA_PASSWORD=… python -m scripts.ui_qa.ai_lab_e2e                      # 랩(기본 대상은 `capture.DEFAULT_BASE_URL`)
    UI_QA_PASSWORD=… python -m scripts.ui_qa.ai_lab_e2e --base http://127.0.0.1:8765 --label local
    … --skip-chat    # 연결 상태만 본다(채팅을 보내지 않는다)

결과: dist/ui-qa/ai-lab-e2e/<label>.json · <label>.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def mask_emails(text: str) -> str:
    def one(m):
        local, _, domain = m.group(0).partition("@")
        return f"{local[:1]}****{local[-1:]}@{domain}"
    return EMAIL_RE.sub(one, text or "")


def _ca_path(base: str) -> str | bool:
    env = os.environ.get("UI_QA_TLS_CA")
    if env:
        return env
    host = urlsplit(base).hostname or ""
    candidate = ROOT / "dist" / "ops" / f"{host}.crt"
    return str(candidate) if candidate.exists() else True


def log(msg: str) -> None:
    print(msg, flush=True)


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


def _json(res: httpx.Response):
    try:
        return res.json()
    except ValueError:
        return {"__text__": (res.text or "")[:300]}


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


def _await_reply(client: httpx.Client, headers: dict, conversation_id: str, user_message_id: str, *, timeout: float) -> dict:
    started = time.monotonic()
    last = None
    while time.monotonic() - started < timeout:
        time.sleep(1.5)
        r = client.get(f"/api/conversations/{conversation_id}/messages", headers=headers)
        if r.status_code != 200:
            last = {"status": r.status_code}
            continue
        items = (_json(r).get("items") or [])
        mine = next((m for m in items if m.get("message_id") == user_message_id), None)
        if mine is None:
            continue
        reply = next((m for m in items if m.get("role") == "assistant" and str(m.get("message_id", "")).startswith(f"a-{user_message_id}")), None)
        if mine.get("processing_status") in ("done", "failed") and reply is not None:
            return {"user": mine, "reply": reply, "seconds": round(time.monotonic() - started, 1)}
        last = {"processing_status": mine.get("processing_status")}
    return {"timeout": True, "last": last, "seconds": round(time.monotonic() - started, 1)}


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
    c = client.post("/api/conversations", json={"title": f"AI 실측 {run.started:%m-%d %H:%M}"}, headers=headers)
    if c.status_code != 201:
        run.row("chat", "FAIL", {"create_status": c.status_code, "body": _json(c)})
        return
    conversation_id = (_json(c).get("conversation") or {}).get("id") or _json(c).get("id")
    try:
        for key, template in QUESTIONS:
            question = template.format(ticket=ticket)
            client_message_id = "ailab-" + uuid.uuid4().hex[:16]
            p = client.post(f"/api/conversations/{conversation_id}/messages",
                            json={"content": question, "client_message_id": client_message_id}, headers=headers, timeout=60)
            if p.status_code != 202:
                run.chat.append({"key": key, "question": question, "verdict": "FAIL", "post_status": p.status_code, "body": _json(p)})
                log(f"[  FAIL  ] chat.{key}: POST {p.status_code}")
                continue
            user_message_id = _json(p)["message"]["message_id"]
            got = _await_reply(client, headers, conversation_id, user_message_id, timeout=timeout)
            if got.get("timeout"):
                run.chat.append({"key": key, "question": question, "verdict": "FAIL", "timeout_seconds": got["seconds"], "last": got.get("last")})
                log(f"[  FAIL  ] chat.{key}: {got['seconds']}초 안에 답이 없다")
                continue
            reply = got["reply"]
            st = reply.get("structured") or {}
            ok = got["user"].get("processing_status") == "done" and not st.get("error_notice")
            entry = {
                "key": key, "question": question, "verdict": "PASS" if ok else "FAIL",
                "seconds": got["seconds"], "status": st.get("status"), "mode": st.get("mode"), "notice": st.get("notice"),
                "rounds": st.get("rounds"), "elapsed_ms": st.get("elapsed_ms"), "model": st.get("model"),
                "sources": len(st.get("sources") or []), "tools": [t.get("name") for t in st.get("tools") or []],
                "error_code": got["user"].get("error_code"),
                "answer_head": mask_emails((reply.get("content") or "")[:240]),
            }
            run.chat.append(entry)
            log(f"[{entry['verdict']:^8}] chat.{key}: {entry['seconds']}s mode={entry['mode']} notice={entry['notice']} "
                f"sources={entry['sources']} → {entry['answer_head'][:80]!r}")
    finally:
        if not keep:
            d = client.delete(f"/api/conversations/{conversation_id}", headers=headers)
            run.notes.append(f"대화 삭제 {d.status_code}")
        else:
            run.notes.append(f"대화 남김 {conversation_id}")


def write_results(run: Run, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"base": run.base, "label": run.label, "started_at": run.started.isoformat(), "rows": run.rows, "chat": run.chat,
            "notes": run.notes}
    (out_dir / f"{run.label}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# AI 실측 — {run.label} ({run.base})", "", f"시작: {run.started:%Y-%m-%d %H:%M} UTC", "",
             "| 항목 | 판정 | 내용 |", "|---|---|---|"]
    for r in run.rows:
        lines.append(f"| {r['key']} | {r['verdict']} | {json.dumps(r['detail'], ensure_ascii=False)[:200].replace('|', '/')} |")
    if run.chat:
        lines += ["", "| 질문 | 판정 | 초 | mode | notice | 출처 | 도구 | 답(앞부분) |", "|---|---|---|---|---|---|---|---|"]
        for c in run.chat:
            lines.append(f"| {c['question']} | {c['verdict']} | {c.get('seconds', '')} | {c.get('mode', '')} | {c.get('notice') or ''} | "
                         f"{c.get('sources', '')} | {','.join(c.get('tools') or [])} | {(c.get('answer_head') or '').replace('|', '/').replace(chr(10), ' ')[:120]} |")
    if run.notes:
        lines += ["", *[f"- {n}" for n in run.notes]]
    path = out_dir / f"{run.label}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--label", default=None, help="결과 파일 이름(기본: 호스트 이름)")
    parser.add_argument("--timeout", type=float, default=150.0, help="질문 하나의 답을 기다리는 초")
    parser.add_argument("--skip-chat", action="store_true")
    parser.add_argument("--keep", action="store_true", help="만든 대화를 지우지 않는다")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    password = os.environ.get("UI_QA_PASSWORD")
    if not password:
        print("UI_QA_PASSWORD 가 없습니다(환경 변수로만 받는다).", file=sys.stderr)
        return 2
    email = os.environ.get("UI_QA_EMAIL", "ui-qa@goodmit.co.kr")
    label = args.label or (urlsplit(args.base).hostname or "lab").replace(".", "-")
    run = Run(args.base, label)
    client = httpx.Client(base_url=args.base, timeout=90, verify=_ca_path(args.base))
    r = client.post("/login", json={"email": email, "password": password})
    if r.status_code != 200:
        print(f"로그인 실패 {r.status_code}", file=sys.stderr)
        return 2
    headers = {"X-CSRF-Token": r.json()["csrf_token"]}
    measure_connection(client, headers, run)
    if not args.skip_chat:
        measure_chat(client, headers, run, timeout=args.timeout, keep=args.keep)
    path = write_results(run, Path(args.out))
    failed = [r for r in run.rows if r["verdict"] == "FAIL"] + [c for c in run.chat if c["verdict"] == "FAIL"]
    log(f"AI_LAB_E2E {'OK' if not failed else 'FAILED'} rows={len(run.rows)} chat={len(run.chat)} failed={len(failed)} → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
