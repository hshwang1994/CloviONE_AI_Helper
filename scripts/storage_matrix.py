"""Storage 16항 매트릭스 — **실 NFS/SMB 위에서** 제품 코드로 검증한다 (S8 Exit · D-199).

    sudo python3 scripts/storage_matrix.py run \
        --kind NFS --mount-point /mnt/clv-nfs --base-path /mnt/clv-nfs/files \
        --backup-path /var/backups/clv-storage-test \
        --service nfs-kernel-server --out EVIDENCE/S8/nfs.json

    sudo python3 scripts/storage_matrix.py pre-reboot  --state /var/lib/clv-storage-matrix.json \
        --mount-point /mnt/clv-nfs
    sudo reboot
    sudo python3 scripts/storage_matrix.py post-reboot --state /var/lib/clv-storage-matrix.json

## 이 하네스가 지키는 규칙 둘

**1. 제품 코드로 검증한다.** `app.storage.mount` · `app.storage.adapters` · `app.storage.units`
를 그대로 import 한다. 검증이 다른 구현을 쓰면 「제품으로 검증했다」가 거짓이 된다.
그 셋은 표준 라이브러리만 쓰므로 venv 없이도 돈다 — 그렇게 설계한 이유가 이것이다.

**2. 과장하지 않는다.** 시험 Storage 는 실 NAS 가 아니다(U9). 각 항목은 **어디서 무엇으로**
증명됐는지를 함께 적는다. 앱+DB 가 있어야 하는 항목(HTTP 지위, `files` 행)은 여기서
`by: pytest` 로 적고 그 시험 이름을 남긴다 — 여기서 통과했다고 적으면 그것이 거짓이다.

## 재부팅 항목이 두 조각인 이유

증명하려는 것이 「사람이 아무 명령도 안 쳐도 돌아온다」이기 때문이다. 한 스크립트가
재부팅을 걸고 그대로 이어서 확인하면 그 사이에 사람이 무엇을 했는지 구분할 수 없다
(`scripts/reboot_check.sh` 가 같은 이유로 같은 모양이다).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.storage import adapters  # noqa: E402
from app.storage.adapters import ProviderRef  # noqa: E402
from app.storage.mount import capacity, mount_state, same_device  # noqa: E402
from app.storage.units import DROPIN_NAME, unit_name  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PAYLOAD = b"ClovirAssist storage matrix payload \xed\x95\x9c\xea\xb8\x80 " + bytes(range(256)) * 8

#: 16항. 순서와 이름이 D-199 · MASTER_PLAN §5.3 의 목록 그대로다.
ITEMS = (
    (1, "Mount"),
    (2, "Read/Write"),
    (3, "Permission"),
    (4, "Create/Delete"),
    (5, "Checksum"),
    (6, "Capacity"),
    (7, "Storage unavailable (503, not 500)"),
    (8, "Reconnect (재시작 불필요)"),
    (9, "동작 중 장애 시 부분 파일 미커밋 + DB 행 미생성"),
    (10, "Reboot"),
    (11, "Reboot 후 자동 Mount"),
    (12, "Mount 완료 전 App 기동 (RequiresMountsFor=)"),
    (13, "잘못된 Local Path 기록 방지 (st_dev)"),
    (14, "Backup"),
    (15, "Restore"),
    (16, "운영/백업 동일 저장소 경고"),
)


class Report:
    """항목별 결과. **어디서 무엇으로 증명했는지**를 값과 함께 적는다."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.rows: dict[int, dict] = {}

    def record(self, number: int, status: str, *, by: str, detail: str, data=None) -> None:
        name = dict(ITEMS)[number]
        self.rows[number] = {
            "item": number, "name": name, "status": status,
            "by": by, "detail": detail, "data": data,
        }
        mark = {"PASS": "OK ", "FAIL": "!! ", "SKIP": "-- "}.get(status, "?? ")
        print(f"[{mark}] {number:2d}. {name} — {detail}")

    def ok(self) -> bool:
        return all(r["status"] != "FAIL" for r in self.rows.values())

    def dump(self, path: Path | None) -> None:
        payload = {
            "kind": self.kind,
            "host": os.uname().nodename if hasattr(os, "uname") else "",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "items": [self.rows.get(n, {"item": n, "name": name, "status": "MISSING"})
                      for n, name in ITEMS],
            "all_passed": self.ok(),
            # 과장하지 않는다(U9 · D-199). 이 문장은 증거 파일에 **반드시** 남는다.
            "caveat": (
                "시험 Storage 이지 실 NAS 장비가 아니다. 실 장비에서 새 결함이 나올 수 있다."
            ),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"\n증거: {path}")
        else:
            print(text)


