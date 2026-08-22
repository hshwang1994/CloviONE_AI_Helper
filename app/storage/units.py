"""systemd `.mount` 유닛을 **제품이 만든다** (D-199 · INSTALLATION.md §6).

## 왜 앱이 마운트를 직접 하지 않는가

앱이 `mount(8)` 을 부르면 세 가지가 따라온다: root 권한이 필요하고(웹 유닛은 하드닝돼
있어 그것을 가질 수 없다), 재부팅 뒤 복구를 앱이 책임져야 하고, 마운트 상태가 앱의
생명주기에 묶인다. 셋 다 systemd 가 이미 하는 일이다.

그래서 **앱은 마운트포인트 경로만 안다.** 붙이고 떼는 것은 `.mount` 유닛이 하고,
재부팅 뒤 자동 복구는 `WantedBy=multi-user.target` 이 한다.

## 유닛 이름은 경로에서 나온다 — 지어내지 않는다

systemd 는 `.mount` 유닛 이름을 마운트포인트에서 **기계적으로** 정한다
(`/var/lib/x/files` → `var-lib-x-files.mount`). 이름을 우리가 따로 지으면 systemd 가
그 유닛을 그 경로의 마운트로 인정하지 않는다 — `systemctl start` 는 되는데
`RequiresMountsFor=` 가 안 걸리는, 원인을 찾기 어려운 상태가 된다.

## 앱 유닛은 마운트를 기다린다 (D-199 12번)

`RequiresMountsFor=` drop-in 을 네 유닛에 건다. 이것이 없으면 부팅 경합에서 **앱이
마운트보다 먼저 뜨고**, 그 짧은 창에 들어온 업로드가 로컬 디스크에 쌓인다. `st_dev`
가드가 그 쓰기를 거부하지만, 거부는 「사용자가 실패를 본다」이고 순서는 「실패 자체가
없다」이다. 둘 다 필요하다.
"""

from __future__ import annotations

from app.core.product import SERVICE_USER
from app.storage.adapters import ProviderRef, spec_for

#: 앱 유닛에 얹는 drop-in 파일 이름. 숫자 접두는 systemd 관례(사전순 적용)다.
DROPIN_NAME = "10-storage-mounts.conf"


def escape_path(path: str) -> str:
    """`systemd-escape --path` 와 같은 규칙. 유닛 이름의 앞 조각을 만든다.

    직접 구현하는 이유는 하나다 — 이 함수는 **설치 전에도**, 설치 스크립트가 아닌
    파이썬 쪽에서도 같은 답을 내야 한다. 두 벌이면 이름이 갈리고, 갈린 이름은
    「유닛은 있는데 마운트가 안 걸린다」로만 드러난다.
    """
    normalized = "/" + "/".join(p for p in str(path).split("/") if p and p != ".")
    if normalized == "/":
        return "-"
    body = normalized.lstrip("/")
    out: list[str] = []
    for ch in body:
        if ch == "/":
            out.append("-")
        elif ch.isalnum() or ch == "_":
            out.append(ch)
        elif ch == "-":
            out.append(r"\x2d")
        elif ch == ".":
            # 첫 글자의 `.` 만 이스케이프한다(systemd 규칙).
            out.append("." if out else r"\x2e")
        else:
            out.append("".join(rf"\x{b:02x}" for b in ch.encode("utf-8")))
    return "".join(out)


def unit_name(mount_point: str) -> str:
    """마운트포인트에 대응하는 `.mount` 유닛 이름."""
    return f"{escape_path(mount_point)}.mount"


