"""커밋된 `frontend/src/generated/sortKeys.json` 이 지금의 서버 정렬 계약과 맞는지 본다.

`check_field_limits_fresh.py` 와 같은 관용이고 같은 이유다. 서버의 허용 키를 고치고 이
생성기를 다시 안 돌리면, 화면은 **없어진 키로 화살표를 그린다** — 누르면 서버가 그 키를
모르는 값으로 보고 기본 정렬로 조용히 떨어뜨리고, 사용자에게는 「눌렀는데 순서가 그대로」로
보인다. 아무 데도 오류가 안 남는 종류의 어긋남이다.

사용법:
    python scripts/check_sort_keys_fresh.py            # 맞는지 본다 (다르면 종료코드 1)
    python scripts/check_sort_keys_fresh.py --write    # 커밋된 파일을 새로 쓴다
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_sort_keys import OUT, render  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="커밋된 파일을 새로 쓴다")
    args = parser.parse_args()

    want = render()
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(want, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
        return 0

    if not OUT.exists():
        print(f"{OUT.relative_to(ROOT)} 가 없다 — python scripts/generate_sort_keys.py")
        return 1
    have = OUT.read_text(encoding="utf-8")
    if have != want:
        print(f"{OUT.relative_to(ROOT)} 가 지금의 서버 정렬 계약과 다르다.")
        print("python scripts/generate_sort_keys.py 로 다시 만들어라.")
        return 1
    print("SORT_KEYS_FRESH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())