def sh(command: str) -> tuple[int, str]:
    # `encoding=` 를 빼면 로케일로 디코드한다 — 한글이 섞인 systemd 설명에서 죽고,
    # 그러면 결과를 한 줄도 못 읽는다(`scripts/check_subprocess_encoding.py`).
    proc = subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True,
        encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def q(value: str) -> str:
    r"""셸에 넘길 값을 따옴표로 감싼다.

    🔴 `.mount` 유닛 이름에는 백슬래시가 들어간다(`mnt-clv\x2dnfs.mount`). 그대로
    문자열에 이어 붙이면 bash 가 `\x` 를 `x` 로 먹어 **다른 유닛 이름**이 되고,
    `systemctl start` 가 조용히 「그런 유닛 없음」으로 끝난다.
    """
    return shlex.quote(value)


# ── 본 검사 ──────────────────────────────────────────────────────────────────


def run(args) -> int:
    ref = ProviderRef(
        kind=args.kind, base_path=args.base_path,
        mount_point=args.mount_point, name=f"matrix-{args.kind}",
    )
    report = Report(args.kind)
    Path(args.base_path).mkdir(parents=True, exist_ok=True)

    _item_1_mount(report, ref)
    _item_2_read_write(report, ref)
    _item_3_permission(report, ref, args.as_user)
    _item_4_create_delete(report, ref)
    _item_5_checksum(report, ref)
    _item_6_capacity(report, ref)
    _item_7_unavailable(report, ref)
    _item_8_reconnect(report, ref, args.service)
    _item_9_no_partial(report, ref)
    _items_10_11_reboot(report, args)
    _item_12_requires_mounts_for(report, ref)
    _item_13_st_dev_guard(report, ref, args.service)
    _items_14_15_backup_restore(report, ref, args.backup_path)
    _item_16_same_device(report, ref, args.backup_path)

    report.dump(Path(args.out) if args.out else None)
    print("\nMATRIX_" + ("PASS" if report.ok() else "FAIL"))
    return 0 if report.ok() else 1


def _item_1_mount(report: Report, ref: ProviderRef) -> None:
    state = adapters.state_of(ref)
    unit = unit_name(ref.mount_point) if ref.mount_point else ""
    rc, active = sh(f"systemctl is-active {q(unit)}") if unit else (0, "n/a")
    status = "PASS" if state.ok else "FAIL"
    report.record(
        1, status, by="real-mount",
        detail=f"{state.status} · fstype={state.fstype} · unit={unit}({active})",
        data={"mount": state.as_dict(), "unit": unit, "unit_active": active},
    )


def _item_2_read_write(report: Report, ref: ProviderRef) -> None:
    key = adapters.new_storage_key(extension=".bin")
    try:
        adapters.write_object(ref, key, PAYLOAD)
        got = adapters.read_object(ref, key)
        ok = got == PAYLOAD
        report.record(
            2, "PASS" if ok else "FAIL", by="real-mount",
            detail=f"{len(PAYLOAD)}바이트를 쓰고 그대로 읽었다" if ok else "읽은 내용이 다르다",
            data={"key": key, "bytes": len(PAYLOAD)},
        )
    except Exception as exc:  # noqa: BLE001
        report.record(2, "FAIL", by="real-mount", detail=f"{type(exc).__name__}: {exc}")
    finally:
        _quiet_delete(ref, key)


