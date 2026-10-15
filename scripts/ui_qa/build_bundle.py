"""프런트 번들을 **잠금 아래** 빌드하고 한 번에 바꿔 끼운다.

여러 작업자가 같은 작업 트리에서 동시에 `npm run build` 를 돌리면 `app/static/react` 가 반쯤 쓰인 채로 서빙돼 캡처가 깨진 번들을
본다. 이 스크립트는 (1) `var/build.lock` 을 잡아 빌드를 직렬화하고 (2) 임시 디렉터리에 빌드한 뒤 (3) 서빙 디렉터리를 통째로 바꿔
끼운다 — 바꿔 끼우는 순간 말고는 서빙 디렉터리가 언제나 온전한 번들이다.

    .venv/Scripts/python.exe scripts/ui_qa/build_bundle.py            # 잠금 → vite build → 바꿔 끼우기
    .venv/Scripts/python.exe scripts/ui_qa/build_bundle.py --wait 900 # 잠금을 최대 900초 기다린다(기본 1200)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
SERVE_DIR = ROOT / "app" / "static" / "react"
TMP_DIR = ROOT / "app" / "static" / "react.building"
LOCK_FILE = ROOT / "var" / "build.lock"


class BuildLock:
    def __init__(self, path: Path, wait_seconds: int):
        self.path = path
        self.wait = wait_seconds
        self.fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.wait
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                stale = False
                try:
                    age = time.time() - self.path.stat().st_mtime
                    stale = age > 3600
                except FileNotFoundError:
                    continue
                if stale:
                    print(f"[build_bundle] 한 시간 넘은 잠금을 걷습니다: {self.path}")
                    self.path.unlink(missing_ok=True)
                    continue
                if time.monotonic() > deadline:
                    raise SystemExit(f"[build_bundle] 다른 빌드가 잠금을 쥐고 있습니다: {self.path}")
                time.sleep(2)

    def __exit__(self, *exc):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def build(out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    rel = os.path.relpath(out_dir, FRONTEND)
    cmd = ["npm", "run", "build", "--", "--outDir", rel, "--emptyOutDir"]
    print("[build_bundle]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(FRONTEND), check=True, shell=(os.name == "nt"))
    if not (out_dir / "index.html").exists():
        raise SystemExit("[build_bundle] 빌드 결과에 index.html 이 없습니다")


def swap(out_dir: Path, serve_dir: Path) -> None:
    backup = serve_dir.with_name(serve_dir.name + ".previous")
    if backup.exists():
        shutil.rmtree(backup)
    if serve_dir.exists():
        for attempt in range(5):
            try:
                os.rename(serve_dir, backup)
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(1)
    os.rename(out_dir, serve_dir)
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=int, default=1200, help="잠금을 기다리는 최대 초")
    args = ap.parse_args()
    with BuildLock(LOCK_FILE, args.wait):
        started = time.monotonic()
        build(TMP_DIR)
        swap(TMP_DIR, SERVE_DIR)
        print(f"[build_bundle] BUNDLE_BUILT {SERVE_DIR} ({time.monotonic() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
