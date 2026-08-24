"""이번 회차가 **건드린 화면만** 로컬에서 띄워 찍는다 (S15 · E5).

`local_server.py` 로 임시 데이터베이스 위에 앱을 하나 띄우고, 그 주소로 `run.py` 를 부른다.
설치처를 건드리지 않고 «이 회차의 빌드» 를 찍는 것이 목적이다 — 사람들이 쓰는 설치에
배포하는 것은 캡처의 전제가 아니라 별개의 결정이다.

## 쓰는 법

    python -m scripts.ui_qa.local_capture --label s15-after \\
        --routes user_my-tickets user_board user_knowledge ...

`--routes` 를 안 주면 아무것도 안 찍는다. 전량 실행은 **S22 의 몫**이고(E8), 여기서
기본값으로 열어 두면 그 규칙이 흐려진다.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa import local_server  # noqa: E402


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="로컬 서버 + 캡처 한 번에 (S15)")
    ap.add_argument("--label", required=True)
    ap.add_argument("--routes", nargs="+", required=True)
    ap.add_argument("--viewports", nargs="*", default=["1920x1080"])
    ap.add_argument("--themes", nargs="*", default=["light", "dark"])
    ap.add_argument("--fail-on", nargs="*", default=None)
    ap.add_argument("--email", default="ui-qa@goodmit.co.kr")
    ap.add_argument("--password", default="Ui-Qa-Local-1!")
    args, rest = ap.parse_known_args()

    workdir = Path(tempfile.mkdtemp(prefix="clovir-uiqa-"))
    url = local_server.create_database()
    server = None
    try:
        settings = local_server.build_settings(url, workdir)
        local_server.seed(url, args.email, args.password, settings)
        port = local_server._free_port()
        server, _ = local_server.serve(settings, port)
        base = "http://127.0.0.1:%d" % port
        print("== 로컬 서버 %s ==" % base, flush=True)

        # 하네스가 이 계정으로 로그인한다. 계정은 방금 심었으므로 CLI 로 만들 필요가 없다.
        import os

        os.environ["UI_QA_EMAIL"] = args.email
        os.environ["UI_QA_PASSWORD"] = args.password

        from scripts.ui_qa import run as run_mod

        argv = ["--base-url", base, "--label", args.label,
                "--routes", *args.routes,
                "--viewports", *args.viewports,
                "--themes", *args.themes]
        if args.fail_on:
            argv += ["--fail-on", *args.fail_on]
        argv += rest
        sys.argv = ["run.py", *argv]
        return run_mod.main()
    finally:
        if server is not None:
            server.should_exit = True
            time.sleep(0.5)
        local_server.drop_database()


if __name__ == "__main__":
    raise SystemExit(main())