def _item_3_permission(report: Report, ref: ProviderRef, as_user: str = "") -> None:
    """🔴 쓰기 권한을 **서비스 계정으로** 확인한다. root 로 확인하면 아무 뜻이 없다.

    OPS-01 실사고가 정확히 이 모양이었다: 디렉터리가 `root:clovirassist 750` 이라
    서비스 계정에 쓰기 비트가 없었는데, 용량도 멀쩡하고 root 로는 잘 써져서 며칠 동안
    아무도 몰랐다. 그래서 root 로 돌면서 「권한 검사 통과」라고 적으면 그것이 거짓이다.

    반례를 함께 본다. 「쓸 수 있다」만 확인하면 **모두에게 열린 저장소**도 통과한다 —
    그 상태에서는 이 항목이 아무것도 지키지 않는다.
    """
    base = Path(ref.base_path)
    stat = base.stat()
    owner = f"uid={stat.st_uid} gid={stat.st_gid} mode={oct(stat.st_mode & 0o7777)}"

    if not as_user:
        if os.geteuid() != 0:
            probe = base / adapters.TMP_DIRNAME / "perm.probe"
            try:
                probe.parent.mkdir(parents=True, exist_ok=True)
                probe.write_bytes(b"x")
                probe.unlink()
                report.record(3, "PASS", by="real-mount", detail=f"쓰기 가능 · {owner}")
            except OSError as exc:
                report.record(3, "FAIL", by="real-mount", detail=f"쓸 수 없다: {exc} · {owner}")
            return
        report.record(
            3, "SKIP", by="real-mount",
            detail=f"root 로 돌아 모드 비트가 무의미하다 · {owner}. "
                   f"--as-user <서비스계정> 을 주면 실제로 확인한다",
            data={"owner": owner},
        )
        return

    allowed = _write_as(as_user, base / adapters.TMP_DIRNAME / "perm.probe")

    # 반례는 **마운트 밖**에 만든다. 안에 만들면 파일시스템마다 뜻이 달라져서, 반례가
    # 반례 노릇을 못 한다: cifs 는 공유 안의 디렉터리 모드 비트를 강제하지 않고 마운트할
    # 때 정한 `uid`·`dir_mode` 가 전부를 결정한다(S8 실검증에서 `chmod 0700` 을 건
    # 디렉터리에 서비스 계정이 그대로 썼다). 여기서 확인하려는 것은 **탐지기가 거절을
    # 실제로 알아보는가**이고, 그것은 로컬 경로로 확인하는 것이 맞다.
    denied_dir = Path("/var/lib") / "clv-matrix-denied"
    denied_dir.mkdir(exist_ok=True)
    os.chmod(denied_dir, 0o700)
    os.chown(denied_dir, 0, 0)
    denied = _write_as(as_user, denied_dir / "should-not-happen")
    try:
        denied_dir.rmdir()
    except OSError:
        pass

    note = ""
    if ref.kind == "SMB":
        note = (" · cifs 는 공유 안의 모드 비트를 강제하지 않는다 — 접근을 정하는 것은"
                " 마운트 옵션(`uid`·`gid`·`file_mode`)이다")
    ok = allowed == "ok" and denied != "ok"
    report.record(
        3, "PASS" if ok else "FAIL", by="real-mount",
        detail=f"서비스 계정 {as_user} 이 저장 경로에 쓸 수 있고(`{allowed}`), 권한 없는 "
               f"자리는 거절된다(`{denied}`) · {owner}{note}"
        if ok else f"허용 자리={allowed} 금지 자리={denied} · {owner}{note}",
        data={"owner": owner, "as_user": as_user, "allowed": allowed, "denied": denied,
              "denied_probe_path": str(denied_dir)},
    )


def _write_as(user: str, path: Path) -> str:
    """그 계정으로 실제 파일을 만들어 본다. 결과는 `ok` 또는 오류 이름."""
    code = (
        "import pathlib, sys\n"
        f"p = pathlib.Path({str(path)!r})\n"
        "try:\n"
        "    p.parent.mkdir(parents=True, exist_ok=True)\n"
        "    p.write_bytes(b'probe')\n"
        "    p.unlink()\n"
        "    print('ok')\n"
        "except OSError as exc:\n"
        "    print(type(exc).__name__ + ':' + (exc.strerror or ''))\n"
    )
    rc, out = sh(f"runuser -u {q(user)} -- python3 -c {q(code)}")
    return (out.splitlines()[-1] if out else f"exit={rc}").strip()


