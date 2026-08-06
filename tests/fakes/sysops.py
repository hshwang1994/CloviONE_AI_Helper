"""특권 헬퍼 테스트용 가짜 시스템.

실제 시스템을 건드리지 않고 **액션 표 전체**를 검사하기 위한 것이다. 이게 없으면
`app/sysops/` 는 root 로 도는 코드인데 아무 데서도 실행되지 않은 채 배포된다.

`FakeRunner` 는 파일을 메모리 딕셔너리로, 명령을 등록된 응답표로 흉내 낸다.
등록되지 않은 명령은 **실패**로 답한다 — 조용히 성공시키면 "명령을 안 부르도록 고쳐도
테스트가 통과" 하는 헛것이 된다.
"""

from __future__ import annotations

from app.sysops.runner import ALLOWED_BINARIES, Completed


class FakeRunner:
    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files: dict[str, str] = dict(files or {})
        self.modes: dict[str, int] = {}
        self.calls: list[tuple[str, ...]] = []
        # (argv 튜플) -> Completed. 부분 일치는 하지 않는다 — 정확히 그 명령만 답한다.
        self.responses: dict[tuple[str, ...], Completed] = {}
        self.enforce_allowlist = True

    # ---- 등록 도우미 -------------------------------------------------
    def reply(self, argv: list[str], *, code: int = 0, out: str = "", err: str = "") -> None:
        self.responses[tuple(argv)] = Completed(tuple(argv), code, out, err)

    # ---- Runner 규약 -------------------------------------------------
    def run(self, argv: list[str], *, timeout: int = 20) -> Completed:
        key = tuple(argv)
        self.calls.append(key)
        if self.enforce_allowlist and argv and argv[0] not in ALLOWED_BINARIES:
            from app.sysops.runner import BinaryNotAllowedError

            raise BinaryNotAllowedError(f"허용되지 않은 프로그램: {argv[0]}")
        got = self.responses.get(key)
        if got is None:
            return Completed(key, 127, "", f"등록되지 않은 명령: {' '.join(argv)}")
        return got

    def read_text(self, path: str) -> str | None:
        return self.files.get(path)

    def write_text(self, path: str, text: str, *, mode: int = 0o644) -> None:
        self.files[path] = text
        self.modes[path] = mode

    def remove(self, path: str) -> None:
        self.files.pop(path, None)
        self.modes.pop(path, None)

    def exists(self, path: str) -> bool:
        return path in self.files

    def copy(self, src: str, dst: str) -> bool:
        if src not in self.files:
            return False
        self.files[dst] = self.files[src]
        self.modes[dst] = self.modes.get(src, 0o644)
        return True
