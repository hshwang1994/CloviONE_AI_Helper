"""헬퍼가 바깥 세상(파일·프로세스)에 닿는 **유일한 통로** (§S).

## 왜 인터페이스로 감싸는가

두 가지 이유다.

① **테스트.** 액션은 "무엇을 하는가" 를 정하고, 실제 실행은 여기서만 일어난다. 그래서
   `FakeRunner` 하나로 액션 전체를 Windows 개발 머신에서 검사할 수 있다. root 없이,
   시스템을 망가뜨리지 않고. 이게 없으면 이 코드는 **영원히 검증되지 않은 채 root 로 돈다.**

② **감사 가능성.** 프로세스 실행이 코드 곳곳에 흩어져 있으면 "이 헬퍼가 무엇을 실행할 수
   있는가" 라는 질문에 답하려면 전부 읽어야 한다. 한 곳에 모여 있으면 한 곳만 읽으면 된다.

## 절대 규칙

**`shell=True` 는 이 파일에도 없고 앞으로도 없다.** argv 리스트만 받는다. 문자열 명령을
받는 문을 하나라도 열면, 검증을 아무리 촘촘히 해도 언젠가 그 문으로 값이 흘러든다.
"""

from __future__ import annotations

import errno
import os
import shutil
import subprocess  # noqa: S404 - argv 전용, shell=False 고정
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_TIMEOUT_SECONDS = 20

# 헬퍼가 실행할 수 있는 **프로그램의 전부**. argv[0] 가 여기 없으면 실행 자체를 거절한다.
# 액션 표가 이미 좁지만, 표를 고치는 사람이 실수해도 이 목록이 마지막 그물이 된다.
ALLOWED_BINARIES = frozenset({
    "/usr/bin/timedatectl",
    "/usr/bin/hostnamectl",
    "/usr/bin/systemctl",
    "/bin/systemctl",
    "/usr/sbin/nginx",
    "/usr/bin/openssl",
    "/usr/bin/hostname",
    "/usr/bin/uptime",
    "/usr/bin/df",
    # ClovirAssist 로컬 릴레이(D-551, `app/sysops/actions_mailrelay.py`). 경로는 Ubuntu 24.04 꾸러미와 랩 점검으로 확인했다.
    # 꾸러미 설치(`apt-get`)는 여기 없다 - 설치기가 한다.
    "/usr/bin/dpkg-query",
    "/usr/sbin/postfix",
    "/usr/sbin/postconf",
    "/usr/sbin/postqueue",
    "/usr/bin/journalctl",
    # 대표 주소를 바꾼 뒤 웹 서버를 몇 초 뒤에 다시 시작한다(D-573, `actions_domain.restart_argv`). 요청을 처리하는 프로세스가 자기를
    # 곧바로 재시작하면 응답을 못 보낸다 - systemd 의 일회성 타이머에 맡긴다. 인자는 `systemctl restart <관리 대상 유닛>` 하나로 고정이다.
    "/usr/bin/systemd-run",
})


@dataclass(frozen=True)
class Completed:
    """실행 결과. `argv` 를 함께 들고 있어야 감사 로그가 스스로 설명된다."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class BinaryNotAllowedError(RuntimeError):
    """액션 표가 허용 목록 밖의 프로그램을 부르려 했다. 코드 결함이지 사용자 입력 문제가 아니다."""


class Runner(Protocol):
    def run(self, argv: list[str], *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> Completed: ...

    def read_text(self, path: str) -> str | None: ...

    def write_text(self, path: str, text: str, *, mode: int = 0o644) -> None: ...

    def remove(self, path: str) -> None: ...

    def exists(self, path: str) -> bool: ...

    def copy(self, src: str, dst: str) -> bool: ...

    def chown(self, path: str, user: str, group: str, *, mode: int | None = None) -> None: ...


class RealRunner:
    """실제 시스템. **헬퍼 프로세스 안에서만** 만들어진다."""

    def run(self, argv: list[str], *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> Completed:
        if not argv:
            raise BinaryNotAllowedError("빈 명령")
        if argv[0] not in ALLOWED_BINARIES:
            raise BinaryNotAllowedError(f"허용되지 않은 프로그램: {argv[0]}")
        try:
            proc = subprocess.run(  # noqa: S603 - argv 고정, shell=False
                argv,
                shell=False,
                capture_output=True,
                text=True,
                # 🔴 인코딩을 적지 않으면 파이썬이 **로케일**로 디코드한다. 한국어 로케일
                # 서버에서 `systemctl` 이 한국어 메시지를 UTF-8 로 뱉으면 그 디코드가 터지고,
                # 예외가 리더 스레드에서 나므로 롤백 경로도 안 지난다 — root 프로세스가
                # 시스템 설정을 반쯤 바꾼 채로 죽는다. 개발 머신에서 실제로 이 예외를 봤다.
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            # 시간 초과를 예외로 올리면 롤백 경로를 지나지 않는다. 실패한 실행으로 돌려주면
            # 호출자가 평소와 같은 경로로 되돌린다.
            return Completed(tuple(argv), 124, "", f"시간이 초과됐습니다({timeout}초).")
        return Completed(tuple(argv), proc.returncode, proc.stdout or "", proc.stderr or "")

    def read_text(self, path: str) -> str | None:
        p = Path(path)
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8")

    def write_text(self, path: str, text: str, *, mode: int = 0o644) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # 같은 디렉터리에 임시로 쓰고 rename 한다. 곧바로 덮어쓰면 그 사이에 프로세스가 죽었을 때
        # **반쯤 쓰인 설정 파일**이 남고, 그 파일을 읽는 서비스가 다음 부팅에 안 뜬다.
        tmp = p.with_name(p.name + ".new")
        tmp.write_text(text, encoding="utf-8")
        os.chmod(tmp, mode)
        try:
            os.replace(tmp, p)
        except OSError as exc:
            # 대상이 **마운트 지점**이면(systemd `ReadWritePaths=` 에 파일 하나를 적으면 그 파일이 자기 위에 bind mount 된다)
            # rename 이 `EBUSY` 로 거절된다 — 랩의 `/etc/opendkim.conf` 가 그랬다(2026-10-12). 유닛에서 그 항목은 걷었지만,
            # 옛 유닛으로 도는 설치에서도 적용이 죽지 않게 그때는 **제자리에서** 덮어쓴다(이 경우만 원자적이지 않다).
            if exc.errno != errno.EBUSY:
                tmp.unlink(missing_ok=True)
                raise
            try:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(text)
                os.chmod(p, mode)
            finally:
                tmp.unlink(missing_ok=True)

    def remove(self, path: str) -> None:
        Path(path).unlink(missing_ok=True)

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def copy(self, src: str, dst: str) -> bool:
        source = Path(src)
        if not source.is_file():
            return False
        target = Path(dst)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return True

    def chown(self, path: str, user: str, group: str, *, mode: int | None = None) -> None:
        """소유자를 이름으로 바꾼다(DKIM 키는 opendkim 만 읽는다). 이름이 없으면 예외 - 엔진이 실패로 바꾸고 되돌린다."""
        import grp  # noqa: PLC0415 - Linux 에서만 있다
        import pwd  # noqa: PLC0415

        os.chown(path, pwd.getpwnam(user).pw_uid, grp.getgrnam(group).gr_gid)
        if mode is not None:
            os.chmod(path, mode)