def _item_4_create_delete(report: Report, ref: ProviderRef) -> None:
    key = adapters.new_storage_key(extension=".bin")
    try:
        adapters.write_object(ref, key, b"delete me")
        existed = adapters.object_exists(ref, key)
        first = adapters.delete_object(ref, key)
        second = adapters.delete_object(ref, key)
        gone = not adapters.object_exists(ref, key)
        ok = existed and first and not second and gone
        report.record(
            4, "PASS" if ok else "FAIL", by="real-mount",
            detail="만들고 지웠고, 없는 것을 다시 지우는 것은 오류가 아니다"
                   if ok else f"만듦={existed} 지움={first} 재삭제={second} 사라짐={gone}",
        )
    except Exception as exc:  # noqa: BLE001
        report.record(4, "FAIL", by="real-mount", detail=f"{type(exc).__name__}: {exc}")


def _item_5_checksum(report: Report, ref: ProviderRef) -> None:
    key = adapters.new_storage_key(extension=".bin")
    try:
        written = adapters.write_object(ref, key, PAYLOAD)
        read_back = hashlib.sha256(adapters.read_object(ref, key)).hexdigest()
        expected = hashlib.sha256(PAYLOAD).hexdigest()
        ok = written == read_back == expected
        report.record(
            5, "PASS" if ok else "FAIL", by="real-mount",
            detail=f"sha256={expected[:16]}… (쓰기·읽기·기대값 일치)" if ok
                   else f"쓰기={written[:16]} 읽기={read_back[:16]} 기대={expected[:16]}",
            data={"sha256": expected},
        )
    except Exception as exc:  # noqa: BLE001
        report.record(5, "FAIL", by="real-mount", detail=f"{type(exc).__name__}: {exc}")
    finally:
        _quiet_delete(ref, key)


def _item_6_capacity(report: Report, ref: ProviderRef) -> None:
    values = capacity(ref.base_path)
    ok = bool(values["total_bytes"]) and values["free_bytes"] is not None
    gib = (values["total_bytes"] or 0) / 2**30
    report.record(
        6, "PASS" if ok else "FAIL", by="real-mount",
        detail=f"전체 {gib:.1f} GiB · 남은 {(values['free_bytes'] or 0) / 2**30:.1f} GiB",
        data=values,
    )


def _item_7_unavailable(report: Report, ref: ProviderRef) -> None:
    """마운트가 없는 자리에서 **쓰기를 거부**하는지. HTTP 지위는 여기서 못 본다.

    503 과 500 을 가르는 것은 앱+DB 가 있어야 볼 수 있고, 그 검증은 pytest 가 든다.
    여기서 「503 확인」이라고 적으면 그것이 거짓이다.
    """
    ghost = ProviderRef(
        kind=ref.kind, base_path="/nonexistent-clv-matrix/files",
        mount_point="/nonexistent-clv-matrix", name="ghost",
    )
    try:
        adapters.write_object(ghost, adapters.new_storage_key(), b"x")
        report.record(7, "FAIL", by="real-mount", detail="없는 마운트에 썼다")
        return
    except adapters.StorageNotReady as exc:
        detail = f"거부 status={exc.state.status}"
    report.record(
        7, "PASS", by="real-mount + pytest",
        detail=f"{detail} · HTTP 503(500 아님)은 "
               f"tests/regression/test_storage_write_refusal.py 가 실제 앱으로 확인한다",
    )


