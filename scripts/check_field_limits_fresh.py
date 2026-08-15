"""커밋된 frontend/src/generated/fieldLimits.json이 지금의 백엔드 스키마와 맞는지 본다
(PA-RC-0005, check_bundle_fresh.py와 같은 관용).

## 왜 필요한가

`scripts/generate_field_limits.py`가 Pydantic 스키마에서 값을 뽑아 JSON으로 커밋한다.
스키마의 `max_length`를 고치고 이 생성기를 다시 안 돌리면, 화면은 **낡은 상한**을 계속
보여준다 — 서버는 새 규칙으로 거절하는데 화면은 옛 규칙으로만 막거나(더 엄격해졌으면 정상
입력을 조용히 막고), 반대로 완화됐으면 더 이상 필요 없는 제한을 계속 강제한다. 둘 다 PA-RC-0005
가 막으려던 "두 SSOT가 갈라진다"가 그대로 재발한 것이다.

## 어떻게 판정하는가

`generate_field_limits.render()`를 다시 호출해(파일을 새로 쓰지 않고) 커밋된 파일과 텍스트를
그대로 비교한다 — 번들과 달리 Node 빌드가 필요 없어(순수 Python introspection) 매번 실제로
다시 계산해도 비용이 거의 없다. `check_bundle_fresh.py`의 해시-스탬프 방식과 달리 직접
diff한다.

사용법:
    python scripts/check_field_limits_fresh.py            # 맞는지 본다 (다르면 종료코드 1)
    python scripts/check_field_limits_fresh.py --write     # 커밋된 파일을 새로 쓴다
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_field_limits import OUT, render  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="fieldLimits.json 신선도 검사")
    parser.add_argument("--write", action="store_true", help="커밋된 파일을 새로 쓴다")
    args = parser.parse_args(argv)

    current = render()

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(current, encoding="utf-8", newline="\n")
        print(f"FIELD_LIMITS_WRITTEN -> {OUT}")
        return 0

    if not OUT.is_file():
        print(
            "[FAIL] fieldLimits.json이 없다 - 고치는 법: "
            "python scripts/generate_field_limits.py",
            file=sys.stderr,
        )
        return 1

    recorded = OUT.read_text(encoding="utf-8").replace("\r\n", "\n")
    if recorded != current.replace("\r\n", "\n"):
        print(
            "[FAIL] fieldLimits.json이 지금의 백엔드 스키마와 다르다 - 관리자 폼이 낡은 "
            "maxLength를 보여줄 수 있다.\n"
            "       고치는 법: python scripts/generate_field_limits.py",
            file=sys.stderr,
        )
        return 1

    print("FIELD_LIMITS_FRESH_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
