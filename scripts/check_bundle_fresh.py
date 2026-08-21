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
    """빌드 입력을 **어느 운영체제에서 돌려도 같은 순서로** 낸다.

    🔴 여기가 한 번 틀렸다. 예전에는 `sorted(base.rglob("*"))` 로 `Path` 객체를 정렬했는데,
    `Path` 의 비교는 플랫폼을 탄다: Windows 는 대소문자를 무시하고(`auth.jsx` < `Banners.jsx`),
    리눅스는 바이트로 본다(`Banners.jsx` < `auth.jsx`). 아래 `source_hash` 가 파일 이름과
    내용을 **순서대로** 이어 붙여 해시하므로, 순서가 다르면 **내용이 한 바이트도 안 달라도**
    해시가 달라진다.

    그래서 Windows 에서 찍은 기준(BUILD_STAMP.json)을 들고 리눅스 서버에 설치하면
    설치 Stage 5 가 «번들이 낡았다» 로 죽는다 — 번들은 멀쩡한데. 실제로 S4 의 LXD 리허설이
    그렇게 멈췄고, 199개 파일의 내용 해시가 양쪽에서 **전부 같다**는 것을 확인하고 나서야
    원인이 순서라는 것이 드러났다.

    정렬 키를 경로 문자열(POSIX 표기)로 고정한다. 그 문자열은 어느 운영체제에서도 같다.
    """
    for name in SOURCE_FILES:
        path = FRONTEND / name
        if path.is_file():
            yield path
    for folder in SOURCE_DIRS:
        base = FRONTEND / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*"), key=lambda p: p.relative_to(FRONTEND).as_posix()):
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


def self_test() -> int:
    """이 검사기 자신을 먼저 시험한다 (E3).

    지키는 성질은 하나다: **입력 순서가 운영체제에 안 달렸다.** `source_hash` 가 이름과
    내용을 순서대로 이어 붙이므로, 순서가 흔들리면 내용이 그대로여도 해시가 달라진다.

    사례는 대소문자가 섞인 이름들이다 — 바로 그 자리에서 Windows(대소문자 무시)와
    리눅스(바이트)가 갈린다. 반례도 함께 확인한다: 옛 구현(`sorted(rglob)`)을 같은
    트리에 돌려 보고, 이 머신에서 두 순서가 실제로 갈리는지 본다. 갈리지 않는 머신
    (리눅스)에서는 그 사례가 「원래 같다」이므로 통과로 센다 — 검사가 거짓말하지 않게
    무엇을 확인했는지 함께 적는다.
    """
    import tempfile

    global FRONTEND
    saved = FRONTEND
    names = ["src/app/Banners.jsx", "src/app/auth.jsx", "src/app/AppShell.jsx",
             "src/app/zulu.jsx", "src/ui/Kit.jsx", "src/ui/kit.helper.jsx"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            FRONTEND = root
            for rel in names:
                f = root / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(rel, encoding="utf-8")
            got = [p.relative_to(root).as_posix() for p in _iter_inputs()]
            want = sorted(names)
            if got != want:
                print(f"[FAIL] self-test: 순서가 바이트 오름차순이 아니다\n  got : {got}\n  want: {want}",
                      file=sys.stderr)
                return 1
            # 반례 — 옛 구현이 이 머신에서 실제로 다른 순서를 내는가.
            old = [p.relative_to(root).as_posix()
                   for p in sorted((root / "src").rglob("*")) if p.is_file()]
            differs = old != want
            h1, _ = source_hash()
            h2, _ = source_hash()
            if h1 != h2:
                print("[FAIL] self-test: 같은 트리에서 해시가 두 번 다르게 나온다", file=sys.stderr)
                return 1
    finally:
        FRONTEND = saved
    verdict = "옛 구현과 순서가 갈린다(반례 확인)" if differs else "이 운영체제에서는 옛 구현도 같은 순서다"
    print(f"BUNDLE_SELFTEST_OK ({len(names)}개 사례 · {verdict})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="프런트 번들 신선도 검사")
    parser.add_argument("--write", action="store_true", help="빌드 직후 기준을 새로 적는다")
    parser.add_argument("--self-test", action="store_true", help="검사기 자신을 시험한다")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

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
