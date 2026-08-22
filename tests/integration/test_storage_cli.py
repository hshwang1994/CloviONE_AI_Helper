"""저장소 CLI — Installer Stage 11 이 부르는 바로 그 코드 (S8).

## 왜 이 시험이 필요한가

실검증 하네스(`scripts/storage_matrix.py`)는 DB 없이 돌아서 **저장소 행 → 마운트 유닛**
경로를 지나지 않는다. 그 구간이 안 닫혀 있으면 「실 NFS 에서 마운트가 붙는다」는
증거가 있어도 **제품이 그 유닛을 만들어 내는지**는 아무도 안 본 것이 된다.

Stage 11 의 계약이 종료코드다: 켜진 운영 저장소에 지금 쓸 수 있으면 `status` 가 0,
아니면 1. 설치 스크립트가 그 값을 그대로 읽는다.
"""

from __future__ import annotations

import json

import pytest

from app.cli import storage_cli
from app.storage import service
from app.storage.models import StorageProvider

pytestmark = pytest.mark.integration


@pytest.fixture()
def cli(db, settings, monkeypatch):
    """CLI 를 시험 세션 위에서 돌린다. 실제 `main()` 은 자기 엔진을 만든다."""

    def _run(command: str, **kwargs) -> tuple[int, str]:
        args = storage_cli.build_parser().parse_args(
            [command] + [str(v) for pair in kwargs.items() for v in pair]
        )
        out: list[str] = []
        monkeypatch.setattr("builtins.print", lambda *a, **k: out.append(" ".join(map(str, a))))
        try:
            code = args.func(db, settings, args)
        finally:
            monkeypatch.undo()
        return code, "\n".join(out)

    return _run


def test_bootstrap_stands_up_the_default_local_store(cli, db):
    """경로를 마이그레이션에 안 박은 이유가 이것이다 — `data_dir` 은 설치처마다 다르다."""
    code, out = cli("bootstrap")
    assert code == 0
    assert "STORAGE_BOOTSTRAP_OK" in out
    assert service.active_provider(db) is not None


def test_bootstrap_twice_does_not_make_two(cli, db):
    """설치는 몇 번이고 다시 돌 수 있어야 한다(Idempotent)."""
    cli("bootstrap")
    cli("bootstrap")
    rows = db.query(StorageProvider).all()
    assert len(rows) == 1


def test_status_exits_zero_when_the_store_is_writable(cli):
    """🔴 종료코드가 Stage 11 의 계약이다."""
    cli("bootstrap")
    code, out = cli("status")
    assert code == 0
    assert json.loads(out)["operational_ok"]


def test_status_exits_nonzero_when_the_store_is_not_mounted(cli, db, tmp_path):
    """반대편 — 여기서 0 이 나오면 설치가 「쓰기를 거부하는 상태」를 OK 로 찍는다."""
    mountpoint = tmp_path / "nas"
    mountpoint.mkdir()
    db.add(StorageProvider(
        name="안 붙은 NAS", kind="NFS", role="OPERATIONAL",
        base_path=mountpoint.as_posix(), mount_point=mountpoint.as_posix(),
        config_json='{"source": "nas:/export"}',
    ))
    db.commit()
    code, _ = cli("status")
    assert code == 1


def test_units_renders_a_mount_unit_from_the_row(cli, db, tmp_path):
    """저장소 행 → 마운트 유닛. **이 구간이 실검증 하네스가 못 지나는 자리다.**

    마운트포인트는 POSIX 경로로 둔다. 유닛 이름이 경로에서 기계적으로 나오는데
    (`systemd-escape`), Windows 절대 경로를 넣으면 이스케이프 결과에 역슬래시가 섞여
    시험 머신에서만 깨진다 — 제품이 도는 곳에는 그런 경로가 없다.
    """
    db.add(StorageProvider(
        name="사내 NAS", kind="NFS", role="OPERATIONAL",
        base_path="/mnt/testnas/files", mount_point="/mnt/testnas",
        config_json='{"source": "nas.example:/export", "options": ""}',
    ))
    db.commit()

    out_dir = tmp_path / "units"
    code, out = cli("units", **{"--out": str(out_dir)})
    assert code == 0, out
    units = sorted(p.name for p in out_dir.glob("*.mount"))
    assert len(units) == 1, units
    body = (out_dir / units[0]).read_text(encoding="utf-8")
    assert "What=nas.example:/export" in body
    assert "Where=/mnt/testnas" in body
    # S8 실검증이 만든 기본값 둘이 실제로 실린다.
    assert "soft" in body and "timeo=" in body

    dropin = (out_dir / storage_cli.DROPIN_NAME).read_text(encoding="utf-8")
    assert "RequiresMountsFor=/mnt/testnas" in dropin


def test_units_refuses_a_provider_with_no_mount_source(cli, db, tmp_path):
    """🔴 소스가 없으면 `What=` 이 빈 유닛이 깔린다 — systemd 는 그것을 조용히 무시한다."""
    db.add(StorageProvider(
        name="소스 없는 NAS", kind="NFS", role="OPERATIONAL",
        base_path="/mnt/testnas", mount_point="/mnt/testnas",
        config_json="{}",
    ))
    db.commit()
    code, _ = cli("units", **{"--out": str(tmp_path / "u")})
    assert code == 2


def test_units_with_only_local_storage_still_clears_the_dropin(cli, db, tmp_path):
    """파일을 아예 안 만들면 예전에 깔린 drop-in 이 남은 설치에서 옛 경로를 계속 기다린다."""
    cli("bootstrap")
    out_dir = tmp_path / "units"
    code, _ = cli("units", **{"--out": str(out_dir)})
    assert code == 0
    assert list(out_dir.glob("*.mount")) == []
    dropin = (out_dir / storage_cli.DROPIN_NAME).read_text(encoding="utf-8")
    assert "RequiresMountsFor=" in dropin


def test_add_provider_uses_the_same_service_the_screen_uses(cli, db, tmp_path):
    """화면 없이도 저장소를 세울 수 있어야 한다. 검증이 다른 코드를 쓰면
    「제품으로 검증했다」가 거짓이 된다."""
    backup = tmp_path / "backup"
    backup.mkdir()
    code, out = cli(
        "add-provider",
        **{"--name": "백업", "--kind": "LOCAL", "--role": "BACKUP",
           "--base-path": backup.as_posix()},
    )
    assert code == 0, out
    assert service.active_provider(db, role="BACKUP") is not None


def test_verify_reports_a_row_whose_bytes_are_gone(cli, db, settings):
    from app.storage import adapters

    provider = service.ensure_default_provider(db, settings)
    record = service.store_bytes(db, filename="a.txt", content=b"hello")
    db.commit()
    adapters.delete_object(service.ref_of(provider), record.storage_key)

    code, out = cli("verify")
    assert code == 1
    assert record.id in out
