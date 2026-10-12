"""랩 메일 E2E-3 (계획 M5 · P18) — ClovirAssist 로컬 릴레이(인터넷으로 직접 전달)로 실제 받는 주소에 시험 메일을 보내고 단계를 잰다.

조사 · 실측 전용이다(제품 코드가 아니다). 화면이 부르는 것과 같은 API 를 시스템 관리자 QA 계정으로 부른다.

- 비밀은 명령행에 받지 않는다. QA 계정 비밀번호는 환경 변수 `UI_QA_PASSWORD`(이메일은 `UI_QA_EMAIL`, 기본 ui-qa@goodmit.co.kr)다.
- 받는 주소는 `--to` 인자로만 받는다. 저장소 파일 · 결과 파일 · 출력에는 가린 꼴(`h****g@goodmit.co.kr`)만 남긴다.
- TLS 는 검증한다. 신뢰 기준점은 `UI_QA_TLS_CA`(없으면 `dist/ops/<DNS 이름>.crt`)다.

단계(계획 M5 「단계를 섞지 않는다」, D-555):
  1 로컬 릴레이 구성 요소 상태(설치됨 · 꺼짐이면 「준비됨」)
  2 보내는 방법을 로컬 릴레이 · 인터넷으로 직접 전달로 저장(받는 도메인별 전달 서버 포함)
  3 릴레이 켜기(헬퍼 apply) → 앱 → 릴레이 연결 확인
  4 준비 점검(바깥 25번 · MX · SPF · DKIM · DMARC · PTR …)을 행마다 기록
  5 시험 메일 → 발송 기록이 「로컬 릴레이가 접수함」 → 바깥 전달 결과(수신측 메일 서버로 전달함 · 재시도 · 거부 · 만료)

받은 편지함 확인은 사람이 한다(⑥). 이 스크립트는 ③ · ④ 까지 잰다.

    UI_QA_PASSWORD=… python -m scripts.ui_qa.lab_mail_e2e --to <받는 주소> \\
        --override goodmit.co.kr=goodmit-co-kr.mail.protection.outlook.com --helo <서버 이름>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_qa.capture import DEFAULT_BASE_URL  # noqa: E402

OUT = ROOT / "dist" / "ui-qa" / "lab-mail-e2e"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def mask(address: str) -> str:
    local, _, domain = address.partition("@")
    if len(local) <= 2:
        hidden = local[:1] + "*"
    else:
        hidden = local[0] + "*" * (len(local) - 2) + local[-1]
    return hidden + "@" + domain


def scrub(value, secret: str):
    """결과에 받는 주소가 그대로 남지 않게 — 문자열 안의 그 주소를 가린 꼴로 바꾼다."""
    if isinstance(value, str):
        return value.replace(secret, mask(secret)) if secret else value
    if isinstance(value, list):
        return [scrub(v, secret) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v, secret) for k, v in value.items()}
    return value


class Run:
    def __init__(self, secret: str) -> None:
        self.rows: list[dict] = []
        self.secret = secret

    def check(self, step: str, ok: bool, detail="") -> bool:
        detail = scrub(detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False), self.secret)
        self.rows.append({"step": step, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + step + (f" — {detail}" if detail else ""), flush=True)
        return ok

    def info(self, step: str, detail="") -> None:
        detail = scrub(detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False), self.secret)
        self.rows.append({"step": step, "ok": None, "detail": detail})
        print("INFO " + step + (f" — {detail}" if detail else ""), flush=True)


def _ca_path(base: str) -> str | bool:
    env = os.environ.get("UI_QA_TLS_CA")
    if env:
        return env
    host = base.split("//", 1)[-1].split("/", 1)[0]
    candidate = ROOT / "dist" / "ops" / f"{host}.crt"
    return str(candidate) if candidate.is_file() else True


def _poll(fn, *, timeout: float, every: float = 2.0):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = fn()
        if last is not None:
            return last
        time.sleep(every)
    return None


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default=DEFAULT_BASE_URL)
    ap.add_argument("--to", required=True, help="실제 받는 주소(출력 · 결과에는 가린 꼴만 남는다)")
    ap.add_argument("--probe-domain", default="", help="준비 점검이 시험할 받는 도메인(기본: 받는 주소의 도메인)")
    ap.add_argument("--override", action="append", default=[], help="받는 도메인별 전달 서버 domain=host (여러 번)")
    ap.add_argument("--helo", default="", help="서버 이름(HELO). 비우면 저장된 값을 쓴다")
    ap.add_argument("--from-address", default="", help="보내는 주소. 비우면 저장된 값을 쓴다")
    ap.add_argument("--compare-resolver", action="append", default=[], help="비교할 공개 DNS 서버(여러 번)")
    ap.add_argument("--dkim", action="store_true",
                    help="DKIM 키가 없으면 서버에서 만들고(개인키는 서버 밖으로 안 나온다) 서명을 켠 채 저장한다")
    ap.add_argument("--wait-outer", type=float, default=300.0, help="바깥 전달 결과를 기다릴 초")
    ap.add_argument("--skip-send", action="store_true", help="시험 메일은 보내지 않는다(준비 점검까지만)")
    ap.add_argument("--track", default="", help="이미 보낸 발송 기록 id 하나만 다시 추적한다(설정 · 켜기 · 점검 · 발송 없음)")
    args = ap.parse_args()

    import httpx

    to = args.to.strip()
    if not EMAIL_RE.fullmatch(to):
        print("받는 주소 모양이 아닙니다.", file=sys.stderr)
        return 2
    password = os.environ.get("UI_QA_PASSWORD")
    if not password:
        print("UI_QA_PASSWORD 가 없습니다(환경 변수로만 받는다).", file=sys.stderr)
        return 2
    email = os.environ.get("UI_QA_EMAIL", "ui-qa@goodmit.co.kr")
    run = Run(to)
    OUT.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(base_url=args.base, timeout=90, verify=_ca_path(args.base))
    r = client.post("/login", json={"email": email, "password": password})
    if not run.check("로그인(시스템 관리자 QA 계정)", r.status_code == 200, f"HTTP {r.status_code}"):
        return _finish(run, 1)
    headers = {"X-CSRF-Token": r.json()["csrf_token"]}

    def detail(did: str) -> dict:
        # 상세 응답은 `{"delivery": {...}}` 로 감싸 온다.
        body = client.get(f"/api/admin/mail/deliveries/{did}").json()
        return body.get("delivery") or body

    if args.track:
        return _track(run, detail, args.track, args.wait_outer)

    # 1 구성 요소
    relay = client.get("/api/admin/mail/relay").json()
    comp = (relay.get("component") or {})
    run.check("로컬 릴레이 구성 요소가 설치돼 있다", comp.get("state") in ("ready", "running", "stopped"),
              {"state": comp.get("state"), "label": comp.get("label")})

    # 2 보내는 방법 저장
    current = client.get("/api/admin/mail/settings").json()["settings"]
    relay_cfg = dict(current.get("relay") or {})
    overrides = []
    for item in args.override:
        domain, _, host = item.partition("=")
        if domain and host:
            overrides.append({"domain": domain.strip().lower(), "host": host.strip().lower()})
    relay_body = {
        "delivery": "direct",
        "smarthost": relay_cfg.get("smarthost") or {"host": "", "port": 587, "security": "starttls", "username": ""},
        "helo_name": args.helo or relay_cfg.get("helo_name") or "",
        "public_ip": relay_cfg.get("public_ip") or "",
        "ipv4_only": True,
        "dkim_enabled": bool(relay_cfg.get("dkim_enabled")),
        "dkim_selector": relay_cfg.get("dkim_selector") or "",
        "transport_overrides": overrides or relay_cfg.get("transport_overrides") or [],
        "compare_resolvers": args.compare_resolver or relay_cfg.get("compare_resolvers") or [],
    }
    body = {
        "enabled": True, "mode": "local_relay",
        "host": current.get("host") or "", "port": current.get("port") or 587, "security": current.get("security") or "starttls",
        "from_address": args.from_address or current.get("from_address") or "",
        "from_name": current.get("from_name") or "ClovirAssist", "username": current.get("username") or "",
        "timeout_seconds": current.get("timeout_seconds") or 20, "tls_verify": bool(current.get("tls_verify", True)),
        "ca_pem": current.get("ca_pem") or "", "relay": relay_body,
    }
    r = client.put("/api/admin/mail/settings", json=body, headers=headers)
    run.check("보내는 방법 저장(로컬 릴레이 · 인터넷으로 직접 전달)", r.status_code == 200,
              f"HTTP {r.status_code} {r.text[:200] if r.status_code != 200 else ''}".strip())
    if r.status_code != 200:
        return _finish(run, 1)

    # 2b DKIM — 키는 서버가 만들고 공개키(TXT 레코드 값)만 돌아온다. 서명을 켠 채 다시 저장한다.
    if args.dkim:
        r = client.post("/api/admin/mail/relay/dkim", json={}, headers=headers)
        run.check("DKIM 키 준비(없으면 만들기)", r.status_code == 200,
                  f"HTTP {r.status_code} {r.text[:200] if r.status_code != 200 else ''}".strip())
        if r.status_code == 200:
            saved = client.get("/api/admin/mail/settings").json()["settings"]
            saved_relay = dict(saved.get("relay") or {})
            relay_body["dkim_enabled"] = True
            relay_body["dkim_selector"] = saved_relay.get("dkim_selector") or relay_body.get("dkim_selector") or ""
            body["relay"] = relay_body
            r = client.put("/api/admin/mail/settings", json=body, headers=headers)
            run.check("DKIM 서명을 켠 채 저장", r.status_code == 200,
                      f"HTTP {r.status_code} {r.text[:200] if r.status_code != 200 else ''}".strip())
            run.info("DKIM 공개키 레코드(도메인 DNS 에 넣을 값)",
                     {"selector": relay_body["dkim_selector"], "public": saved_relay.get("dkim_public") or ""})

    # 3 켜기
    r = client.post("/api/admin/mail/relay/apply", headers=headers)
    applied = r.json() if r.status_code == 200 else {}
    result = applied.get("result") or {}
    run.check("릴레이 켜기(헬퍼 apply)", r.status_code == 200 and bool(result.get("ok")),
              {"http": r.status_code, "ok": result.get("ok"), "message": result.get("message") or r.text[:200]})
    verify = (applied.get("verify") or {}).get("job_id")
    if verify:
        done = _poll(lambda: (lambda j: j if not j.get("pending") else None)(
            client.get(f"/api/admin/mail/verify/{verify}").json()), timeout=90)
        health = client.get("/api/admin/mail/status").json().get("health") or {}
        run.check("앱 → 릴레이 연결 확인", bool(done) and health.get("state") in ("ok", "unverified"),
                  {"health": health.get("state"), "label": health.get("label"), "stage": health.get("stage"),
                   "message": health.get("message")})

    # 4 준비 점검
    probe = args.probe_domain or to.partition("@")[2]
    r = client.post("/api/admin/mail/relay/check", json={"probe_domain": probe}, headers=headers)
    job = r.json().get("job_id") if r.status_code == 200 else None
    readiness = None
    if job:
        got = _poll(lambda: (lambda j: j if not j.get("pending") else None)(
            client.get(f"/api/admin/mail/relay/check/{job}").json()), timeout=180, every=3)
        readiness = (got or {}).get("readiness")
    run.check("준비 점검이 끝났다", readiness is not None, f"job {job}")
    for row in ((readiness or {}).get("checks") or []):
        run.info(f"점검 {row.get('key')}", {"state": row.get("state"), "sentence": row.get("sentence") or row.get("message"),
                                           "fix": row.get("fix") or row.get("where")})

    if args.skip_send:
        return _finish(run, 0)

    # 5 시험 메일
    r = client.post("/api/admin/mail/test", json={"to": to}, headers=headers)
    sent = r.json() if r.status_code == 200 else {}
    delivery = sent.get("delivery") or {}
    run.check("시험 메일을 큐에 넣었다", r.status_code == 200 and bool(delivery.get("id")),
              {"http": r.status_code, "sentence": sent.get("sentence")})
    if not delivery.get("id"):
        return _finish(run, 1)
    return _track(run, detail, delivery["id"], args.wait_outer)


def _track(run: Run, detail, did: str, wait_outer: float) -> int:
    """발송 기록 한 통의 단계 — ③ 로컬 릴레이 접수(250) → ④ 수신측 메일 서버 접수(바깥 전달). ⑤ · ⑥ 은 사람이 본다."""
    def accepted():
        d = detail(did)
        return d if d.get("status") in ("sent", "failed", "cancelled", "unconfigured") else None
    d = _poll(accepted, timeout=120, every=2) or {}
    run.check("로컬 릴레이가 접수했다(250)", d.get("status") == "sent",
              {"status": d.get("status"), "label": d.get("status_label"), "stage": d.get("failure_stage"),
               "response": d.get("relay_response"), "message_id": d.get("message_id")})

    def outer():
        x = detail(did)
        rel = x.get("relay") or {}
        return x if rel.get("remote_status") in ("delivered", "bounced", "expired") else None
    d2 = _poll(outer, timeout=wait_outer, every=10) or detail(did)
    rel = d2.get("relay") or {}
    state = rel.get("remote_status")
    run.check("바깥 전달 결과가 나왔다", state in ("delivered", "bounced", "expired"),
              {"remote_status": state, "label": rel.get("remote_label"), "stage": rel.get("remote_stage"),
               "detail": rel.get("remote_detail"), "checked_at": rel.get("remote_checked_at"),
               "screen_label": d2.get("status_label")})
    if state != "delivered":
        run.info("바깥 전달이 끝나지 않았거나 거부됐다 — 측정한 단계와 바깥 조건을 그대로 남긴다", {"relay": rel})
    return _finish(run, 0 if state == "delivered" else 1)


def _finish(run: Run, code: int) -> int:
    (OUT / "result.json").write_text(json.dumps({"rows": run.rows, "exit": code}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"LAB_MAIL_E2E_DONE exit={code} → {OUT / 'result.json'}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
