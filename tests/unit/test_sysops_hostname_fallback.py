"""SYS-02: `system.info` 의 호스트 이름 조회가 systemd 255 에서 영구히 빈 문자열이었다.

`hostnamectl show -p StaticHostname --value` 는 이 서버(systemd 255)에 없는 verb다
(실측: `Unknown command verb 'show'`) - `/system` 화면이 "호스트 이름: 확인하지
못했습니다"를 항상 보여줬다. `hostname.set`(app/sysops/actions_system.py) 은 이미
`hostnamectl status --static` 을 먼저 쓰는 폴백을 갖고 있고 그게 이 서버에서 동작한다 -
같은 지식이 조회(`system.info`) 쪽에는 적용되지 않았던 것이 결함이다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.sysops import actions as registry
from tests.fakes.sysops import FakeRunner

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)


def _info(runner):
    return registry.execute(runner, "system.info", {}, backup_root="/tmp/backups", now=NOW)


def test_uses_status_static_when_available():
    runner = FakeRunner()
    runner.reply(["/usr/bin/hostnamectl", "status", "--static"], out="ai-n8n-svr\n")
    runner.reply(["/usr/bin/timedatectl", "show", "-p", "Timezone", "--value"], out="Asia/Seoul\n")
    runner.reply(["/usr/bin/timedatectl", "show", "-p", "NTPSynchronized", "--value"], out="yes\n")
    runner.reply(["/usr/bin/df", "-h", "/"], out="/dev/sda1 20G 5G 15G 25% /\n")

    result = _info(runner)
    assert result.data["hostname"] == "ai-n8n-svr"
    # 신버전 폴백(show -p)은 부르지 않는다 - status --static 이 이미 답을 줬다.
    assert ["/usr/bin/hostnamectl", "show", "-p", "StaticHostname", "--value"] not in [
        list(c) for c in runner.calls
    ]


def test_falls_back_to_show_dash_p_when_status_static_is_unsupported():
    """systemd 255 에서 이 verb 가 없다고 났던 실제 실패 형태(exit!=0)를 흉내낸다."""
    runner = FakeRunner()
    runner.reply(["/usr/bin/hostnamectl", "status", "--static"],
                  code=1, err="Unknown command verb 'status'")
    runner.reply(["/usr/bin/hostnamectl", "show", "-p", "StaticHostname", "--value"], out="ai-n8n-svr\n")
    runner.reply(["/usr/bin/timedatectl", "show", "-p", "Timezone", "--value"], out="Asia/Seoul\n")
    runner.reply(["/usr/bin/timedatectl", "show", "-p", "NTPSynchronized", "--value"], out="yes\n")
    runner.reply(["/usr/bin/df", "-h", "/"], out="/dev/sda1 20G 5G 15G 25% /\n")

    result = _info(runner)
    assert result.data["hostname"] == "ai-n8n-svr"


def test_neither_command_available_reports_unknown_not_a_crash():
    """오탐 방지 - 둘 다 실패해도 빈 문자열로 조용히 남는다(화면이 '확인하지 못했습니다'로
    보여줄 몫이지, 액션 전체가 죽으면 안 된다)."""
    runner = FakeRunner()
    runner.reply(["/usr/bin/hostnamectl", "status", "--static"], code=1, err="no")
    runner.reply(["/usr/bin/hostnamectl", "show", "-p", "StaticHostname", "--value"], code=1, err="no")
    runner.reply(["/usr/bin/timedatectl", "show", "-p", "Timezone", "--value"], out="Asia/Seoul\n")
    runner.reply(["/usr/bin/timedatectl", "show", "-p", "NTPSynchronized", "--value"], out="yes\n")
    runner.reply(["/usr/bin/df", "-h", "/"], out="/dev/sda1 20G 5G 15G 25% /\n")

    result = _info(runner)
    assert result.data["hostname"] == ""
    assert result.ok


# ── UI-R42: DNS·프록시의 지금 지정된 값도 준다 ────────────────────────────────
#
# 화면이 그 두 줄을 "서버에서만 확인할 수 있습니다"로 비워 두고 있었다 — 정직했지만 답은
# 아니었다. 이 콘솔이 쓴 드롭인을 그대로 읽어 준다. 여기서 못박는 것은 셋이다.
#   1) 지정돼 있으면 값을 준다.
#   2) 지정 안 했으면 **없다고** 말한다("읽지 못함"과 다른 사실이다).
#   3) 조회가 실패해도 나머지 시스템 정보는 그대로 나온다 — 전부 아니면 아무것도가 되면
#      진단에 못 쓴다(이 파일 위쪽 `_perform_info` 의 docstring 과 같은 이유).


def test_dns_and_proxy_report_configured_values():
    from app.sysops.actions_service import RESOLVED_DROPIN, _proxy_dropin_path

    runner = FakeRunner({
        RESOLVED_DROPIN: "[Resolve]\nDNS=10.0.0.1 10.0.0.2\nDomains=corp.example\n",
        _proxy_dropin_path("clovirone-web-assistant.service"):
            '[Service]\nEnvironment="HTTPS_PROXY=http://proxy.example:3128"\n'
            'Environment="NO_PROXY=localhost"\n',
    })
    data = _info(runner).data
    assert data["dns"]["configured"] is True
    assert data["dns"]["servers"] == ["10.0.0.1", "10.0.0.2"]
    assert data["dns"]["search"] == "corp.example"
    assert data["proxy"]["configured"] is True
    assert data["proxy"]["url"] == "http://proxy.example:3128"
    assert data["proxy"]["no_proxy"] == "localhost"


def test_unset_is_said_as_unset_not_as_unreadable():
    data = _info(FakeRunner()).data
    assert data["dns"] == {"configured": False, "servers": [], "search": None, "source": "unset"}
    assert data["proxy"]["configured"] is False
    assert data["proxy"]["source"] == "unset"


def test_a_broken_read_does_not_take_the_rest_of_the_info_down():
    class Boom(FakeRunner):
        def read_text(self, path):
            raise OSError("permission denied")

    from app.sysops.actions_service import RESOLVED_DROPIN

    runner = Boom({RESOLVED_DROPIN: "x"})
    runner.reply(["/usr/bin/hostnamectl", "status", "--static"], out="ai-n8n-svr\n")
    data = _info(runner).data
    assert data["dns"]["source"] == "unreadable"
    # 나머지는 그대로 나온다.
    assert data["hostname"] == "ai-n8n-svr"
    assert "units" in data
