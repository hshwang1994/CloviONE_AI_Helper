"""설치본의 허용 목록에 새 기본 호스트를 더한다 (계획 3.17, D-522).

설치(Stage 8)는 `config/*.json` 을 설치본이 **없을 때만** 복사한다. 운영자가 고친 목록을 덮으면 안 되기 때문이다. 그런데
그 규칙만 있으면 새 버전이 기본 목록에 호스트를 더해도(예: OpenAI 두 호스트) 업그레이드한 서버에는 영영 들어가지 않는다.
그러면 사람이 서버에 들어가 파일을 고쳐야 하고, 그것이 이 제품이 없애려는 수동 단계다.

그래서 기본 목록의 **직전 사본**을 기록해 두고, 이번 기본 목록과의 차이만 옮긴다.

  이번 기본 - 직전 기본 = 이번 버전이 새로 더한 호스트 → 설치본에 없으면 더한다
  직전 기본 - 설치본     = 운영자가 지운 호스트        → 되살리지 않는다
  설치본에만 있는 것      = 운영자가 더한 호스트        → 그대로 둔다

직전 사본이 없으면(이 규칙이 생기기 전의 설치) 운영자가 기본 항목을 지운 적이 없다고 보고 빠진 기본 호스트를 한 번 더한다.
그 뒤로는 사본이 생겨 지운 항목을 지킨다. 더한 호스트는 한 줄씩 표준 출력으로 알린다.

표준 라이브러리만 쓴다. 설치 스크립트가 제품 venv 의 파이썬으로 부른다.

    python merge_allowlist.py --default <배포본 파일> --installed <설치본 파일> --record <직전 기본 사본>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _hosts(payload: object) -> list[str] | None:
    if isinstance(payload, dict) and isinstance(payload.get("hosts"), list):
        return [str(h) for h in payload["hosts"]]
    return None


def _load(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _write(path: Path, payload: object) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def merge(default_path: Path, installed_path: Path, record_path: Path) -> list[str]:
    """더한 호스트 목록을 돌려준다. 허용 목록이 아닌 파일은 건드리지 않는다."""
    default = _load(default_path)
    default_hosts = _hosts(default)
    if default_hosts is None:
        return []
    installed = _load(installed_path)
    if installed is None:
        # 설치본이 없으면 설치 스크립트가 기본을 그대로 복사한다. 여기서는 사본만 남긴다.
        _write(record_path, default)
        return []
    installed_hosts = _hosts(installed)
    if installed_hosts is None:
        # 운영자가 모양을 바꾼 파일이다. 어떻게 합칠지 알 수 없으므로 손대지 않는다.
        return []
    previous = _load(record_path)
    previous_hosts = _hosts(previous)
    if previous_hosts is None:
        # 사본이 없는 첫 병합이다. 운영자가 기본 항목을 지운 적이 없다고 본다(모듈 설명).
        previous_hosts = []
    added = [h for h in default_hosts if h not in previous_hosts and h not in installed_hosts]
    if added:
        installed["hosts"] = installed_hosts + added
        _write(installed_path, installed)
    _write(record_path, default)
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="허용 목록에 새 기본 호스트를 더한다")
    parser.add_argument("--default", required=True, type=Path)
    parser.add_argument("--installed", required=True, type=Path)
    parser.add_argument("--record", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        added = merge(args.default, args.installed, args.record)
    except (OSError, ValueError) as exc:
        print(f"허용 목록을 합치지 못했습니다({args.installed.name}): {exc}", file=sys.stderr)
        return 1
    for host in added:
        print(f"added {host}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