def _item_8_reconnect(report: Report, ref: ProviderRef, service: str) -> None:
    """서버를 내렸다 올린 뒤, **같은 프로세스가** 다시 쓸 수 있는가."""
    if not service:
        report.record(8, "SKIP", by="real-mount", detail="--service 를 안 줘서 못 내렸다")
        return
    rc, out = sh(f"systemctl stop {q(service)}")
    if rc != 0:
        report.record(8, "FAIL", by="real-mount", detail=f"{service} 를 못 멈췄다: {out}")
        return
    time.sleep(2)
    down_key = adapters.new_storage_key(extension=".bin")
    # 시간을 재며 쓴다. 걸리는 저장소에서 하네스까지 멈추면 그 사실이 증거로 안 남는다.
    down_result, down_seconds = _try_write_bounded(ref, down_key)

    sh(f"systemctl start {q(service)}")
    for _ in range(30):
        time.sleep(1)
        if adapters.state_of(ref).ok:
            break
    up_key = adapters.new_storage_key(extension=".bin")
    up_result = _try_write(ref, up_key, PAYLOAD)
    _quiet_delete(ref, up_key)
    _quiet_delete(ref, down_key)

    # 이 항목의 판정 기준은 D-199 가 적은 그대로 **「재시작 불필요」** 다: 저장소가
    # 돌아온 뒤 **앱을 다시 띄우지 않고** 다시 쓸 수 있는가. 그것만 본다.
    #
    # 장애 중 쓰기가 몇 초 만에 돌아오는지는 **다른 성질**이고(사용자가 503 을 받기까지
    # 걸리는 시간), 여기서 그것까지 합쳐 판정하면 두 사실이 한 초록/빨강으로 뭉개진다.
    # 그래서 숫자는 재서 증거에 남기고, 판정에는 안 쓴다.
    ok = up_result == "ok"
    report.record(
        8, "PASS" if ok else "FAIL", by="real-mount",
        detail=f"{service} 재기동 뒤 **앱 재시작 없이** 다시 썼다 · 장애 중 쓰기는 "
               f"{down_seconds:.0f}초 만에 {down_result} 로 돌아왔다"
        if ok else f"재기동 후에도 못 썼다: {up_result} (장애 중={down_result})",
        data={"while_down": down_result, "while_down_seconds": round(down_seconds, 1),
              "after_restart": up_result},
    )


def _item_9_no_partial(report: Report, ref: ProviderRef) -> None:
    """커밋이 실패했을 때 **최종 이름이 안 생긴다**.

    실패를 실제로 만든다: 최종 경로 자리에 디렉터리를 미리 만들어 두면 `os.replace` 가
    EISDIR/ENOTEMPTY 로 실패한다. root 로 돌아도 재현된다 — 권한이 아니라 종류의 문제다.
    """
    key = adapters.new_storage_key(extension=".bin")
    final = adapters.object_path(ref, key)
    final.parent.mkdir(parents=True, exist_ok=True)
    final.mkdir()
    try:
        adapters.write_object(ref, key, PAYLOAD)
        report.record(9, "FAIL", by="real-mount", detail="실패해야 할 쓰기가 성공했다")
        return
    except adapters.StorageWriteFailed as exc:
        error = str(exc)[:80]
    finally:
        try:
            final.rmdir()
        except OSError:
            pass

    leftovers = list((Path(ref.base_path) / adapters.TMP_DIRNAME).glob("*.part"))
    committed = adapters.object_exists(ref, key)
    ok = not committed and not leftovers
    report.record(
        9, "PASS" if ok else "FAIL", by="real-mount + pytest",
        detail=(f"커밋 실패({error}) 후 최종 이름 없음 · 임시 파일 없음 · "
                f"DB 행 미생성은 tests/regression/test_storage_write_refusal.py 가 확인한다")
        if ok else f"최종파일={committed} 임시파일={len(leftovers)}",
    )


def _items_10_11_reboot(report: Report, args) -> None:
    """재부팅 두 항목은 **별도 단계**로만 참이 된다. 여기서는 그 결과를 읽어 온다."""
    state_path = Path(args.state) if args.state else None
    if state_path is None or not state_path.is_file():
        for number in (10, 11):
            report.record(
                number, "SKIP", by="reboot-phase",
                detail="pre-reboot / post-reboot 단계를 아직 안 돌렸다"
                       " (--state 로 결과 파일을 주면 여기에 실린다)",
            )
        return
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    verdict = saved.get("verdict", {})
    for number in (10, 11):
        row = verdict.get(str(number))
        if row is None:
            report.record(number, "SKIP", by="reboot-phase", detail="post-reboot 결과가 없다")
        else:
            report.record(number, row["status"], by="reboot-phase", detail=row["detail"],
                          data=row.get("data"))


