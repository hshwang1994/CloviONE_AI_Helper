"""감사 CSV 가 잘렸다는 사실은 **파일 안에** 있어야 한다.

## 무엇이 잘못됐나

내보내기 상한은 5만 행이고, 잘렸다는 사실은 `X-Export-Truncated` **HTTP 헤더로만** 알렸다.
브라우저는 그 헤더를 사용자에게 보여 주지 않는다 — 다운로드 폴더에 떨어진 파일에는 아무
표시도 없다. 감사 담당자는 그 파일을 엑셀로 열어 **그게 전부인 줄 알고** 감사 보고서에
붙인다. "그 기간엔 그것뿐이었다"는 결론이 조용히 틀린다.

파일 자체가 자기가 잘렸다고 말해야 한다.

## 상한을 낮춰 시험하는 이유

진짜 5만 행을 심으면 이 테스트 하나가 몇 분을 먹는다. 상한은 모듈 상수 하나이고 코드는
그 이름을 호출 시점에 읽으므로, 상수를 3으로 낮추면 **같은 코드 경로**가 그대로 돈다.
"""

from __future__ import annotations

import pytest

from app.audit.models import AuditLog

pytestmark = pytest.mark.integration

SMALL_CAP = 3


@pytest.fixture()
def seed_logs(db):
    """감사 로그 n건을 심는다."""

    def _seed(count: int):
        from datetime import datetime

        for i in range(count):
            db.add(
                AuditLog(
                    user_id=None,
                    action="test.export",
                    object_type="thing",
                    object_id=f"obj-{i:03d}",
                    result="success",
                    created_at=datetime(2026, 8, 1, 0, 0, i % 60),
                )
            )
        db.commit()

    return _seed


def _export(client):
    response = client.get("/api/admin/audit/export.csv")
    assert response.status_code == 200, response.text
    return response


def _total(client) -> int:
    """지금 이 계정에게 보이는 감사 행 수.

    로그인 자체가 `auth.login` 행을 하나 남기므로 표본 크기를 손으로 세면 어긋난다 —
    한 번 어긋나면 "상한과 정확히 같은 행 수" 같은 경계 조건을 시험할 수가 없다.
    """
    response = client.get("/api/admin/audit", params={"page_size": 1})
    assert response.status_code == 200, response.text
    return int(response.json()["total"])


def test_the_file_says_it_was_truncated(client, login_as, seed_logs, monkeypatch):
    """잘린 파일을 열면 **파일 안에서** 잘렸다는 것을 읽을 수 있어야 한다."""
    monkeypatch.setattr("app.audit.router.EXPORT_MAX_ROWS", SMALL_CAP)
    login_as("auditor")
    seed_logs(SMALL_CAP + 5)

    body = _export(client).text
    lines = [line for line in body.splitlines() if line.strip()]

    assert "잘렸" in body, (
        "잘린 CSV 인데 파일 안에는 잘렸다는 말이 한 글자도 없다 "
        f"(마지막 줄: {lines[-1]!r})"
    )
    assert str(SMALL_CAP) in lines[-1], (
        f"마지막 줄이 몇 행에서 잘렸는지 말하지 않는다: {lines[-1]!r}"
    )


def test_the_truncation_notice_is_the_last_line_not_a_data_row(
    client, login_as, seed_logs, monkeypatch
):
    """머리글은 그대로 1행이어야 한다 — 위에 끼워 넣으면 엑셀의 열이 통째로 밀린다."""
    monkeypatch.setattr("app.audit.router.EXPORT_MAX_ROWS", SMALL_CAP)
    login_as("auditor")
    seed_logs(SMALL_CAP + 5)

    lines = [line for line in _export(client).text.splitlines() if line.strip()]
    assert lines[0].lstrip("﻿").startswith("시각(KST)"), (
        f"머리글이 1행이 아니다: {lines[0]!r}"
    )
    # 머리글 1 + 데이터 SMALL_CAP + 안내 1
    assert len(lines) == SMALL_CAP + 2, (
        f"줄 수가 맞지 않는다({len(lines)}): 데이터 {SMALL_CAP}행 + 머리글 + 안내여야 한다"
    )
    assert "잘렸" in lines[-1], f"안내가 마지막 줄이 아니다: {lines[-1]!r}"


def test_a_complete_export_carries_no_notice(client, login_as, seed_logs, monkeypatch):
    """안 잘린 파일에 경고를 붙이면 다음부터 아무도 그 경고를 안 읽는다."""
    login_as("auditor")
    seed_logs(2)
    monkeypatch.setattr("app.audit.router.EXPORT_MAX_ROWS", _total(client) + 1)

    response = _export(client)
    assert "잘렸" not in response.text, "안 잘렸는데 잘렸다고 적혀 있다"
    assert response.headers["X-Export-Truncated"] == "0"


def test_exactly_the_cap_is_not_truncated(client, login_as, seed_logs, monkeypatch):
    """딱 상한만큼이면 잘린 것이 아니다.

    `len(rows) >= CAP` 로 판정하면 정확히 상한인 파일이 **거짓으로** 잘렸다고 말한다 —
    한 번 거짓말을 하면 그다음 진짜 경고도 같이 무시된다.
    """
    login_as("auditor")
    seed_logs(2)
    monkeypatch.setattr("app.audit.router.EXPORT_MAX_ROWS", _total(client))

    response = _export(client)
    assert response.headers["X-Export-Truncated"] == "0", (
        "정확히 상한인 내보내기를 잘렸다고 말했다"
    )
    assert "잘렸" not in response.text


def test_the_filename_also_says_it_is_partial(client, login_as, seed_logs, monkeypatch):
    """파일을 열기 전에도 보여야 한다 — 다운로드 폴더에서 이름만 보이는 상황이 흔하다."""
    monkeypatch.setattr("app.audit.router.EXPORT_MAX_ROWS", SMALL_CAP)
    login_as("auditor")
    seed_logs(SMALL_CAP + 5)

    disposition = _export(client).headers["Content-Disposition"]
    assert "partial" in disposition, (
        f"잘린 파일인데 파일 이름이 전체 내보내기와 똑같다: {disposition}"
    )
