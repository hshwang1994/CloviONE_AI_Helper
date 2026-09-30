"""설치 문서 대조 검사기가 스스로 맞다 (scripts/check_install_docs.py, D-523).

검사기가 아무것도 보지 않으면서 초록일 수 있다(문서에서 명령을 하나도 못 찾는 경우). 그래서 세 가지를 잰다:
맞는 문장과 틀린 문장을 가르는가, 실제 문서에서 명령을 찾는가, 실제 문서가 지금 스크립트와 맞는가.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _checker():
    spec = importlib.util.spec_from_file_location("check_install_docs", ROOT / "scripts" / "check_install_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_checker_tells_right_from_wrong():
    assert _checker().selftest() == 0


def test_a_renamed_option_in_the_docs_is_caught():
    checker = _checker()
    subcommands, options = checker.installer_vocabulary((ROOT / "deploy" / "install.sh").read_text(encoding="utf-8"))
    cli = checker.cli_vocabulary((ROOT / "deploy" / "clovirassist-cli.sh").read_text(encoding="utf-8"))
    doc = "```bash\nsudo bash install.sh install --dns <host> --bind-ip <ip>\n```\n"
    problems = checker.scan_text(doc, subcommands=subcommands, options=options, cli_commands=cli)
    assert len(problems) == 1 and "--dns" in problems[0]
    # 스크립트가 실제로 받는 옵션과 서브커맨드를 읽었다(빈 어휘로 모든 것을 통과시키지 않는다).
    assert {"install", "upgrade", "rollback"} <= subcommands and {"--dns-name", "--release"} <= options
    assert {"user", "first-admin-code"} <= cli


def test_the_real_docs_match_the_installer(capsys):
    assert _checker().main([]) == 0
    out = capsys.readouterr().out
    assert "INSTALL_DOCS_OK" in out
    checked = int(out.split("문서의 설치 명령 ", 1)[1].split("개", 1)[0])
    assert checked >= 10, "문서에서 설치 명령을 거의 못 찾았다 - 검사가 아무것도 보지 않는다"
