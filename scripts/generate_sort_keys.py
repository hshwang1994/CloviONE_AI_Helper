"""서버의 정렬 화이트리스트를 뽑아 고정 JSON 으로 낸다.

`scripts/generate_field_limits.py` 와 같은 관용이다 — 값이 바뀌는 시점은 사람이 도메인의
`SortSpec` 을 고칠 때뿐이고, 그때는 이미 재빌드가 필요한 순간이다. 런타임 API 를 새로 만들지
않는다(정렬 키는 정적이고, 응답에 실으면 첫 응답 전에 머리행이 정렬 없이 그려졌다가 화살표가
나중에 튀어나온다).

여기서 키를 한 번도 타이핑하지 않는다 — 전부 실제 `SortSpec` 에서 읽는다. 다시 안 돌리면
`scripts/check_sort_keys_fresh.py` 가 잡는다.

사용법:
    python scripts/generate_sort_keys.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.sort_registry import all_sort_specs  # noqa: E402

OUT = ROOT / "frontend" / "src" / "generated" / "sortKeys.json"


def render() -> str:
    return json.dumps(all_sort_specs(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())