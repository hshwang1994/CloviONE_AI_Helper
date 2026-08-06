"""커밋된 프런트 번들이 지금의 소스와 맞는지 본다 (P5).

## 왜 필요한가

이 저장소는 빌드 산출물(`app/static/react/`)을 **git 에 커밋**한다. 그 덕분에 서버에
Node 를 안 깔고도 `git clone` 만으로 UI 가 돈다 - 설치가 훨씬 단순해지는 좋은 선택이다.

대신 조용한 실패가 하나 생긴다. **소스만 고치고 번들을 다시 안 만들면**, git 으로 설치한
서버는 아무 오류 없이 **옛 UI 를 계속 돌린다.** 로그에도 안 남고, 화면도 멀쩡해 보이고,
"고쳤는데 왜 그대로냐" 만 남는다. 사람이 기억해야 하는 종류의 일은 언젠가 반드시 잊는다 -
이 작업 중에도 실제로 프런트를 열여섯 파일 고치고 번들을 안 만든 상태가 됐다.

## 어떻게 판정하는가

빌드에 **실제로 들어가는 입력**만 해시한다. 테스트 파일은 번들에 안 들어가므로 뺀다 -
안 빼면 테스트 한 줄 고칠 때마다 "번들이 낡았다" 고 해서, 사람이 곧 이 검사를 무시하게 된다.
검사는 **틀리지 않는 것**보다 **믿을 수 있는 것**이 중요하다.

한계도 적어 둔다: 테스트 파일이 어쩌다 번들 진입점에서 import 되면 이 검사는 그 변경을
못 본다. 그런 import 는 그 자체로 잘못이라 여기서 막지 않고 그대로 둔다.

## 쓰는 법

    python scripts/check_bundle_fresh.py            # 맞는지 본다 (다르면 종료코드 1)
    python scripts/check_bundle_fresh.py --write    # 빌드 직후 기준을 새로 적는다
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
BUNDLE = ROOT / "app" / "static" / "react"
STAMP = BUNDLE / "BUILD_STAMP.json"

# 빌드 입력. 여기 없는 것을 고쳐도 번들은 안 바뀐다는 뜻이므로, 늘릴 때는 신중해야 한다.
SOURCE_DIRS = ("src",)
SOURCE_FILES = ("package.json", "package-lock.json", "index.html",
                "vite.config.js", "vite.config.mjs", "vite.config.ts")
# 번들에 들어가지 않는 것들. 뺀 이유가 각각 있어야 한다.
SKIP_SUFFIXES = (".test.js", ".test.jsx", ".test.ts", ".test.tsx", ".md", ".snap")
SKIP_DIRS = ("__tests__", "__snapshots__", "node_modules")


def _iter_inputs():
    for name in SOURCE_FILES:
        path = FRONTEND / name
        if path.is_file():
            yield path
    for folder in SOURCE_DIRS:
        base = FRONTEND / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.name.endswith(SKIP_SUFFIXES):
                continue
            yield path


def source_hash() -> tuple[str, int]:
    """줄바꿈을 정규화해서 해시한다.

    Windows 에서 만든 번들과 Linux 에서 만든 번들이 CRLF 차이만으로 달라지면, 아무것도
    안 바뀌었는데 "낡았다" 는 답이 나온다. 그 답이 한 번이라도 나오면 사람은 이 검사를 끈다.
    """
    digest = hashlib.sha256()
    count = 0
    for path in _iter_inputs():
        rel = path.relative_to(FRONTEND).as_posix()
        body = path.read_bytes().replace(b"\r\n", b"\n")
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(body).digest())
        count += 1
    return digest.hexdigest(), count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="프런트 번들 신선도 검사")
    parser.add_argument("--write", action="store_true", help="빌드 직후 기준을 새로 적는다")
    args = parser.parse_args(argv)

    if not FRONTEND.is_dir():
        # 배포 산출물에는 frontend/ 가 없을 수 있다. 그때는 검사할 것이 없다.
        print("BUNDLE_FRESH_SKIPPED: frontend/ 가 없다 (배포본으로 보인다)")
        return 0

    current, count = source_hash()
    if count == 0:
        print("[FAIL] 프런트 소스를 하나도 못 찾았다 - 검사가 뜻이 없다", file=sys.stderr)
        return 1

    if args.write:
        if not BUNDLE.is_dir():
            print(f"[FAIL] 번들이 없다: {BUNDLE}", file=sys.stderr)
            return 1
        STAMP.write_text(
            json.dumps({"source_hash": current, "input_count": count,
                        "note": "scripts/check_bundle_fresh.py --write 가 적는다. 손으로 고치지 마라."},
                       ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"BUNDLE_STAMP_WRITTEN ({count}개 입력, {current[:12]})")
        return 0

    if not STAMP.is_file():
        # "모르겠다" 를 "괜찮다" 로 바꾸지 않는다. 기준이 없으면 번들의 출처를 알 수 없고,
        # 그 상태로 배포하면 무엇이 도는지 아무도 모른다.
        print(
            "[FAIL] 번들 기준(BUILD_STAMP.json)이 없다 - 이 번들이 어느 소스에서 나왔는지 알 수 없다.\n"
            "       고치는 법: cd frontend && npm run build && "
            "python scripts/check_bundle_fresh.py --write",
            file=sys.stderr,
        )
        return 1

    try:
        recorded = json.loads(STAMP.read_text(encoding="utf-8")).get("source_hash")
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] 번들 기준을 읽지 못했다: {exc}", file=sys.stderr)
        return 1

    if recorded != current:
        print(
            "[FAIL] 프런트 소스가 번들보다 새롭다 - git 으로 설치한 서버는 **옛 UI** 를 돌린다.\n"
            f"       기준 {str(recorded)[:12]} vs 지금 {current[:12]} (입력 {count}개)\n"
            "       고치는 법: cd frontend && npm run build && "
            "python scripts/check_bundle_fresh.py --write",
            file=sys.stderr,
        )
        return 1

    print(f"BUNDLE_FRESH_OK ({count}개 입력)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
