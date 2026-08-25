"""S21 전수 실행을 **네 묶음으로 나눠 동시에** 돌린다 (W14).

820 Flow 를 한 프로세스로 돌면 다섯 시간이 넘는다. 그 길이 자체가 문제는 아니지만, 그
동안 한 번이라도 멈추면 전부를 잃는다 — 지시가 bounded batch 를 요구한 이유가 그것이다.

## 왜 «서버까지» 나누는가

같은 데이터베이스에 네 브라우저를 붙이면 서로의 쓰기를 밟는다. 한쪽이 티켓을 휴지통으로
보내는 동안 다른 쪽이 그 티켓을 고치려 하고, 실패는 화면이 아니라 **동시성 때문에** 난다.
그래서 묶음마다 **자기 데이터베이스와 자기 서버**를 갖는다. 로그인 세션 자리도 나눈다 —
같은 `storage_state.json` 을 넷이 덮으면 한쪽이 남의 역할로 잰다.

    python -m scripts.ui_qa.s21_run_all --chunks 4
    python -m scripts.ui_qa.s21_run_all --chunks 4 --keep   # 끝나고 서버를 안 내린다
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

WORK = REPO_ROOT / "dist" / "ui-qa" / "s21-work"
OUT = REPO_ROOT / "dist" / "ui-qa" / "s21"
PY = sys.executable


def start_server(index: int, port: int) -> subprocess.Popen:
    data_dir = WORK / ("srv%d" % index)
    data_dir.mkdir(parents=True, exist_ok=True)
    log = open(WORK / ("server%d.log" % index), "w", encoding="utf-8")
    return subprocess.Popen(
        [PY, "-m", "scripts.ui_qa.local_server", "--hold", "--port", str(port),
         "--db-name", "clovir_s21_%d" % index, "--data-dir", str(data_dir), "--keep"],
        cwd=str(REPO_ROOT), stdout=log, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def wait_ready(port: int, timeout: int = 240) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=3):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(3)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="S21 전수 실행 (묶음 병렬)")
    ap.add_argument("--chunks", type=int, default=4)
    ap.add_argument("--base-port", type=int, default=8101)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--surfaces", nargs="*", default=None,
                    help="이 화면들만 (표적 재검증)")
    ap.add_argument("--out", default=str(OUT), help="결과를 적을 자리")
    args = ap.parse_args()
    out_dir = Path(args.out).resolve()

    WORK.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("flows-*.json"):
        stale.unlink()

    servers, ports = [], []
    for i in range(args.chunks):
        port = args.base_port + i
        ports.append(port)
        servers.append(start_server(i + 1, port))
        print("[서버 %d] 127.0.0.1:%d 올리는 중" % (i + 1, port), flush=True)

    runs = []
    try:
        for i, port in enumerate(ports):
            if not wait_ready(port):
                print("[FATAL] 서버 %d 이 안 떴다" % (i + 1), file=sys.stderr)
                return 2
            print("[서버 %d] 준비됨" % (i + 1), flush=True)

        for i, port in enumerate(ports):
            session_dir = WORK / ("session%d" % (i + 1))
            log = open(WORK / ("chunk%d.log" % (i + 1)), "w", encoding="utf-8")
            env = {**os.environ, "PYTHONIOENCODING": "utf-8",
                   "APP_ENV": "test",
                   "SESSION_SECRET": "ui-qa-local-session-secret",
                   "DATABASE_URL": ("postgresql://cloviradmin:s2devpw@127.0.0.1:55433/"
                                    "clovir_s21_%d" % (i + 1)),
                   "SECRETS_DIR": str(WORK / ("srv%d" % (i + 1)) / "secrets"),
                   "DATA_DIR": str(WORK / ("srv%d" % (i + 1))),
                   "UI_QA_EMAIL": "ui-qa@goodmit.co.kr",
                   "UI_QA_PASSWORD": "Ui-Qa-Local-1!"}
            runs.append(subprocess.Popen(
                [PY, "-m", "scripts.ui_qa.s21_e2e",
                 "--base-url", "http://127.0.0.1:%d" % port,
                 "--out", str(out_dir), "--session-dir", str(session_dir),
                 "--chunk", "%d/%d" % (i + 1, args.chunks)]
                + (["--surfaces", *args.surfaces] if args.surfaces else []),
                cwd=str(REPO_ROOT), stdout=log, stderr=subprocess.STDOUT, env=env))
            print("[묶음 %d/%d] 시작 · 로그 %s"
                  % (i + 1, args.chunks, WORK / ("chunk%d.log" % (i + 1))), flush=True)

        codes = [p.wait() for p in runs]
        print("묶음 종료 코드: %s" % codes, flush=True)
    finally:
        if not args.keep:
            for p in servers:
                p.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
