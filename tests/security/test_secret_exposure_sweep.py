"""Sweep every admin GET endpoint as system_admin with a seeded secret and
assert the plaintext value never appears in any response (spec §25.4, §31.10)."""

import pytest

pytestmark = pytest.mark.security

SECRET_VALUE = "TOP-SECRET-PLAINTEXT-VALUE-DO-NOT-LEAK-9271"


@pytest.fixture()
def seeded(client, login_as, settings):
    csrf = login_as("system_admin")
    (settings.secrets_dir / "sweep-secret").write_text(SECRET_VALUE, encoding="utf-8")
    h = {"X-CSRF-Token": csrf}
    # Integration + runner referencing the secret.
    #
    # 주소는 **런타임 허용 목록에 있는 호스트**여야 한다. 예전에는 여기가 api.notion.com
    # 이었는데 그 호스트가 목록에서 빠지면서 생성이 400 으로 막혔고, 그러면 아래 시험들은
    # 시크릿을 가진 행이 하나도 없는 세계에서 "아무 데도 안 샌다" 를 확인하게 된다 —
    # 아무것도 증명하지 못하는 초록불이다.
    created = client.post(
        "/api/admin/integrations",
        json={"name": "sweep-int", "provider_type": "http_service",
              "base_url": "https://api.anthropic.com", "auth_type": "bearer",
              "secret_ref": "sweep-secret"},
        headers=h,
    )
    assert created.status_code == 201, (
        f"시크릿을 가리키는 연동을 못 만들었다 — 아래 검사가 빈 세계를 훑는다: {created.text}"
    )
    return h


ADMIN_GET_ENDPOINTS = [
    "/api/admin/users",
    "/api/admin/integrations",
    "/api/admin/prompts",
    "/api/admin/policies",
    "/api/admin/schedules",
    "/api/admin/approvals",
    "/api/admin/audit",
    "/api/admin/settings",
    "/api/admin/backups",
    "/api/admin/notion-mapping",
    "/api/admin/dashboard",
    "/api/admin/diagnostics/bundle",
    "/api/admin/jobs",
    "/api/notifications",
]


def test_no_endpoint_leaks_secret_plaintext(client, seeded):
    leaks = []
    for path in ADMIN_GET_ENDPOINTS:
        r = client.get(path, headers=seeded)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        if SECRET_VALUE in r.text:
            leaks.append(path)
    assert leaks == [], f"secret leaked in: {leaks}"


def test_integration_detail_shows_status_not_value(client, seeded):
    listing = client.get("/api/admin/integrations", headers=seeded).json()["items"]
    sweep = next(i for i in listing if i["name"] == "sweep-int")
    assert sweep["secret_status"] == "configured"
    detail = client.get(f"/api/admin/integrations/{sweep['id']}", headers=seeded)
    assert SECRET_VALUE not in detail.text
    assert detail.json()["integration"]["secret_status"] == "configured"


def test_config_version_snapshots_store_ref_not_value(client, seeded, db):
    from app.core.versioning import ConfigVersion

    rows = db.query(ConfigVersion).all()
    for row in rows:
        assert SECRET_VALUE not in row.snapshot_json


def test_audit_never_stores_secret(client, seeded, db):
    from app.audit.models import AuditLog

    for row in db.query(AuditLog).all():
        blob = (row.before_json or "") + (row.after_json or "")
        assert SECRET_VALUE not in blob


# ── 시크릿 파일을 쓰는 쪽 ─────────────────────────────────────────────────────
#
# 아래 둘은 `tests/integration/test_notion_console.py` 에 있었다. 그 화면이 유일한 쓰기
# 호출부였고 노션 런타임과 함께 사라졌다. 그런데 `FileSecretReferenceProvider.write()` 는
# 그대로 남아 있으므로 다음에 시크릿을 저장하는 화면이 생기면 같은 함수를 쓴다 — 그때
# 「반쯤 쓰다 만 토큰」과 「임시 파일이 남는」 두 사고를 다시 겪지 않도록 여기로 옮긴다.
# 응답에 안 새는 것을 보는 이 파일과 같은 질문의 반대편이다: 임시 파일이 남으면 다음
# 사람이 그것을 시크릿으로 읽는다.


def test_the_secret_provider_really_detects_a_directory_it_cannot_write(tmp_path):
    """`writable()` 자체가 정직한지 본다. **가짜를 꽂지 않고** 진짜 구현을 부른다.

    이 시험이 없던 시절 화면 시험만 있었고, 그 시험은 `writable` 을 통째로 가짜로 바꿔 놓고
    돌았다. 그래서 `writable()` 첫 줄에 `return True` 를 넣어도 초록불이 나왔다 - 즉 "못 쓰는
    서버를 알아본다" 는 성질을 아무도 확인하지 않고 있었다.
    """
    from app.core.secret_refs import FileSecretReferenceProvider, SecretDirNotWritableError

    assert FileSecretReferenceProvider(tmp_path).writable() is True

    missing = FileSecretReferenceProvider(tmp_path / "no-such-dir")
    assert missing.writable() is False
    with pytest.raises(SecretDirNotWritableError):
        missing.write("sweep-secret", "value")

    # 경로가 디렉터리가 아니라 파일인 설치도 실제로 있다(설치 스크립트를 반만 돌린 경우).
    as_file = tmp_path / "secrets-is-a-file"
    as_file.write_text("", encoding="utf-8")
    assert FileSecretReferenceProvider(as_file).writable() is False


def test_the_secret_write_replaces_atomically_and_leaves_no_leftovers(tmp_path):
    """덮어쓰는 도중에 읽는 쪽이 **잘린 토큰**을 보면 안 된다(그 조회는 401 이 된다).

    임시 파일 -> `os.replace` 관용을 쓴 결과로, 쓰기가 끝난 뒤 디렉터리에는 시크릿 파일
    하나만 남아야 한다. 임시 파일이 남으면 다음 사람이 그것을 시크릿으로 착각한다.
    """
    from app.core.secret_refs import FileSecretReferenceProvider

    provider = FileSecretReferenceProvider(tmp_path)
    provider.write("sweep-secret", "first-token")
    provider.write("sweep-secret", "second-token")

    assert provider.get("sweep-secret").reveal() == "second-token"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["sweep-secret"]