def _item_12_requires_mounts_for(report: Report, ref: ProviderRef) -> None:
    """앱 유닛이 이 마운트를 기다리는가. **systemd 에게 직접 묻는다.**

    drop-in 파일만 보면 「깔았다」까지만 알 수 있다. 이름이 어긋나면 파일은 있는데
    systemd 는 그 마운트를 모르는 상태가 되고, 그것이 정확히 이 항목이 잡으려는 사고다.
    """
    if not ref.mount_point:
        report.record(12, "SKIP", by="real-mount", detail="로컬 저장소에는 마운트가 없다")
        return
    units, seen, missing = ("clovirassist-web", "clovirassist-worker",
                            "clovirassist-scheduler", "clovirassist-privhelper"), {}, []
    for unit in units:
        rc, out = sh(f"systemctl show {q(unit + '.service')} -p RequiresMountsFor --value")
        seen[unit] = out
        if rc != 0 or ref.mount_point not in out:
            missing.append(unit)
    installed = Path(f"/etc/systemd/system/clovirassist-web.service.d/{DROPIN_NAME}")
    if not installed.is_file():
        report.record(
            12, "SKIP", by="real-mount",
            detail=f"이 호스트에 제품이 설치돼 있지 않다(drop-in 없음). "
                   f"설치 경로는 deploy/install.sh Stage 11 이 든다",
            data={"expected_dropin": str(installed)},
        )
        return
    report.record(
        12, "PASS" if not missing else "FAIL", by="real-mount",
        detail="유닛 4종이 이 마운트를 기다린다" if not missing else f"안 기다리는 유닛: {missing}",
        data=seen,
    )


def _item_13_st_dev_guard(report: Report, ref: ProviderRef, service: str) -> None:
    """🔴 이 항목이 매트릭스의 이유다 — 마운트를 떼고 **실제로** 써 본다."""
    if not ref.mount_point:
        report.record(13, "SKIP", by="real-mount", detail="로컬 저장소에는 마운트가 없다")
        return
    before = sorted(p.name for p in Path(ref.mount_point).iterdir())
    rc, out = sh(f"umount {q(ref.mount_point)}")
    if rc != 0:
        report.record(13, "FAIL", by="real-mount", detail=f"마운트를 못 뗐다: {out}")
        return
    try:
        key = adapters.new_storage_key(extension=".bin")
        result = _try_write(ref, key, PAYLOAD)
        state = adapters.state_of(ref)
        left = sorted(p.name for p in Path(ref.mount_point).iterdir())
        refused = result.startswith("StorageNotReady")
        clean = not left
        ok = refused and clean
        report.record(
            13, "PASS" if ok else "FAIL", by="real-mount",
            detail=(f"마운트를 떼자 쓰기를 거부했고(status={state.status}) 로컬에 아무것도 "
                    f"안 남았다") if ok else f"결과={result} 남은 항목={left}",
            data={"write_result": result, "mount": state.as_dict(),
                  "local_entries": left, "entries_before_umount": before},
        )
    finally:
        sh(f"systemctl start {q(unit_name(ref.mount_point))}")
        for _ in range(30):
            time.sleep(1)
            if adapters.state_of(ref).ok:
                break


def _items_14_15_backup_restore(report: Report, ref: ProviderRef, backup_path: str) -> None:
    if not backup_path:
        for number in (14, 15):
            report.record(number, "SKIP", by="real-mount", detail="--backup-path 를 안 줬다")
        return
    Path(backup_path).mkdir(parents=True, exist_ok=True)
    backup = ProviderRef(kind="LOCAL", base_path=backup_path, name="matrix-backup")

    keys = []
    for index in range(3):
        key = adapters.new_storage_key(extension=".bin")
        adapters.write_object(ref, key, PAYLOAD + bytes([index]))
        keys.append(key)

    copied = 0
    for key in keys:
        data = adapters.read_object(ref, key)
        adapters.write_object(backup, key, data)
        if hashlib.sha256(adapters.read_object(backup, key)).hexdigest() == \
                hashlib.sha256(data).hexdigest():
            copied += 1
    report.record(
        14, "PASS" if copied == len(keys) else "FAIL", by="real-mount + pytest",
        detail=f"{copied}/{len(keys)}건을 백업 저장소로 옮기고 **다시 읽어** 체크섬을 맞췄다 · "
               f"행 기준 이관은 tests/integration/test_storage_archive.py 가 확인한다",
    )

    for key in keys:
        adapters.delete_object(ref, key)
    restored = 0
    for key in keys:
        adapters.write_object(ref, key, adapters.read_object(backup, key))
        if hashlib.sha256(adapters.read_object(ref, key)).hexdigest() == \
                hashlib.sha256(PAYLOAD + bytes([keys.index(key)])).hexdigest():
            restored += 1
    report.record(
        15, "PASS" if restored == len(keys) else "FAIL", by="real-mount + pytest",
        detail=f"{restored}/{len(keys)}건을 되돌리고 원본 체크섬과 맞췄다",
    )
    for key in keys:
        _quiet_delete(ref, key)
        _quiet_delete(backup, key)


