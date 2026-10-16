# qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
"""저장소 설정 API — 「업로드가 어디로 가는가」에 답이 하나여야 한다 (S8 · D-199).

qa-contract-change: 생성 응답의 계약을 200 에서 201 로 바꿨다(S-10) — 같은 콘솔의 다른
생성 라우트(공지·사용자)가 이미 201 을 내는데 저장소만 기본값 200 이라, 상태 코드로
「만들어졌다」를 구별하는 클라이언트에게 이 라우트만 예외였다. 기존 단언을 지우지 않고
기대값만 새 계약으로 옮기고, 아래에 그 계약을 직접 세우는 시험을 함께 둔다.

## 이 파일이 지키는 것 넷

1. **역할마다 켜진 저장소는 하나다.** 둘이면 어제 올린 파일과 오늘 올린 파일이 다른
   장치에 있고, 그 사실은 백업을 복원할 때 처음 드러난다.
2. **마운트가 안 붙었으면 그렇다고 말한다.** 「설정이 있다」와 「지금 쓸 수 있다」는
   다른 사실이고, 화면이 그 둘을 같은 것으로 보여 주면 아무도 안 붙은 것을 모른다.
3. **운영과 백업이 같은 장치면 경고한다.** 그 백업은 장치가 죽는 순간 함께 죽는다.
4. **거절은 정직한 4xx 다.** 이름 중복·공백뿐인 이름·경합은 관리자의 실수이거나 순서
   문제이지 서버 고장이 아니다. 500 으로 답하면 관리자는 자기 입력이 틀린 것인지
   제품이 깨진 것인지 구별할 수 없다(XB-01 · XD-03 · S-01 · S-02).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.fakes.pgerrors import foreign_key_violation, unique_violation

from app.core.db import make_engine, make_session_factory
from app.core.errors import ConflictError, ValidationAppError
from app.storage import service
from app.storage.models import StorageProvider

pytestmark = pytest.mark.integration


@pytest.fixture()
def local_provider(db, settings):
    provider = service.ensure_default_provider(db, settings)
    db.commit()
    return provider


# ── 권한 ─────────────────────────────────────────────────────────────────────


def test_a_normal_user_cannot_see_the_storage_settings(client, login_as, local_provider):
    """목록은 경로·마운트 소스·용량을 담는다. 그것만으로도 서버 구조가 드러난다."""
    login_as("user")
    assert client.get("/api/storage/providers").status_code == 403
    assert client.get("/api/storage/status").status_code == 403


def test_a_system_admin_can_see_them(client, login_as, local_provider):
    login_as("system_admin")
    response = client.get("/api/storage/providers")
    assert response.status_code == 200, response.text
    names = [i["name"] for i in response.json()["items"]]
    assert local_provider.name in names


def test_an_operator_cannot_change_where_files_land(client, login_as, local_provider):
    """`STORAGE_CONFIGURE` 는 `SYSTEM_ADMIN_ONLY` 다(S5 가 그렇게 고정했다)."""
    csrf = login_as("operator")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "몰래", "kind": "LOCAL", "role": "OPERATIONAL",
            "base_path": "/tmp/somewhere",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("role", ["user", "operator", "admin", "auditor"])
def test_only_the_system_admin_can_touch_a_provider(client, login_as, local_provider, role):
    """화면에서 버튼을 감춘 것과 서버가 막는 것은 다른 사실이다 (S20).

    S20 이 이 API 의 **첫 화면**(설정 → 파일 저장소)을 세우면서 세 쓰기 동작(추가·수정·
    지금 확인)이 처음으로 사람 손에 닿았다. 그 화면은 `system_admin` 에게만 탭을 보이지만
    그것은 표시일 뿐이라(불변규칙 §5) 나머지 역할이 주소를 직접 불러도 막히는지를 여기서
    센다 — 셋 다 `STORAGE_CONFIGURE`(SYSTEM_ADMIN_ONLY) 하나를 지난다.
    """
    csrf = login_as(role)
    headers = {"X-CSRF-Token": csrf}
    pid = local_provider.id

    assert client.get("/api/storage/status").status_code == 403 if role == "user" else True
    assert client.patch(
        f"/api/storage/providers/{pid}", json={"enabled": False}, headers=headers
    ).status_code == 403
    assert client.post(
        f"/api/storage/providers/{pid}/probe", json={}, headers=headers
    ).status_code == 403


def test_the_system_admin_actually_can(client, login_as, local_provider):
    """반례 — 위 넷이 403 인 이유가 «아무도 못 한다» 가 아님을 같은 자리에서 보인다."""
    csrf = login_as("system_admin")
    headers = {"X-CSRF-Token": csrf}
    pid = local_provider.id

    assert client.post(
        f"/api/storage/providers/{pid}/probe", json={}, headers=headers
    ).status_code == 200
    response = client.patch(
        f"/api/storage/providers/{pid}", json={"name": "이름을 바꿨다"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "이름을 바꿨다"


# ── 상태 ─────────────────────────────────────────────────────────────────────


def test_a_local_provider_reports_itself_writable(client, login_as, local_provider):
    login_as("system_admin")
    item = client.get("/api/storage/providers").json()["items"][0]
    assert item["writable"] is True
    assert item["mount"]["status"] == "ok"
    assert item["total_bytes"] is None or item["total_bytes"] > 0


def test_a_remote_provider_that_is_not_mounted_says_so(client, login_as, db, tmp_path):
    """🔴 「설정이 있다」와 「지금 쓸 수 있다」는 다른 사실이다."""
    mountpoint = tmp_path / "nas"
    mountpoint.mkdir()
    db.add(StorageProvider(
        name="붙지 않은 NAS", kind="NFS", role="BACKUP",
        base_path=mountpoint.as_posix(), mount_point=mountpoint.as_posix(),
        config_json='{"source": "nas:/export"}',
    ))
    db.commit()

    login_as("system_admin")
    items = {i["name"]: i for i in client.get("/api/storage/providers").json()["items"]}
    nas = items["붙지 않은 NAS"]
    assert nas["writable"] is False
    assert nas["mount"]["status"] == "not_mounted"
    assert "로컬 디스크" in nas["mount"]["detail"]


def test_the_probe_tells_the_admin_which_unit_to_start(client, login_as, db, tmp_path):
    """안 붙어 있을 때 관리자가 다음에 칠 명령이 `systemctl start <그 유닛>` 이다."""
    mountpoint = tmp_path / "smb"
    mountpoint.mkdir()
    provider = StorageProvider(
        name="SMB 공유", kind="SMB", role="BACKUP",
        base_path=mountpoint.as_posix(), mount_point=mountpoint.as_posix(),
        config_json='{"source": "//nas/share"}',
    )
    db.add(provider)
    db.commit()

    csrf = login_as("system_admin")
    response = client.post(
        f"/api/storage/providers/{provider.id}/probe", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200, response.text
    assert response.json()["mount_unit"].endswith(".mount")


# ── 만들기와 고치기 ──────────────────────────────────────────────────────────


def test_a_second_enabled_provider_for_the_same_role_is_refused(
    client, login_as, local_provider, tmp_path
):
    """🔴 자동으로 옛것을 끄지 않는다. 업로드가 어디로 가는지 바뀌는 변경이라,
    「끄는 것」을 사람이 실제로 결정해야 한다."""
    csrf = login_as("system_admin")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "두 번째", "kind": "LOCAL", "role": "OPERATIONAL",
            "base_path": (tmp_path / "other").as_posix(),
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 409, response.text
    assert local_provider.name in response.json()["error"]["message"]


def test_a_backup_provider_can_stand_next_to_the_operational_one(
    client, login_as, local_provider, tmp_path
):
    """반대쪽. 전부 거절하는 검사도 위 시험은 통과한다."""
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    csrf = login_as("system_admin")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "백업 저장소", "kind": "LOCAL", "role": "BACKUP",
            "base_path": backup_dir.as_posix(),
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "BACKUP"


def test_a_remote_provider_without_a_mountpoint_is_refused_with_a_reason(
    client, login_as, local_provider
):
    """DB CHECK 에만 맡기면 사용자는 500 을 보고 무엇이 틀렸는지 알 수 없다."""
    csrf = login_as("system_admin")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "마운트 없는 NFS", "kind": "NFS", "role": "BACKUP",
            "base_path": "/mnt/nas/files",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text
    assert "마운트 지점" in response.json()["error"]["message"]


def test_a_write_path_outside_the_mountpoint_is_refused(client, login_as, local_provider):
    """🔴 가드가 물어보는 자리와 실제로 쓰는 자리가 다르면, 마운트가 붙어 있어도
    로컬 디스크에 쌓인다."""
    csrf = login_as("system_admin")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "엇갈린 경로", "kind": "NFS", "role": "BACKUP",
            "base_path": "/var/lib/elsewhere", "mount_point": "/mnt/nas",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text
    assert "마운트 지점 아래" in response.json()["error"]["message"]


def test_updating_a_provider_takes_the_optimistic_lock(client, login_as, local_provider):
    """S6 이 정한 규약 그대로다(D-240). 같은 충돌을 자원마다 다른 이름으로 다루면
    프런트가 여러 벌의 처리를 갖게 된다."""
    csrf = login_as("system_admin")
    stale = local_provider.version
    ok = client.patch(
        f"/api/storage/providers/{local_provider.id}",
        json={"name": "이름 변경", "base_version": stale},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 200, ok.text

    conflict = client.patch(
        f"/api/storage/providers/{local_provider.id}",
        json={"name": "덮어쓰기", "base_version": stale},
        headers={"X-CSRF-Token": csrf},
    )
    assert conflict.status_code == 409


# ── 운영과 백업이 같은 장치 (D-199 16번) ─────────────────────────────────────


def test_the_same_device_for_both_roles_is_a_warning(client, login_as, db, settings, tmp_path):
    """그 백업은 장치가 죽는 순간 함께 죽는다. 「백업이 있다」가 거짓이 되는 유일한 경우다."""
    service.ensure_default_provider(db, settings)
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    db.add(StorageProvider(
        name="같은 디스크 백업", kind="LOCAL", role="BACKUP",
        base_path=backup_dir.as_posix(),
    ))
    db.commit()

    login_as("system_admin")
    body = client.get("/api/storage/providers").json()
    assert body["warning"] is not None
    assert "같은 장치" in body["warning"]


def test_with_no_backup_provider_there_is_no_warning(client, login_as, local_provider):
    """경고를 늘 켜 두면 사람이 안 읽는다."""
    login_as("system_admin")
    assert client.get("/api/storage/providers").json()["warning"] is None


# ── 거절은 정직한 4xx 다 (XB-01 · XD-03 · S-01 · S-02 · S-10) ────────────────


def _create(client, csrf, **overrides) -> "object":
    body = {
        "name": "이름 하나", "kind": "LOCAL", "role": "BACKUP",
        "base_path": "/srv/clovir/backup", "enabled": False,
    }
    body.update(overrides)
    return client.post(
        "/api/storage/providers", json=body, headers={"X-CSRF-Token": csrf}
    )


def test_creating_a_provider_answers_201(client, login_as, local_provider):
    """S-10: 만들었으면 201 이라고 말한다 — 공지·사용자 생성과 같은 계약이다."""
    csrf = login_as("system_admin")
    response = _create(client, csrf, name="201 저장소", base_path="/srv/clovir/two-oh-one")
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "201 저장소"


def test_a_duplicate_provider_name_is_a_conflict_not_a_500(client, login_as, local_provider):
    """🔴 XB-01 · XD-03: 이미 쓰는 이름은 관리자의 흔한 실수다. 그 답이 500 이면
    관리자는 자기 입력이 틀린 것인지 서버가 깨진 것인지 알 수 없다."""
    csrf = login_as("system_admin")
    assert _create(client, csrf, name="사내 NAS", base_path="/srv/nas/a").status_code == 201

    again = _create(client, csrf, name="사내 NAS", base_path="/srv/nas/b")
    assert again.status_code == 409, again.text
    assert "이미 있는 저장소 이름입니다" in again.json()["error"]["message"]


def test_a_name_that_differs_only_in_case_is_the_same_name(client, login_as, local_provider):
    """'nas' 와 'NAS' 는 사람 눈에 같은 저장소다 — 목록에서 둘을 구별할 방법이 없다.
    부서·직책이 쓰는 판정과 같다(app/org/service.py::find_by_name)."""
    csrf = login_as("system_admin")
    assert _create(client, csrf, name="nas-one", base_path="/srv/nas/one").status_code == 201

    upper = _create(client, csrf, name="NAS-ONE", base_path="/srv/nas/two")
    assert upper.status_code == 409, upper.text


def test_a_different_name_still_goes_through(client, login_as, local_provider):
    """반례 — 위 둘이 409 인 이유가 «생성이 막혔다» 가 아님을 같은 자리에서 보인다."""
    csrf = login_as("system_admin")
    assert _create(client, csrf, name="이름 A", base_path="/srv/nas/a").status_code == 201
    assert _create(client, csrf, name="이름 B", base_path="/srv/nas/b").status_code == 201


def test_renaming_onto_an_existing_name_is_a_conflict_not_a_500(
    client, login_as, local_provider
):
    """이름 바꾸기도 같은 유니크 인덱스를 지난다 — 생성만 고치면 절반이 남는다."""
    csrf = login_as("system_admin")
    created = _create(client, csrf, name="바꿀 저장소", base_path="/srv/nas/rename")
    assert created.status_code == 201, created.text

    clash = client.patch(
        f"/api/storage/providers/{created.json()['id']}",
        json={"name": local_provider.name},
        headers={"X-CSRF-Token": csrf},
    )
    assert clash.status_code == 409, clash.text
    assert "이미 있는 저장소 이름입니다" in clash.json()["error"]["message"]


def test_renaming_to_its_own_name_is_not_a_conflict(client, login_as, local_provider):
    """반례 — 자기 이름은 「이미 있는 이름」이 아니다. 이 반례가 없으면 위 시험은
    «모든 이름 변경을 막는» 구현으로도 통과한다."""
    csrf = login_as("system_admin")
    response = client.patch(
        f"/api/storage/providers/{local_provider.id}",
        json={"name": local_provider.name},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == local_provider.name


@pytest.mark.parametrize("blank", ["   ", "\t", "\n\n"])
def test_a_whitespace_only_name_is_422_not_a_db_check_500(
    client, login_as, local_provider, blank
):
    """🔴 S-01: `Field(min_length=1)` 은 strip 하기 전 길이를 본다. 그래서 공백뿐인
    이름이 검사를 지나 DB CHECK(`ck_sprov_name_nonempty`)에서 처음 막혔고, 사용자가
    본 것은 500 이었다."""
    csrf = login_as("system_admin")
    response = _create(client, csrf, name=blank, base_path="/srv/nas/blank")
    assert response.status_code == 422, response.text
    assert "저장소 이름" in response.json()["error"]["message"]


def test_a_whitespace_only_rename_is_also_422(client, login_as, local_provider):
    csrf = login_as("system_admin")
    response = client.patch(
        f"/api/storage/providers/{local_provider.id}",
        json={"name": "   "},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text


def test_a_name_with_surrounding_spaces_is_stored_trimmed(client, login_as, local_provider):
    """반례 — 공백을 가진 정상 이름은 거절이 아니라 정규화다. 검증한 형태와 저장한
    형태가 같아야 목록·감사 로그가 같은 문자열을 말한다."""
    csrf = login_as("system_admin")
    response = _create(client, csrf, name="  공백 낀 이름  ", base_path="/srv/nas/trim")
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "공백 낀 이름"


# ── 낙관적 잠금은 값을 얻을 수 있어야 쓸 수 있다 (S-07) ──────────────────────


def test_the_read_response_carries_the_version_the_lock_needs(
    client, login_as, local_provider
):
    """🔴 S-07: 서버는 `base_version` 을 받아 낡은 쓰기를 409 로 막는데, 읽기 응답에
    `version` 이 없어서 클라이언트가 보낼 값을 얻을 방법이 없었다 — 잠금이 있는데
    아무도 못 쓰는 상태였고, 결과는 나중 저장이 앞 저장을 말없이 덮는 것이었다."""
    login_as("system_admin")
    row = client.get("/api/storage/providers").json()["items"][0]
    assert row["version"] == local_provider.version


def test_the_version_from_the_list_actually_locks(client, login_as, local_provider):
    """읽은 값을 그대로 돌려보내면 저장되고, 그 사이 남이 저장했으면 409 다."""
    csrf = login_as("system_admin")
    row = client.get("/api/storage/providers").json()["items"][0]

    first = client.patch(
        f"/api/storage/providers/{row['id']}",
        json={"options": "rw", "base_version": row["version"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 200, first.text
    assert first.json()["version"] == row["version"] + 1

    stale = client.patch(
        f"/api/storage/providers/{row['id']}",
        json={"options": "ro", "base_version": row["version"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert stale.status_code == 409, stale.text


# ── 경합도 같은 답이어야 한다 (S-02 · XD-03) ─────────────────────────────────


def test_a_lost_name_race_gets_the_same_409_as_a_late_request(db, local_provider, monkeypatch):
    """사전 검사와 INSERT 사이에는 잠금이 없다. 진 쪽이 유니크 인덱스에 걸렸을 때
    답이 「이미 있습니다」에서 「서버 오류」로 바뀌면 안 된다 — 순서만 조금 달랐을 뿐이다."""
    def _flush_that_loses(*_args, **_kwargs):
        raise unique_violation("INSERT INTO storage_providers", constraint="uq_sprov_name")

    monkeypatch.setattr(db, "flush", _flush_that_loses)
    with pytest.raises(ConflictError) as caught:
        service.create_provider(
            db, name="경합 이름", kind="LOCAL", role="BACKUP",
            base_path="/srv/nas/race", enabled=False,
        )
    assert "이미 있는 저장소 이름입니다" in str(caught.value)


def test_a_lost_role_race_gets_the_same_409_as_a_late_request(db, local_provider, monkeypatch):
    """역할 점유도 같다 — 「저장」 더블클릭 한 번이 이 경로다."""
    def _flush_that_loses(*_args, **_kwargs):
        raise unique_violation(
            "INSERT INTO storage_providers", constraint="uq_sprov_role_enabled"
        )

    monkeypatch.setattr(db, "flush", _flush_that_loses)
    with pytest.raises(ConflictError) as caught:
        service.create_provider(
            db, name="경합 역할", kind="LOCAL", role="BACKUP",
            base_path="/srv/nas/role-race", enabled=True,
        )
    assert "이미 활성화된 저장소가 있습니다" in str(caught.value)


def test_a_lost_rename_race_gets_the_same_409_as_a_late_request(db, local_provider, monkeypatch):
    """수정 경로도 같은 인덱스를 지난다 — 생성만 감싸면 이름 바꾸기가 그대로 500 이다."""
    def _flush_that_loses(*_args, **_kwargs):
        raise unique_violation("UPDATE storage_providers", constraint="uq_sprov_name")

    monkeypatch.setattr(db, "flush", _flush_that_loses)
    with pytest.raises(ConflictError) as caught:
        service.update_provider(db, local_provider, name="경합 이름")
    assert "이미 있는 저장소 이름입니다" in str(caught.value)


def test_a_foreign_key_violation_is_not_swallowed_as_a_conflict(db, local_provider, monkeypatch):
    """반례 — 이름을 아는 두 유니크 제약만 접는다. FK·CHECK·NOT NULL 위반은 「다시
    하면 된다」가 아니라 코드가 틀렸다는 뜻이라 그대로 올려보낸다(D-191)."""
    from sqlalchemy.exc import IntegrityError

    def _flush_that_breaks(*_args, **_kwargs):
        raise foreign_key_violation("INSERT INTO storage_providers")

    monkeypatch.setattr(db, "flush", _flush_that_breaks)
    with pytest.raises(IntegrityError):
        service.create_provider(
            db, name="깨진 참조", kind="LOCAL", role="BACKUP",
            base_path="/srv/nas/fk", enabled=False,
        )


def test_a_blank_name_never_reaches_the_database(db, local_provider):
    """서비스가 경계다 — CLI(`app/cli/storage_cli.py`)도 이 함수를 그대로 부른다."""
    with pytest.raises(ValidationAppError):
        service.create_provider(
            db, name="   ", kind="LOCAL", role="BACKUP",
            base_path="/srv/nas/blank", enabled=False,
        )


@pytest.mark.real_db
def test_eight_concurrent_creates_leave_exactly_one_enabled_provider(db_url, settings):
    """🔴 S-02: 실제 커넥션 여덟 개로 같은 역할을 동시에 켠다. 예전에는 하나가 200,
    나머지가 500 이었다 — 지금은 하나만 성공하고 나머지는 ConflictError 다."""
    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            service.ensure_default_provider(db, settings)
            db.commit()
    finally:
        engine.dispose()

    def attempt(index: int):
        engine = make_engine(db_url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                try:
                    row = service.create_provider(
                        db, name=f"동시 백업 {index}", kind="LOCAL", role="BACKUP",
                        base_path=f"/srv/nas/concurrent-{index}", enabled=True,
                    )
                    db.commit()
                    return ("ok", row.id)
                except ConflictError:
                    db.rollback()
                    return ("conflict", None)
                except Exception as exc:  # noqa: BLE001 — 무엇이 샜는지 이름으로 남긴다
                    db.rollback()
                    return ("leaked", type(exc).__name__)
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))

    leaked = [r for r in results if r[0] == "leaked"]
    assert leaked == [], f"경합에서 처리 안 된 예외가 샜다: {leaked}"
    assert len([r for r in results if r[0] == "ok"]) == 1, results

    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            from sqlalchemy import func, select

            enabled = db.execute(
                select(func.count()).select_from(StorageProvider).where(
                    StorageProvider.role == "BACKUP", StorageProvider.enabled.is_(True)
                )
            ).scalar_one()
            assert enabled == 1, f"경합 뒤 켜진 백업 저장소가 {enabled}개다"
    finally:
        engine.dispose()


@pytest.mark.real_db
def test_eight_concurrent_creates_with_the_same_name_leave_one_row(db_url, settings):
    """이름 경합도 같다 — 직렬이면 409 인데 동시에는 500 이던 자리다(XD-03)."""
    def attempt(_index: int):
        engine = make_engine(db_url)
        factory = make_session_factory(engine)
        try:
            with factory() as db:
                try:
                    row = service.create_provider(
                        db, name="같은 이름", kind="LOCAL", role="BACKUP",
                        base_path=f"/srv/nas/same-{_index}", enabled=False,
                    )
                    db.commit()
                    return ("ok", row.id)
                except ConflictError:
                    db.rollback()
                    return ("conflict", None)
                except Exception as exc:  # noqa: BLE001
                    db.rollback()
                    return ("leaked", type(exc).__name__)
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))

    leaked = [r for r in results if r[0] == "leaked"]
    assert leaked == [], f"경합에서 처리 안 된 예외가 샜다: {leaked}"
    assert len([r for r in results if r[0] == "ok"]) == 1, results

    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            from sqlalchemy import func, select

            count = db.execute(
                select(func.count()).select_from(StorageProvider).where(
                    StorageProvider.name == "같은 이름"
                )
            ).scalar_one()
            assert count == 1, f"경합 뒤 같은 이름의 저장소가 {count}개 남았다"
    finally:
        engine.dispose()
