"""Heading 시각/의미 분리 재유입 방지 검사 (PA-RC-0012 acceptance_criteria 2, 5).

왜 필요한가: MUI에서 `variant="h6"`은 "20px 굵은 글자"라는 시각 선택이면서 동시에(같은
Typography에 `component=`가 없으면) 실제 `<h6>` 태그도 결정해 버린다. 손으로 쓴 관리자
화면 5개가 이 함정으로 `h1` 바로 다음에 `h6`을 놓아 문서 heading 구조가 네 단계
(h2~h5)를 건너뛰었다(스크린리더의 heading 목록 탐색·구역 점프가 깨진다). 이 저장소는
이미 옳은 관용을 알고 쓰고 있다 — `component=`로 시각과 의미를 분리하는 자리가 이미 27회
있었다(`ui/adminKit.jsx:52` 등) — 문서가 아니라 검사가 없으면 다음 화면이 또 같은
함정에 빠지는 걸 아무도 못 잡는다(`check_typography_literals.py`·
`check_button_hierarchy.py`와 같은 이유, 같은 자리).

이 검사가 잡는 것: `variant="h3"`~`variant="h6"` 또는 `variant="subtitle1"`/
`variant="subtitle2"`가 있는데 **같은 줄에** `component=`가 없는 경우. 뒤의 둘도
MUI 기본 매핑에서 `<h6>`로 떨어진다(`defaultVariantMapping.subtitle1/2 === "h6"`,
`node_modules/@mui/material/Typography/Typography.js`) — 실제로 `Offboarding.jsx`의
`variant="subtitle1"` 하나가 이 형태로 h1 다음 h6을 만들었는데, 처음 이 검사를 h3~h6만
잡게 짰을 때는 못 잡았고 `heading-order.test.jsx`(렌더 결과를 직접 보는 회귀 시험)가
잡아서 뒤늦게 여기 추가했다 — 그래서 두 검사를 같이 둔다(하나가 놓쳐도 다른 하나가 잡게).
h1/h2는 대상이 아니다 — `component=` 없이 써도 기본 매핑이 이미 h1/h2라 모순이 없다
(애초에 이 결함이 나올 수가 없다).

이 검사가 **안** 하는 것: heading "순서"(h1 다음에 h3 아니라 h2인가) 자체는 줄 단위
정적 검사로 못 잡는다 — 화면 전체의 렌더 결과를 봐야 하는 문제라 이건 vitest 회귀
테스트(heading-order.test.jsx)가 대신 못박는다. 이 스크립트는 그 앞 단계, "애초에
component=를 빠뜨리는 것" 하나만 막는다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"

RX_VARIANT_H36 = re.compile(r'variant="(?:h[3-6]|subtitle[12])"')
RX_COMPONENT = re.compile(r"\bcomponent=")

# 2026-08-16 PA-RC-0012 조사에서 직접 소스 문맥으로 확인된, component= 없이 두는 게
# 실제로 맞는 자리만 담는다 — 문서 구조가 아니라 순간적으로 뜨고 사라지는 연출이라
# heading 목록에 안 들어가도 접근성 손실이 없다. 새 예외를 추가하려면 같은 방식으로
# 실제 화면 문맥을 확인한 뒤 이유를 적는다.
EXEMPT: dict[str, str] = {
    "app/LoginHandoff.jsx:137": "로그인 직후 전체화면을 잠깐 덮는 전환 연출(\"로그인되었습니다\") "
                                "— 문서 구조를 설명하는 구역 제목이 아니라 상태 공지이고, 아래 "
                                "화면과 동시에 존재하지 않는다(교체되는 오버레이). h2로 만들면 "
                                "오히려 실제 페이지 구조에 없는 가짜 구역이 생긴다.",
}


def _is_comment_line(line: str) -> bool:
    """check_typography_literals.py와 같은 관용 — JSDoc 연속줄과 `//` 라인 코멘트만 거른다."""
    stripped = line.strip()
    if stripped.startswith("*") or stripped.startswith("/*"):
        return True
    return stripped.startswith("//")


def _iter_source_files(src_dir: Path):
    for path in sorted(src_dir.rglob("*")):
        if path.suffix not in (".js", ".jsx"):
            continue
        if ".test." in path.name:
            continue
        yield path


def main(src_dir: Path | None = None) -> int:
    src_dir = src_dir or SRC
    hits: list[str] = []

    for path in _iter_source_files(src_dir):
        rel = path.relative_to(src_dir).as_posix()
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line):
                continue
            if not RX_VARIANT_H36.search(line):
                continue
            if RX_COMPONENT.search(line):
                continue
            key = f"{rel}:{lineno}"
            if key in EXEMPT:
                continue
            hits.append(f"{key}: {line.strip()[:100]}")

    if hits:
        print("[FAIL] variant=\"h3~h6/subtitle1/subtitle2\"인데 같은 줄에 component=가 없다 — 문서 heading 구조가", file=sys.stderr)
        print("       의도치 않게 그 태그를 그대로 따라간다:", file=sys.stderr)
        for h in hits:
            print(f"  - {h}", file=sys.stderr)
        print("", file=sys.stderr)
        print("  카드/구역 제목이면 component=\"h2\"(PageHeader의 h1 바로 아래) 또는 그 화면의", file=sys.stderr)
        print("  실제 위치에 맞는 레벨을 명시하라. 진짜 heading이 아니라면(순간 연출 등)", file=sys.stderr)
        print("  scripts/check_heading_variant_mapping.py의 EXEMPT에 실제 문맥과 함께 등재하라.", file=sys.stderr)
        return 1

    print(f"HEADING_VARIANT_MAPPING_OK (예외 {len(EXEMPT)}건 등록됨)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
