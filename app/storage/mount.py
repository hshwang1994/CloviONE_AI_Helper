"""마운트 판정 — 「지금 이 경로가 진짜 그 저장소인가」에 답하는 **한 곳** (D-199 13번).

## 이 파일이 존재하는 이유

가장 조용한 저장소 사고는 **마운트가 안 붙은 채로 파일이 쌓이는 것**이다. NFS 서버가
안 떠 있으면 `/var/lib/clovirassist/files/nas` 는 사라지지 않는다 — 그냥 **로컬 디스크의
빈 디렉터리**로 남는다. 앱은 거기에 잘 쓰고, 사용자는 잘 올렸다는 화면을 보고, 체크섬도
맞고, 며칠 뒤 마운트가 붙는 순간 그 파일들이 **한꺼번에 안 보이게 된다.** 오류는 한 번도
나지 않는다.

그래서 쓰기 전에 「마운트됐는가」를 반드시 묻고, 아니면 **쓰기를 거부**한다.

## 판정은 두 벌이 아니다

`st_dev` 비교와 `/proc/self/mountinfo` 조회가 **둘 다** 필요하지만, 그 둘을 합쳐 답을
내는 함수는 `mount_state()` 하나다. 판정이 두 곳이면 그중 하나가 빠진 날 로컬 디스크에
조용히 쌓인다 — `scripts/check_domain_single_source.py` 가 이 규칙을 지킨다.

  * **`/proc/self/mountinfo`**: Linux 에서는 이쪽이 정본이다. 「이 경로가 마운트포인트
    자체인가」와 「무슨 파일시스템인가」를 함께 답한다.
  * **`st_dev` 대 부모의 `st_dev`**: 어디서나 돈다. mountinfo 를 못 읽는 환경(개발용
    Windows · 축소된 컨테이너)에서 이쪽이 답한다.

둘이 어긋나면 **mountinfo 를 믿는다.** bind mount 는 원본과 `st_dev` 가 같아서 `st_dev`
비교만으로는 「안 붙었다」로 보이지만, mountinfo 에는 분명히 있다.

## 여기서 쓰기를 하지 않는다

이 파일은 **묻기만** 한다. 실제 저장은 `app/storage/adapters.py` 가 하고, 그쪽은 쓰기
전에 반드시 이 파일에 묻는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: 마운트 판정 결과. 사람이 읽는 문장은 `MountState.detail` 이 든다.
MOUNT_OK = "ok"
MOUNT_MISSING = "missing"            # 경로 자체가 없다
MOUNT_NOT_DIR = "not_dir"            # 있는데 디렉터리가 아니다
MOUNT_NOT_MOUNTED = "not_mounted"    # 있고 디렉터리인데 **아무것도 안 붙어 있다**
MOUNT_WRONG_FSTYPE = "wrong_fstype"  # 붙어 있는데 기대한 종류가 아니다
MOUNT_UNREADABLE = "unreadable"      # stat 자체가 실패했다(권한·응답 없음)

MOUNTINFO = "/proc/self/mountinfo"


@dataclass(frozen=True)
class MountState:
    """한 경로의 마운트 상태. **숫자를 그대로 들고 다닌다** — 증거 로그가 이걸 적는다.

    `status` 가 `MOUNT_OK` 가 아니면 그 경로에는 쓰지 않는다. 「아마 괜찮을 것」이라는
    판단을 호출부가 따로 하지 못하게 불리언 하나로 좁혀 둔다(`ok`).
    """

    status: str
    path: str
    st_dev: int | None = None
    parent_st_dev: int | None = None
    fstype: str | None = None
    source: str | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == MOUNT_OK

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "path": self.path,
            "st_dev": self.st_dev,
            "parent_st_dev": self.parent_st_dev,
            "fstype": self.fstype,
            "source": self.source,
            "detail": self.detail,
        }


def device_of(path: str | Path) -> int | None:
    """그 경로가 올라앉은 장치 번호. stat 이 실패하면 None."""
    try:
        return os.stat(str(path)).st_dev
    except OSError:
        return None


def read_mountinfo(text: str | None = None) -> list[tuple[str, str, str]]:
    """`(mountpoint, fstype, source)` 목록. Linux 밖이거나 못 읽으면 빈 목록.

    `text` 를 주면 그 내용을 파싱한다 — 시험이 known good / known bad 를 넣는 자리다.
    필드 수가 가변이라(선택 필드가 `-` 앞에 온다) `-` 를 기준으로 나눈다.
    """
    if text is None:
        try:
            text = Path(MOUNTINFO).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
    out: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        if " - " not in line:
            continue
        left, right = line.split(" - ", 1)
        lf = left.split()
        rf = right.split()
        if len(lf) < 5 or len(rf) < 2:
            continue
        # 마운트포인트에는 공백이 `\040` 으로 들어온다.
        out.append((_unescape(lf[4]), rf[0], _unescape(rf[1])))
    return out


def _unescape(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def mountinfo_entry(path: str | Path, *, text: str | None = None) -> tuple[str, str] | None:
    """그 경로가 **마운트포인트 자체**면 `(fstype, source)`, 아니면 None.

    부모가 마운트포인트인 것은 여기서 True 가 아니다 — 우리가 묻는 것은 「이 자리에
    무언가 붙었는가」이지 「이 파일이 어느 파일시스템에 있는가」가 아니다.
    """
    target = os.path.normpath(str(path))
    for mountpoint, fstype, source in read_mountinfo(text):
        if os.path.normpath(mountpoint) == target:
            return fstype, source
    return None


def mount_state(
    path: str | Path,
    *,
    require_mount: bool,
    expect_fstypes: tuple[str, ...] = (),
    mountinfo_text: str | None = None,
) -> MountState:
    """그 경로에 지금 써도 되는지 판정한다. **쓰기 전에 반드시 지난다.**

    `require_mount=False`(LOCAL)는 「디렉터리로 있으면 된다」이고,
    `require_mount=True`(NFS/SMB)는 「그 자리에 실제로 무언가 붙어 있어야 한다」이다.
    """
    p = str(path)
    st_dev = device_of(p)
    if st_dev is None:
        if not os.path.exists(p):
            return MountState(MOUNT_MISSING, p, detail="경로가 없습니다.")
        return MountState(MOUNT_UNREADABLE, p, detail="경로 상태를 읽을 수 없습니다.")
    if not os.path.isdir(p):
        return MountState(MOUNT_NOT_DIR, p, st_dev=st_dev, detail="디렉터리가 아닙니다.")

    parent_dev = device_of(os.path.dirname(os.path.normpath(p)) or "/")
    entry = mountinfo_entry(p, text=mountinfo_text)
    fstype = entry[0] if entry else None
    source = entry[1] if entry else None

    if not require_mount:
        return MountState(
            MOUNT_OK, p, st_dev=st_dev, parent_st_dev=parent_dev,
            fstype=fstype, source=source, detail="로컬 디렉터리입니다.",
        )

    # mountinfo 를 읽을 수 있으면 그쪽이 정본이다. bind mount 는 원본과 `st_dev` 가
    # 같아서 장치 비교만으로는 「안 붙었다」로 보인다.
    has_mountinfo = bool(read_mountinfo(mountinfo_text))
    if has_mountinfo:
        mounted = entry is not None
    else:
        mounted = parent_dev is not None and st_dev != parent_dev

    if not mounted:
        return MountState(
            MOUNT_NOT_MOUNTED, p, st_dev=st_dev, parent_st_dev=parent_dev,
            detail="마운트되지 않았습니다. 이 자리에 쓰면 로컬 디스크에 쌓입니다.",
        )

    if expect_fstypes and fstype is not None and fstype not in expect_fstypes:
        return MountState(
            MOUNT_WRONG_FSTYPE, p, st_dev=st_dev, parent_st_dev=parent_dev,
            fstype=fstype, source=source,
            detail=f"기대한 파일시스템이 아닙니다(기대 {'/'.join(expect_fstypes)}, 실제 {fstype}).",
        )

    return MountState(
        MOUNT_OK, p, st_dev=st_dev, parent_st_dev=parent_dev,
        fstype=fstype, source=source, detail="마운트되어 있습니다.",
    )


def write_target_state(
    base_path: str | Path,
    mount_point: str | Path | None,
    *,
    require_mount: bool,
    expect_fstypes: tuple[str, ...] = (),
    mountinfo_text: str | None = None,
) -> MountState:
    """**쓰기 경로까지 포함한** 최종 판정. 저장 전에 호출하는 것은 이 함수 하나다.

    `mount_state()` 는 「마운트포인트에 무언가 붙었는가」만 답한다. 그것만으로는 부족한
    경우가 하나 있다: 마운트는 붙었는데 **그 아래 하위 디렉터리가 없어서** 앱이 새로
    만드는 경우다. 만들어진 디렉터리는 마운트 위에 있으니 문제없어 보이지만, 마운트가
    붙기 **전에** 만들어졌다면 그것은 로컬 디스크의 디렉터리이고 마운트에 덮여 보이지
    않게 된다 — 그 안의 파일도 함께 사라진 것처럼 보인다.

    그래서 `base_path` 의 장치가 마운트포인트의 장치와 같은지까지 여기서 본다.
    **판정을 두 곳에 나눠 두지 않는다**(`scripts/check_domain_single_source.py`).
    """
    guard = str(mount_point) if (require_mount and mount_point) else str(base_path)
    state = mount_state(
        guard,
        require_mount=require_mount,
        expect_fstypes=expect_fstypes,
        mountinfo_text=mountinfo_text,
    )
    if not state.ok or not require_mount or not mount_point:
        return state
    base_dev = device_of(base_path)
    if base_dev != state.st_dev:
        return MountState(
            MOUNT_NOT_MOUNTED, str(base_path),
            st_dev=base_dev, parent_st_dev=state.st_dev, fstype=state.fstype,
            source=state.source,
            detail="저장 경로가 마운트된 장치 위에 있지 않습니다.",
        )
    return state


def capacity(path: str | Path) -> dict:
    """그 경로가 올라앉은 파일시스템의 용량. 못 읽으면 값이 전부 None 이다.

    `statvfs` 가 없는 환경(Windows 개발 머신)에서도 죽지 않는다 — 이 값은 화면과
    증거 로그가 쓰는 정보이지 쓰기 가부를 정하는 값이 아니다.
    """
    statvfs = getattr(os, "statvfs", None)
    if statvfs is None:
        return {"total_bytes": None, "free_bytes": None, "used_bytes": None}
    try:
        st = statvfs(str(path))
    except OSError:
        return {"total_bytes": None, "free_bytes": None, "used_bytes": None}
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    return {"total_bytes": total, "free_bytes": free, "used_bytes": total - free}


def same_device(left: str | Path, right: str | Path) -> bool | None:
    """두 경로가 **같은 장치**인가. 한쪽이라도 못 읽으면 None(모른다).

    운영 저장소와 백업 저장소가 같은 장치면 그 백업은 장치가 죽는 순간 함께 죽는다 —
    「백업이 있다」는 사실이 거짓이 되는 유일한 경우라 경고로 말한다(D-199 16번).
    """
    a, b = device_of(left), device_of(right)
    if a is None or b is None:
        return None
    return a == b
