import pytest

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def test_dashboard_aggregates(client, login_as):
    login_as("operator")
    r = client.get("/api/admin/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["components"]["web"] == "up"
    assert body["components"]["worker"] == "unknown"  # no heartbeat yet
    assert "counts" in body and "jobs_24h" in body
    assert body["disk"]["free_gb"] is not None  # works on Windows (shutil)
    assert body["cert_days_remaining"] is None  # no cert path in dev


def test_dashboard_reflects_heartbeat(client, login_as, db, fake_clock):
    login_as("operator")
    from app.health.service import write_heartbeat

    write_heartbeat(db, "worker", fake_clock.now())
    db.commit()
    body = client.get("/api/admin/dashboard").json()
    assert body["components"]["worker"] == "up"


def test_dashboard_stale_heartbeat(client, login_as, db, fake_clock):
    login_as("operator")
    from app.health.service import write_heartbeat

    write_heartbeat(db, "scheduler", fake_clock.now())
    db.commit()
    fake_clock.advance(200)  # > 90s stale threshold
    body = client.get("/api/admin/dashboard").json()
    # A stale heartbeat reads as 'down' (spec §14.1), not a separate 'stale' state.
    assert body["components"]["scheduler"] == "down"


def test_dashboard_counts_no_longer_advertise_removed_registries(client, admin_csrf):
    """S11 이 워크플로·러너 화면을 걷어냈다. 지표가 남아 있으면 대시보드가 없는 화면으로
    가는 타일을 계속 그린다 — 눌러도 아무 데도 안 가는 숫자다."""
    counts = client.get("/api/admin/dashboard").json()["counts"]
    assert "active_workflows" not in counts
    assert "runners" not in counts
    # 살아남은 지표는 그대로다.
    assert "active_schedules" in counts


def test_backup_create_verify_and_list(client, login_as, stub_pg_dump):
    csrf = login_as("system_admin")
    r = client.post("/api/admin/backups", headers=_headers(csrf))
    assert r.status_code == 201, r.text
    backup = r.json()["backup"]
    assert backup["status"] == "verified"  # auto restore-test verified it
    assert backup["checksum"]

    listing = client.get("/api/admin/backups").json()
    assert any(b["id"] == backup["id"] for b in listing["items"])

    dashboard = client.get("/api/admin/dashboard").json()
    assert dashboard["last_backup_at"] is not None


def test_verify_downgrades_status_on_failure(db, settings, fake_clock, stub_pg_dump):
    """재검증 실패 시 상태를 failed로 낮춰야 한다(손상된 백업이 '정상'으로 남지 않도록).

    qa-contract-change: S12 부터 `path` 는 **세트 디렉터리**다. 손상시킬 대상은 그
    디렉터리가 아니라 안의 덤프 파일이다.
    """
    from app.backups.models import STATUS_FAILED
    from app.backups.service import dump_path, run_backup, verify_existing

    row = run_backup(db, settings, created_by="tester", now=fake_clock.now())
    db.commit()
    assert row.status in ("succeeded", "verified")
    dump_path(row.path).write_text("corrupted-not-an-archive")  # 파일 손상
    result = verify_existing(db, row, now=fake_clock.now(), settings=settings)
    assert result["ok"] is False
    assert row.status == STATUS_FAILED


def test_verify_refuses_a_still_running_backup(client, login_as, db, fake_clock):
    """UA-19: reap_stuck_running()의 문서화된 계약("검증도 running을 제외한다")을 이
    엔드포인트 자체가 어기고 있었다. running 행을 체크섬 검증하면 아직 다 안 쓰인 파일을
    보고 판단해, 실제로는 정상적으로 진행 중인 백업을 failed로 격하시킬 수 있다."""
    from app.backups.models import STATUS_RUNNING, Backup

    row = Backup(backup_type="manual", path="/tmp/clv-still-running.sqlite3",
                 status=STATUS_RUNNING, created_at=fake_clock.now())
    db.add(row)
    db.commit()
    backup_id = row.id

    csrf = login_as("system_admin")
    r = client.post(f"/api/admin/backups/{backup_id}/verify", headers=_headers(csrf))
    assert r.status_code == 409, f"진행 중인 백업을 검증할 수 있다: {r.status_code} {r.text}"

    db.expire_all()
    assert db.get(Backup, backup_id).status == STATUS_RUNNING, (
        "차단됐어야 할 검증이 실제로는 상태를 건드렸다"
    )


def test_retention_spares_running_and_latest_failed(db, fake_clock):
    from app.backups.models import STATUS_FAILED, STATUS_RUNNING, Backup
    from app.backups.service import apply_retention

    running = Backup(backup_type="manual", path="/tmp/clv-running.sqlite3", status=STATUS_RUNNING, created_at=fake_clock.now())
    failed = Backup(backup_type="manual", path="/tmp/clv-failed.sqlite3", status=STATUS_FAILED, created_at=fake_clock.now())
    db.add_all([running, failed])
    db.commit()
    apply_retention(db, keep=14)
    db.commit()
    ids = {b.id for b in db.query(Backup).all()}
    assert running.id in ids  # 진행 중 백업은 지우지 않는다(파일 쓰는 중일 수 있음)
    assert failed.id in ids   # 가장 최근 실패 1건은 장애 추적용으로 남긴다


def test_manual_backup_respects_configured_retention(client, login_as, db, fake_clock):
    """수동 '지금 백업' 버튼도 관리자가 설정한 보관 개수(backup_schedule.keep)를 지켜야 한다.

    예약 백업(run_scheduled_backup)은 backup_schedule.keep 을 읽어 apply_retention 에 넘기는데,
    수동 생성(POST /api/admin/backups → create_backup)은 apply_retention(db) 를 인자 없이
    불러 하드코딩된 기본값(14)을 쓴다 — 관리자가 keep 을 14 미만으로 좁혀도 수동 백업을
    누르면 정책이 지켜지지 않고 오래된 백업이 그대로 쌓인다.

    qa-contract-change: S12 가 보존에 **나이 바닥**(`keep_days`)을 더했다 — 개수와 나이를
    둘 다 넘겨야 지운다. 그래서 이 시험은 `keep_days: 0` 을 **명시적으로** 골라 개수 축만
    본다. 나이 축은 아래 `test_retention_age_floor_keeps_recent_backups` 가 따로 본다.
    둘을 한 시험에서 보면 어느 바닥이 걸렸는지 실패 메시지가 말해 주지 못한다.
    """
    from datetime import timedelta

    from app.backups.models import STATUS_VERIFIED, Backup

    csrf = login_as("system_admin")
    r = client.put(
        "/api/admin/settings/backup_schedule",
        json={"value": {"enabled": True, "cron": "0 3 * * *", "timezone": "Asia/Seoul",
                        "keep": 2, "keep_days": 0}},
        headers=_headers(csrf),
    )
    assert r.status_code == 200, r.text

    now = fake_clock.now()
    for i in range(4):
        db.add(Backup(
            backup_type="sqlite", path=f"/tmp/clv-old-{i}.sqlite3",
            status=STATUS_VERIFIED, created_at=now - timedelta(minutes=10 - i),
        ))
    db.commit()

    r = client.post("/api/admin/backups", headers=_headers(csrf))
    assert r.status_code == 201, r.text

    remaining = (
        db.query(Backup)
        .filter(Backup.status.in_(["succeeded", "verified"]))
        .count()
    )
    assert remaining == 2, (
        f"설정한 보관 개수(2)를 지키지 않고 {remaining}건이 남았다 "
        "(수동 백업이 설정된 keep 을 무시하고 기본값 14 를 쓰는 버그)"
    )


def test_backup_requires_system_admin(client, login_as):
    csrf = login_as("admin")  # admin < system_admin for backup creation
    r = client.post("/api/admin/backups", headers=_headers(csrf))
    assert r.status_code == 403


def test_restore_instructions_are_script_only(client, login_as):
    """복원은 화면이 아니라 스크립트가 한다 — 그 안내가 **실제로 존재하는 명령**을 가리켜야
    한다. 없는 스크립트 이름을 안내하면 사고 당일에야 그 사실을 안다.

    qa-contract-change: S12 가 **두 가지 되돌리기를 갈랐다**. `steps` 는 이제 「데이터를
    되돌린다」(세트 → `pg_restore`)이고, 「배포를 되돌린다」(`install.sh rollback`)는
    입력이 다른 별개라 `rollback_input` 이 진다. 둘을 한 목록에 두면 목록의 세트 경로를
    rollback 에 넣어 실패한다 — 그 혼동을 막는 것이 이 분리의 이유다.
    """
    login_as("system_admin")
    r = client.get("/api/admin/backups/restore-instructions")
    assert r.status_code == 200
    body = r.json()

    steps = str(body["steps"])
    # 데이터 복원의 실제 명령. 「파일을 제자리에 복사」 같은 SQLite 시절 문구가 아니다.
    assert "pg_restore" in steps
    assert "sha256sum -c" in steps, "세트가 적힌 그대로인지 확인하는 걸음이 빠졌다"

    # 배포 되돌리기는 별개 키에 남아 있어야 한다 — 사라지면 그 길을 아무도 못 찾는다.
    assert "install.sh rollback" in body["rollback_input"]

    # 복원 직후 검색이 비어 있는 것은 정상이라는 사실이 안내에 있어야 한다(D-270) —
    # 없으면 정상 복원을 장애로 신고하게 된다.
    assert body["scope_note"]

    # 옛 진입점 이름이 되살아나지 않는지 (R13).
    assert "clovirone" not in str(body)


def test_diagnostic_bundle_masks_and_excludes_secrets(client, login_as, settings, db):
    # Seed an integration with a secret ref + secret file; bundle must not leak it.
    (settings.secrets_dir / "diag-secret").write_text("PLAINTEXT-DIAG", encoding="utf-8")
    csrf = login_as("admin")
    client.post(
        "/api/admin/integrations",
        json={
            "name": "diag-int", "provider_type": "http_service",
            "base_url": "https://api.notion.com", "auth_type": "bearer",
            "secret_ref": "diag-secret",
        },
        headers=_headers(csrf),
    )
    r = client.get("/api/admin/diagnostics/bundle")
    assert r.status_code == 200
    assert "PLAINTEXT-DIAG" not in r.text


def test_diagnostic_bundle_does_not_mask_non_secret_setting_by_name(client, login_as):
    """`password_policy` is a non-secret policy object ({min_length, min_classes}),
    not a credential — its *name* merely contains the substring "password".
    mask_sensitive matches on key names, so masking the whole settings envelope
    (instead of just each setting's "value" sub-object) used to collapse this
    entire non-secret entry to "***", hiding min_length/min_classes from an
    operator troubleshooting via diagnostics. The real secret case (smtp's
    password_ref sub-field) must still be masked.
    """
    login_as("admin")
    r = client.get("/api/admin/diagnostics/bundle")
    assert r.status_code == 200
    settings = r.json()["settings"]

    pw_policy = settings["password_policy"]
    assert pw_policy != "***", "non-secret setting collapsed to '***' just because its name contains 'password'"
    assert pw_policy["value"] == {"min_length": 12, "min_classes": 3}
    assert pw_policy["type"] == "object"

    # The actual secret sub-field inside smtp must still be masked.
    smtp_value = settings["smtp"]["value"]
    assert smtp_value["password_ref"] == "***"


def test_auditor_can_read_dashboard(client, login_as):
    login_as("auditor")
    assert client.get("/api/admin/dashboard").status_code == 200


def test_user_cannot_read_dashboard(client, login_as):
    login_as("user")
    assert client.get("/api/admin/dashboard").status_code == 403
