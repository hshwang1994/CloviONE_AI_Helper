"""이번 회차가 **건드린 화면만** 로컬에서 띄워 찍는다 (S15 · E5).

`local_server.py` 로 임시 데이터베이스 위에 앱을 하나 띄우고, 그 주소로 `run.py` 를 부른다.
설치처를 건드리지 않고 «이 회차의 빌드» 를 찍는 것이 목적이다 — 사람들이 쓰는 설치에
배포하는 것은 캡처의 전제가 아니라 별개의 결정이다.

## 쓰는 법

    python -m scripts.ui_qa.local_capture --label s15-after \\
        --routes user_my-tickets user_board user_knowledge ...

`--routes` 를 안 주면 아무것도 안 찍는다. 전량 실행은 **S22 의 몫**이고(E8), 여기서
기본값으로 열어 두면 그 규칙이 흐려진다.

## 캡처 말고 다른 하네스 (S16)

`--harness` 로 `scripts.ui_qa` 의 다른 모듈을 같은 서버에 대고 부른다. 완료로 표시한
Surface 의 증거는 **지금 빌드에서도 유효해야** 하는데(게이트의 `EVIDENCE_STALE_BUILD`),
그 증거의 절반은 캡처가 아니라 `kit_e2e`·`shell_e2e`·`nav_e2e` 같은 실브라우저 하네스다.
그것들만 설치처를 요구하면 「빌드가 바뀔 때마다 배포해야 한다」가 되어 E5 와 어긋난다.

    python -m scripts.ui_qa.local_capture --harness kit_e2e
    python -m scripts.ui_qa.local_capture --harness shell_e2e --harness nav_e2e

`--harness` 를 주면 `--routes` 는 필요 없다(캡처를 안 돌린다).
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
    ap.add_argument("--label", default="local")
    ap.add_argument("--routes", nargs="+", default=None)
    ap.add_argument("--harness", action="append", default=[],
                    help="scripts.ui_qa 의 모듈 이름(kit_e2e·shell_e2e·nav_e2e…). "
                         "주면 캡처 대신 그것을 부른다")
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
        # 하네스가 다른 역할의 계정을 요구하면 `user_cli` 를 **자식 프로세스로** 부른다
        # (auth.py §_provision — DB 를 직접 건드리지 않는다는 규율 때문이다). 그 자식은
        # 우리가 방금 만든 임시 데이터베이스를 알 방법이 없어서 기본 주소로 붙다가 시간
        # 초과로 죽는다. 설정을 **환경으로도** 넘겨 자식이 같은 DB 를 보게 한다.
        os.environ["DATABASE_URL"] = url
        os.environ["APP_ENV"] = "test"
        os.environ["SESSION_SECRET"] = "ui-qa-local-session-secret"
        os.environ["SECRETS_DIR"] = str(settings.secrets_dir)
        os.environ["DATA_DIR"] = str(workdir)

        if args.harness:
            """하네스를 순서대로 부르고 **하나라도 실패하면 그 종료 코드를 그대로 낸다.**
            여러 개를 돌린 뒤 마지막 것만 보고 초록이라고 말하지 않는다."""
            import importlib

            worst = 0
            for name in args.harness:
                mod = importlib.import_module("scripts.ui_qa." + name)
                sys.argv = [name + ".py", "--base-url", base, *rest]
                print("\n== %s ==" % name, flush=True)
                code = mod.main()
                worst = max(worst, code or 0)
            return worst

        if not args.routes:
            print("[FATAL] --routes 나 --harness 중 하나는 있어야 한다.", file=sys.stderr)
            return 2

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
