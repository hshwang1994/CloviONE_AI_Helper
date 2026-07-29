"""정적 파일 주소에 내용 지문을 붙인다.

배포해도 사용자 화면이 그대로인 문제가 있었다. 정적 파일은 nginx와 앱 양쪽에서 한 시간을
캐시하는데 주소가 `/static/css/tokens.css`로 고정이라, 파일이 바뀌어도 브라우저가 알 방법이
없었다. 그래서 배포할 때마다 최대 한 시간 동안 사용자는 옛 화면을 봤다. CSS면 색이 안 바뀌는
정도지만, JS가 옛것으로 남으면 새 API와 어긋나 실제로 깨진다.

새로고침을 부탁하는 것은 해결이 아니다. 파일이 바뀌면 주소가 바뀌게 한다.
주소가 바뀌면 브라우저는 무조건 새로 받고, 안 바뀐 파일은 캐시를 그대로 쓴다.

지문은 파일의 수정 시각과 크기에서 뽑는다. 내용을 읽어 해시하지 않는 이유는 첫 요청을
느리게 만들지 않기 위해서이고, 배포가 파일을 새로 설치하면 두 값이 함께 바뀐다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


class AssetVersions:
    """파일별 지문을 계산한다. 파일이 바뀌면 지문도 바뀐다.

    처음엔 "프로세스가 뜬 뒤 정적 파일은 안 바뀐다(배포하면 재시작한다)"고 보고 지문을
    영구 캐시했다. 그 가정이 틀렸다. `docs/MAINTENANCE_PLAYBOOK.md` §1과 CLAUDE.md §6이
    **정적 파일만 바꿨을 때는 재시작 없이 교체하라**고 안내한다 — StaticFiles가 디스크에서
    매 요청 서빙하므로 파일 자체는 즉시 바뀐다. 그런데 영구 캐시된 지문은 옛 주소를 계속
    내보내고, 그 주소는 브라우저가 한 시간 캐시하고 있다. 결과적으로 문서가 시킨 절차를
    그대로 따르면 캐시 버스팅이 통째로 무효가 되고, 사용자는 옛 화면을 계속 본다.
    캐시 버스팅을 넣은 이유가 바로 그 증상이었으므로 자기 자신을 되돌리는 셈이었다.

    그래서 매번 stat한다. 파일 하나당 syscall 하나이고 한 페이지가 참조하는 정적 파일은
    대여섯 개다. 요청 한 번의 비용에 견주면 무시할 수 있고, 이게 문서와 코드를 일치시킨다.
    """

    def __init__(self, static_dir: Path, *, cache: bool = True) -> None:
        self._static_dir = static_dir
        # cache=True는 이제 "해석된 경로를 재사용한다"는 뜻이지 "지문을 고정한다"가 아니다.
        # 경로 검증(resolve + static 밖 차단)은 결과가 안 변하므로 캐시해도 된다.
        self._resolved: dict[str, Path | None] | None = {} if cache else None

    def stamp(self, path: str) -> str:
        """'/static/css/chat.css' → '/static/css/chat.css?v=a1b2c3d4'

        파일이 바뀌면 지문이 바뀐다. 재시작은 필요 없다.
        """
        return self._compute(path)

    def _resolve(self, path: str) -> Path | None:
        """static 안의 실제 경로. 밖을 가리키면 None. 결과가 안 변하므로 캐시한다."""
        if self._resolved is not None and path in self._resolved:
            return self._resolved[path]
        target = self._static_dir / path.removeprefix("/static/")
        try:
            # 경로 조작으로 static 밖의 파일을 지문 대상으로 삼지 못하게 한다.
            resolved = target.resolve()
            resolved.relative_to(self._static_dir.resolve())
        except (OSError, ValueError):
            resolved = None
        if self._resolved is not None:
            self._resolved[path] = resolved
        return resolved

    def _compute(self, path: str) -> str:
        resolved = self._resolve(path)
        if resolved is None:
            return path
        try:
            info = resolved.stat()
        except OSError:
            # 파일이 없으면 주소를 그대로 둔다. 지문 때문에 화면이 죽는 일은 없어야 한다.
            return path
        seed = f"{info.st_mtime_ns}:{info.st_size}".encode()
        return f"{path}?v={hashlib.sha256(seed).hexdigest()[:8]}"
