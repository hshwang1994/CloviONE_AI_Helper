"""번들 무결성 검사가 **항상 실패하지 않게** 못박는다.

## 무엇이 있었나

`scripts/build-bundle.sh` 가 매니페스트를 이렇게 만들었다:

    ( cd "$STAGE" && find . -type f -exec sha256sum {} + > MANIFEST.sha256 )

셸은 `find` 를 실행하기 **전에** 리다이렉트 대상을 만든다. 그래서 `find` 가 갓 만들어진 빈
`MANIFEST.sha256` 을 목록에 넣고 **그때의 해시(빈 파일)** 를 적는다. 그런데 다 쓰고 나면 그
파일의 내용은 더 이상 비어 있지 않다 - 즉 **자기 자신과 절대 일치할 수 없다.**

결과: `sha256sum -c MANIFEST.sha256` 이 모든 번들에서 **언제나**

    sha256sum: WARNING: 1 computed checksum did NOT match

를 내고 exit 1 이었다. 실제로 서버에서 그렇게 나오는 것을 확인했다(1426개 중 1개 실패,
실패한 것이 `./MANIFEST.sha256` 자기 자신).

## 왜 이게 진짜 결함인가

`docs/MAINTENANCE_PLAYBOOK.md` §2-3 이 이 명령을 **배포 전 무결성 확인 단계**로 적어 두고 있다.
늘 실패하는 검사는 없는 검사보다 나쁘다 - 운영자는 그 한 줄을 '원래 그런 것' 으로 학습하고,
그 뒤로는 **진짜로 파일 하나가 깨진 번들도 똑같아 보인다.** 검사가 신호를 잃는다.

여기서 검사하는 것은 "매니페스트가 자기를 포함하지 않는다" 는 성질 하나다. 실제 번들을 만들어
보는 것은 wheelhouse 다운로드가 필요해 유닛 테스트에서 할 일이 아니다 - 그런 척하지 않는다.
"""

from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.regression

ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILD_BUNDLE = ROOT / "scripts" / "build-bundle.sh"


def _manifest_line() -> str:
    text = BUILD_BUNDLE.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        # 주석이 아니면서 매니페스트를 실제로 만드는 줄.
        if stripped.startswith("#"):
            continue
        if "MANIFEST.sha256" in stripped and "find" in stripped:
            return stripped
    raise AssertionError(
        "build-bundle.sh 에서 MANIFEST.sha256 을 만드는 find 줄을 찾지 못했다 - "
        "매니페스트 생성 방식이 바뀌었다면 이 검사를 그 방식에 맞게 고쳐야 한다."
    )


def test_build_bundle_exists():
    assert BUILD_BUNDLE.is_file(), f"없는 파일이다: {BUILD_BUNDLE}"


def test_the_manifest_does_not_hash_itself():
    """자기 자신을 목록에 넣으면 `sha256sum -c` 가 영원히 1건 실패한다."""
    line = _manifest_line()
    assert re.search(r"!\s*-name\s+'?MANIFEST\.sha256'?", line), (
        "매니페스트를 만드는 find 가 MANIFEST.sha256 자신을 제외하지 않는다.\n"
        f"  문제의 줄: {line}\n"
        "셸이 find 보다 먼저 리다이렉트 대상을 만들기 때문에, 제외하지 않으면 find 가 그 빈\n"
        "파일의 해시를 적고 -> 다 쓰고 나면 내용이 달라져 -> 자기 자신과 영원히 불일치한다.\n"
        "고치는 법: find . -type f ! -name MANIFEST.sha256 -exec sha256sum {} + > MANIFEST.sha256"
    )


def test_the_manifest_is_still_written_from_the_stage_root():
    """상대경로(`./app-src/...`)여야 서버에서 풀린 자리에서 그대로 대조된다."""
    line = _manifest_line()
    assert 'cd "$STAGE"' in line, (
        "매니페스트는 STAGE 안에서 만들어야 경로가 상대경로로 남는다. 절대경로가 되면\n"
        f"서버에서 대조할 수 없다.\n  문제의 줄: {line}"
    )
    assert "find ." in line, f"stage 루트 기준(`find .`)이 아니다.\n  문제의 줄: {line}"
