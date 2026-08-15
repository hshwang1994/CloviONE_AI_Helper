"""PA-RC-0005 — 관리자 폼 maxLength를 백엔드 Pydantic 스키마에서 뽑아 고정 JSON으로 낸다.

## 왜 빌드 시 생성인가(런타임 API가 아니라)

이 값이 바뀌는 시점은 사람이 Pydantic 스키마를 고칠 때뿐이다 — 이미 재빌드가 필요한
순간이다. 여기에 별도 런타임 API·프런트 캐시·최초 로딩 상태를 얹는 대신, 이 저장소가 이미
쓰는 관용(빌드 산출물을 커밋하고, 신선도는 검사로 고정한다 — check_bundle_fresh.py)을
그대로 따른다.

## 손으로 값을 옮기지 않는다

여기서 숫자를 한 번도 타이핑하지 않는다 — 전부 `app/core/field_limits.py`를 거쳐 실제
Pydantic 모델의 `model_json_schema()`에서 읽는다. 스키마가 바뀌면 이 스크립트를 다시 돌리는
것만으로 값도 따라 바뀐다 — 그리고 다시 안 돌리면 `check_field_limits_fresh.py`가 잡는다.

사용법:
    python scripts/generate_field_limits.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.field_limits import all_field_limits  # noqa: E402

OUT = ROOT / "frontend" / "src" / "generated" / "fieldLimits.json"


def render() -> str:
    limits = all_field_limits()
    return json.dumps(limits, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    text = render()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    limits = json.loads(text)
    field_count = sum(len(fields) for forms in limits.values() for fields in forms.values())
    print(f"FIELD_LIMITS_WRITTEN ({len(limits)}개 화면, {field_count}개 필드 상한) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