def render_mount_unit(
    ref: ProviderRef,
    *,
    source: str,
    options: str = "",
    credentials_path: str | None = None,
    owner: str = SERVICE_USER,
) -> str:
    """NFS/SMB 마운트 유닛 본문. LOCAL 은 유닛이 없으므로 `ValueError`.

    `source` 는 `nas.example:/export` (NFS) 또는 `//nas.example/share` (SMB) 다.
    자격증명은 **파일 참조로만** 넘긴다 — 유닛 파일은 0644 로 깔리므로 비밀번호를
    여기 적으면 모든 로컬 사용자가 읽는다(CLAUDE.md §6.3).
    """
    spec = spec_for(ref.kind)
    if not spec.requires_mount or spec.mount_type is None:
        raise ValueError(f"{ref.kind} 는 마운트 유닛이 없습니다.")
    if not ref.mount_point:
        raise ValueError("마운트포인트가 필요합니다.")

    opts = [o for o in (options or "").split(",") if o.strip()]
    if credentials_path:
        opts.append(f"credentials={credentials_path}")
    opts.extend(_ownership_defaults(spec.kind, opts, owner))
    opts.extend(_timeout_defaults(spec.kind, opts))
    if not opts:
        opts = ["defaults"]
    # `_netdev` 는 「네트워크가 있어야 붙는다」는 표시다. 없으면 부팅이 네트워크보다
    # 먼저 마운트를 시도하고, 실패한 뒤 다시 시도하지 않는다.
    if "_netdev" not in opts:
        opts.append("_netdev")

    return "\n".join(
        [
            "[Unit]",
            f"Description=ClovirAssist {spec.label} ({ref.name or ref.kind})",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Mount]",
            f"What={source}",
            f"Where={ref.mount_point}",
            f"Type={spec.mount_type}",
            f"Options={','.join(opts)}",
            "TimeoutSec=30",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


#: NFS 기본 시간 제한. 5초 × 2회 재시도 ≈ 15초 안에 실패가 **돌아온다**.
NFS_TIMEO_DECISECONDS = 50
NFS_RETRANS = 2

#: SMB 파일 권한. 첨부는 남이 읽으면 안 되므로 그룹까지만 연다.
SMB_FILE_MODE = "0640"
SMB_DIR_MODE = "0750"


def _ownership_defaults(kind: str, opts: list[str], owner: str) -> list[str]:
    """🔴 SMB 는 마운트할 때 정한 uid/gid 로 **모든 파일의 주인이 고정된다.**

    S8 실검증에서 실제로 밟았다: `uid=0,gid=0` 으로 붙인 공유에서 서비스 계정이 아무것도
    못 썼다. cifs 는 `chown` 을 안 받으므로(유닉스 확장이 없으면) 고칠 방법도 없다.
    그런데 **마운트는 멀쩡하다** — `st_dev` 가드도, fstype 검사도 전부 통과한다.
    그래서 증상은 「올릴 때마다 503」뿐이고, 원인은 마운트 옵션 한 줄에 있다.

    운영자가 Linux 의 cifs 관례를 몰라도 되는 상태로 둔다. 직접 적은 값은 덮지 않는다.
    """
    if kind != "SMB":
        return []
    joined = ",".join(opts)
    extra: list[str] = []
    if "uid=" not in joined:
        extra.append(f"uid={owner}")
    if "gid=" not in joined:
        extra.append(f"gid={owner}")
    if "file_mode=" not in joined:
        extra.append(f"file_mode={SMB_FILE_MODE}")
    if "dir_mode=" not in joined:
        extra.append(f"dir_mode={SMB_DIR_MODE}")
    return extra


def _timeout_defaults(kind: str, opts: list[str]) -> list[str]:
    """🔴 NFS 기본값(`hard,timeo=600`)은 서버가 죽으면 **영원히 기다린다**.

    S8 실검증에서 실제로 밟았다: `systemctl stop nfs-kernel-server` 뒤의 쓰기 한 번이
    5분이 지나도 안 돌아왔다. 그 상태에서는 D-199 7번(「Storage unavailable 은 503 이지
    500 이 아니다」)이 **성립할 수가 없다** — 503 도 500 도 안 나가고 요청이 영영
    안 끝난다. `--workers 4` 짜리 웹이 NAS 장애 하나로 통째로 멈춘다.

    `soft` 가 보통 위험한 이유는 쓰다 만 파일이 조용히 잘리기 때문인데, **이 제품에는
    그 위험이 없다**: 임시 이름에 쓰고 `fsync` 한 뒤 `os.replace` 로 올리므로
    (`app/storage/adapters.py`), 시간 초과로 실패하면 최종 이름은 생기지 않고 DB 행도
    안 생긴다. 그래서 여기서는 `soft` 가 `hard` 보다 **엄격하게 낫다**.

    운영자가 직접 지정한 값은 덮지 않는다. `hard` 를 적었다면 그것은 판단이지 실수가
    아니다 — 대신 그 설치에서는 위 사실이 그대로 따라온다.
    """
    if kind != "NFS":
        return []
    joined = ",".join(opts)
    extra: list[str] = []
    if "soft" not in opts and "hard" not in opts:
        extra.append("soft")
    if "timeo=" not in joined:
        extra.append(f"timeo={NFS_TIMEO_DECISECONDS}")
    if "retrans=" not in joined:
        extra.append(f"retrans={NFS_RETRANS}")
    return extra


def render_dropin(mount_points: list[str]) -> str:
    """앱 유닛용 `RequiresMountsFor=` drop-in.

    마운트포인트가 없으면 **빈 지시자 한 줄**을 낸다. 파일을 아예 안 만들면 예전에
    깔린 drop-in 이 남아 있는 설치에서 옛 경로를 계속 기다리게 된다.
    """
    paths = " ".join(sorted({p for p in mount_points if p}))
    return "\n".join(
        [
            "# ClovirAssist Storage (S8, D-199 12번).",
            "# 마운트가 붙기 전에는 앱이 뜨지 않는다. 부팅 경합에서 앱이 먼저 뜨면 그 창에",
            "# 들어온 업로드가 로컬 디스크에 쌓인다.",
            "[Unit]",
            "RequiresMountsFor=",
            f"RequiresMountsFor={paths}" if paths else "",
            "",
        ]
    )
