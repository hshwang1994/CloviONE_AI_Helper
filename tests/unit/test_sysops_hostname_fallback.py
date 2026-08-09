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