def _item_16_same_device(report: Report, ref: ProviderRef, backup_path: str) -> None:
    if not backup_path:
        report.record(16, "SKIP", by="real-mount", detail="--backup-path 를 안 줬다")
        return
    shared = same_device(ref.base_path, backup_path)
    self_same = same_device(ref.base_path, ref.base_path)
    # 반례를 함께 본다. 「다르다」만 확인하면 **늘 다르다고 답하는 구현**도 통과한다.
    ok = self_same is True and shared is not None
    report.record(
        16, "PASS" if ok else "FAIL", by="real-mount",
        detail=(f"운영과 백업이 {'같은' if shared else '다른'} 장치다 "
                f"(자기 자신과의 비교는 True — 판정이 살아 있다)"),
        data={"same_device": shared, "self_check": self_same},
    )


# ── 재부팅 두 조각 ───────────────────────────────────────────────────────────


def pre_reboot(args) -> int:
    """재부팅 전 상태를 적어 두고 끝난다. **여기서 재부팅하지 않는다.**"""
    unit = unit_name(args.mount_point)
    state = mount_state(args.mount_point, require_mount=True)
    marker_key = adapters.new_storage_key(extension=".bin")
    ref = ProviderRef(
        kind=args.kind, base_path=args.base_path or args.mount_point,
        mount_point=args.mount_point, name="matrix-reboot",
    )
    adapters.write_object(ref, marker_key, PAYLOAD)
    rc, enabled = sh(f"systemctl is-enabled {q(unit)}")

    payload = {
        "mount_point": args.mount_point,
        "base_path": ref.base_path,
        "kind": args.kind,
        "unit": unit,
        "unit_enabled": enabled,
        "marker_key": marker_key,
        "marker_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
        "mount_before": state.as_dict(),
        "boot_id_before": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    Path(args.state).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if enabled != "enabled":
        print(f"\n⚠️ {unit} 이 enabled 가 아니다 — 재부팅 뒤 자동으로 안 붙는다", file=sys.stderr)
    print("\nPRE_REBOOT_OK — 이제 `sudo reboot` 하고, 올라온 뒤 post-reboot 를 돌린다")
    return 0


def post_reboot(args) -> int:
    """재부팅 뒤 **사람이 아무 명령도 안 친 상태**에서 확인한다."""
    saved = json.loads(Path(args.state).read_text(encoding="utf-8"))
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    rebooted = boot_id != saved["boot_id_before"]

    ref = ProviderRef(
        kind=saved["kind"], base_path=saved["base_path"],
        mount_point=saved["mount_point"], name="matrix-reboot",
    )
    state = adapters.state_of(ref)
    rc, active = sh(f"systemctl is-active {q(saved['unit'])}")
    try:
        digest = hashlib.sha256(adapters.read_object(ref, saved["marker_key"])).hexdigest()
    except Exception as exc:  # noqa: BLE001
        digest = f"read-failed: {type(exc).__name__}"
    survived = digest == saved["marker_sha256"]

    verdict = {
        "10": {
            "status": "PASS" if rebooted else "FAIL",
            "detail": (f"boot_id 가 바뀌었다 — 실제로 재부팅됐다" if rebooted
                       else "boot_id 가 그대로다 — 재부팅되지 않았다"),
            "data": {"boot_id_before": saved["boot_id_before"], "boot_id_after": boot_id},
        },
        "11": {
            "status": "PASS" if (rebooted and state.ok and survived) else "FAIL",
            "detail": (f"수동 명령 0회로 마운트가 돌아왔고(unit={active}) 재부팅 전 파일이 "
                       f"그대로다" if (state.ok and survived)
                       else f"마운트={state.status} 유닛={active} 파일확인={digest[:24]}"),
            "data": {"mount": state.as_dict(), "unit_active": active,
                     "marker_ok": survived},
        },
    }
    saved["verdict"] = verdict
    saved["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    Path(args.state).write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    for number in ("10", "11"):
        row = verdict[number]
        print(f"[{'OK ' if row['status'] == 'PASS' else '!! '}] {number}. {row['detail']}")
    _quiet_delete(ref, saved["marker_key"])
    ok = all(row["status"] == "PASS" for row in verdict.values())
    print("POST_REBOOT_" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ── 도우미 ───────────────────────────────────────────────────────────────────


def _try_write(ref: ProviderRef, key: str, payload: bytes) -> str:
    try:
        adapters.write_object(ref, key, payload)
        return "ok"
    except adapters.StorageNotReady as exc:
        return f"StorageNotReady({exc.state.status})"
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}"


def _try_write_bounded(ref: ProviderRef, key: str, seconds: int = 180) -> tuple[str, float]:
    """🔴 별도 프로세스에서 **시간을 재며** 쓴다. 결과와 걸린 초를 함께 돌려준다.

    두 가지를 동시에 해결한다:

      * `hard` 로 마운트된 NFS 는 서버가 죽으면 쓰기가 **영원히** 안 돌아온다. 같은
        프로세스에서 부르면 하네스가 거기서 멈추고, 멈춘 하네스는 결과를 한 줄도 안
        낸다 — 「걸렸다」는 사실 자체가 증거로 안 남는다.
      * `soft` 라도 **몇 초 만에** 돌아오지는 않는다. S8 실측은 30초였고 NFSv4 의
        상태 복구가 겹치면 더 걸린다. 그 숫자가 곳 「사용자가 503 을 받기까지의 시간」
        이므로, 통과/실패가 아니라 **초를 적는다.**

    상한을 60초로 두면 30~90초 사이의 정상 동작이 「영원히 걸림」으로 기록된다 —
    S8 이 실제로 한 번 그렇게 잘못 읽었다.
    """
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from app.storage import adapters\n"
        "from app.storage.adapters import ProviderRef\n"
        "ref = ProviderRef(kind=%r, base_path=%r, mount_point=%r)\n"
        "try:\n"
        "    adapters.write_object(ref, %r, b'bounded probe')\n"
        "    print('ok')\n"
        "except adapters.StorageNotReady as exc:\n"
        "    print('StorageNotReady(' + exc.state.status + ')')\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__)\n"
    ) % (str(ROOT), ref.kind, ref.base_path, ref.mount_point, key)
    began = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=seconds, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return f"timeout(>{seconds}s)", float(seconds)
    elapsed = time.time() - began
    output = (proc.stdout or proc.stderr).strip()
    return (output.splitlines()[-1] if output else f"exit={proc.returncode}"), elapsed


def _quiet_delete(ref: ProviderRef, key: str) -> None:
    """치우기는 조용히 실패해도 된다. 여기서 죽으면 **뒤 항목이 아예 안 돈다.**"""
    try:
        adapters.delete_object(ref, key)
    except Exception:  # noqa: BLE001
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="storage_matrix")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--kind", required=True, choices=["NFS", "SMB", "LOCAL"])
    run_cmd.add_argument("--mount-point", default="", dest="mount_point")
    run_cmd.add_argument("--base-path", required=True, dest="base_path")
    run_cmd.add_argument("--backup-path", default="", dest="backup_path")
    run_cmd.add_argument("--service", default="", help="공유 서버 유닛 이름(재접속 검사용)")
    # 권한은 **서비스 계정으로** 봐야 뜻이 있다. root 로 확인한 「쓸 수 있다」는
    # OPS-01 실사고를 못 잡는다.
    run_cmd.add_argument("--as-user", default="", dest="as_user",
                         help="쓰기 권한을 확인할 서비스 계정")
    run_cmd.add_argument("--state", default="", help="pre/post-reboot 결과 파일")
    run_cmd.add_argument("--out", default="")
    run_cmd.set_defaults(func=run)

    pre = sub.add_parser("pre-reboot")
    pre.add_argument("--state", required=True)
    pre.add_argument("--mount-point", required=True, dest="mount_point")
    pre.add_argument("--base-path", default="", dest="base_path")
    pre.add_argument("--kind", default="NFS", choices=["NFS", "SMB", "LOCAL"])
    pre.set_defaults(func=pre_reboot)

    post = sub.add_parser("post-reboot")
    post.add_argument("--state", required=True)
    post.set_defaults(func=post_reboot)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
