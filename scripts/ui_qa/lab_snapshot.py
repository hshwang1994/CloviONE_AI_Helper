"""랩 읽기 전용 사진 — 배포 전후로 데이터 수와 운영 설정이 그대로인지 견준다 (r23 W8).

사용자 계정(`dist/ops/user.env` 의 AI_TRUTH_*)으로 **GET 만** 부른다. 아무것도 바꾸지 않는다. 비밀(비밀번호 · 키)은 화면 API 가
원래 싣지 않고, 이 도구도 값 칸 가운데 이름에 password · secret · token · key 가 든 것은 「(가림)」으로 바꿔 적는다.

    python -m scripts.ui_qa.lab_snapshot --base https://clovirassist.goodmit.co.kr --out dist/ui-qa/r23-lab/snapshot-before.json
    python -m scripts.ui_qa.lab_snapshot --base … --out …/snapshot-after.json --compare …/snapshot-before.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ui_qa.ai_lab_common import read_env_file  # noqa: E402

ENV_KEYS = ("AI_TRUTH_EMAIL", "AI_TRUTH_PASSWORD")

# 수만 센다(목록 응답의 total). 경로는 화면이 쓰는 것과 같다.
COUNTS = {
    "내 티켓(전체 상태)": "/api/tickets/mine?all_status=1&page_size=1",
    "팀 티켓": "/api/tickets/team?page_size=1",
    "프로젝트": "/api/projects?page_size=1",
    "문서": "/api/knowledge/documents?page_size=1",
    "사용자": "/api/admin/users?page_size=1",
    "게시글": "/api/board/posts?page_size=1",
    "게임방": "/api/games/rooms",
    "감사 로그": "/api/admin/audit?page_size=1",
}
# 운영 설정 — 값 그대로 견준다(비밀은 가린다).
SETTINGS = {
    "메일 설정": "/api/admin/mail/settings",
    "AI 연결": "/api/admin/ai",
    "내 프로필 설정": "/api/me/preferences",
}
SECRET_HINTS = ("password", "secret", "token", "api_key", "apikey", "private")


def _values_only(o):
    """사용자 값만 남긴다 — 화면용 목록(`catalog` · `groups` · 이름표)은 배포로 문구가 바뀌어도 사용자 설정이 바뀐 것이 아니다."""
    if isinstance(o, dict):
        return {k: _values_only(v) for k, v in o.items() if k not in ("catalog", "groups", "labels", "options", "admin_catalog")}
    if isinstance(o, list):
        return [_values_only(v) for v in o]
    return o


def _mask(o):
    if isinstance(o, dict):
        return {k: ("(가림)" if any(h in k.lower() for h in SECRET_HINTS) and v not in (None, "", False) else _mask(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_mask(v) for v in o]
    return o


def _total(body):
    if isinstance(body, dict):
        for k in ("total", "count"):
            if isinstance(body.get(k), int):
                return body[k]
        for k in ("items", "rooms", "rows"):
            if isinstance(body.get(k), list):
                return len(body[k])
    if isinstance(body, list):
        return len(body)
    return None


def take(base: str, creds: dict) -> dict:
    import httpx

    out: dict = {"base": base, "counts": {}, "settings": {}, "errors": {}}
    with httpx.Client(base_url=base, verify=False, timeout=30.0, follow_redirects=True) as c:
        # 로그인 폼은 성공하면 첫 화면으로 돌려보낸다(303) — 따라간 뒤 세션으로 /api/me 가 서는지가 판정이다.
        c.post("/login", data={"email": creds["AI_TRUTH_EMAIL"], "password": creds["AI_TRUTH_PASSWORD"]})
        who = c.get("/api/me")
        if who.status_code != 200:
            raise SystemExit(f"로그인 실패(/api/me {who.status_code})")
        me = who.json()
        out["who"] = {"role": (me.get("user") or {}).get("role")}
        out["app"] = {k: v for k, v in (c.get("/api/version").json() if c.get("/api/version").status_code == 200 else {}).items()
                      if k in ("version", "commit", "build", "bundle")}
        for name, path in COUNTS.items():
            res = c.get(path)
            if res.status_code == 200:
                out["counts"][name] = _total(res.json())
            else:
                out["errors"][name] = res.status_code
        for name, path in SETTINGS.items():
            res = c.get(path)
            if res.status_code == 200:
                body = res.json()
                if name == "메일 설정":
                    s = (body or {}).get("settings") or {}
                    body = {k: s.get(k) for k in ("enabled", "mode", "from_address", "from_name", "host", "port", "security")}
                    body["helo_name"] = ((s.get("relay") or {}).get("helo_name"))
                    body["delivery"] = ((s.get("relay") or {}).get("delivery"))
                elif name == "AI 연결":
                    cfg = (body or {}).get("config") or {}
                    body = {k: cfg.get(k) for k in ("generation_enabled", "provider", "auth_method", "model", "timeout_seconds", "max_concurrency")}
                    body["features"] = (res.json() or {}).get("features")
                out["settings"][name] = _mask(_values_only(body))
            else:
                out["errors"][name] = res.status_code
    return out


# 감사 로그는 이 도구의 로그인마다 한 줄씩 는다 — 견주기에서 빼고 수만 따로 적는다.
NOT_COMPARED = {"감사 로그"}


def compare(a: dict, b: dict) -> list[str]:
    diffs = []
    for sect in ("counts", "settings"):
        for k in sorted(set(a.get(sect, {})) | set(b.get(sect, {}))):
            if k in NOT_COMPARED:
                continue
            if a.get(sect, {}).get(k) != b.get(sect, {}).get(k):
                diffs.append(f"{sect}.{k}: {json.dumps(a.get(sect, {}).get(k), ensure_ascii=False)[:200]} → "
                             f"{json.dumps(b.get(sect, {}).get(k), ensure_ascii=False)[:200]}")
    return diffs


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--compare", default="")
    ap.add_argument("--env-file", default=str(ROOT / "dist" / "ops" / "user.env"))
    args = ap.parse_args()
    creds = read_env_file(args.env_file, ENV_KEYS)
    if not all(creds.get(k) for k in ENV_KEYS):
        print("자격이 없습니다 — env 파일에 AI_TRUTH_EMAIL · AI_TRUTH_PASSWORD 가 있어야 합니다.")
        return 2
    snap = take(args.base.rstrip("/"), creds)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print("LAB_SNAPSHOT", json.dumps({"counts": snap["counts"], "errors": snap["errors"]}, ensure_ascii=False))
    if args.compare:
        prev = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        diffs = compare(prev, snap)
        print("LAB_SNAPSHOT_SAME" if not diffs else "LAB_SNAPSHOT_DIFF")
        for d in diffs:
            print("  -", d)
        return 0 if not diffs else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
