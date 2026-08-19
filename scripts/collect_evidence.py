"""QA 실행 산출물에서 **커밋 가능한 증거**만 뽑아 `docs/ui-renewal/captures/` 로 옮긴다.

    .venv/Scripts/python.exe scripts/collect_evidence.py --label before-renewal --into before

`dist/ui-qa/<label>/` 는 `.gitignore` 되어 있고 한 번 실행에 PNG 584장(약 150MB)이 나온다.
그대로 커밋하면 저장소가 감당하지 못하므로 여기서 **가로 480px 상한으로 재인코딩한 썸네일**만
옮긴다. 원본은 지우지 않는다 — 픽셀 단위 확인이 필요하면 `dist/` 의 원본을 본다.

축소는 순수 Python 으로 한다. Pillow 가 이미 `.venv` 에 있으므로(12.3.0) 새 의존성은 없고,
Playwright 를 띄워 `page.evaluate` 로 줄이는 우회도 필요 없다.

**Pillow 가 없는 환경**에서는 축소할 방법이 없다. 그때는 전부 커밋하는 대신 **Surface 당
대표 조합 1개(`light` · `1920x1080`)의 원본 PNG** 만 옮긴다. 축소할 수 없다는 이유로 584장을
밀어 넣거나, 반대로 0건으로 조용히 끝내는 쪽이 둘 다 더 나쁘다.

## 정직성 규칙

* 없는 라벨, 없거나 깨진 `results.json`, `pages` 0건은 **종료 코드 2**로 멈춘다.
  "0건 수집 성공"으로 끝내면 빈 `captures/` 가 증거 수집 완료로 읽힌다.
* 개별 스크린샷을 못 읽으면 그 항목만 버리고 사유를 `index.json` 의 `skipped` 에 남긴다.
  하나라도 버렸으면 **종료 코드 1** 이다. 조용히 통과시키지 않는다.
* 실행 도중 번들이 바뀐 실행(`build_before` != `build_after`)은 두 빌드가 섞인 증거다.
  버리지는 않되 `index.json` 의 `warnings` 에 남긴다.
* `--dry-run` 은 무엇이 옮겨질지와 예상 용량만 출력하고 파일을 만들지 않는다.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # `scripts.ui_qa.routes` 를 소스에서 읽기 위해
    sys.path.insert(0, str(REPO_ROOT))

DIST_DEFAULT = REPO_ROOT / "dist" / "ui-qa"
CAPTURES_ROOT = REPO_ROOT / "docs" / "ui-renewal" / "captures"

EXIT_OK, EXIT_PARTIAL, EXIT_CANNOT_RUN = 0, 1, 2

THUMB_MAX_WIDTH = 480
# Pillow 가 없을 때만 쓰는 대표 조합. 하나만 고를 수 있다면 가장 흔한 데스크톱 폭이다.
FALLBACK_THEME = "light"
FALLBACK_VIEWPORT = "1920x1080"

try:  # 축소 가능 여부는 런타임에 결정된다 — 없으면 대표 1장 모드로 내려간다.
    from PIL import Image
except Exception:  # noqa: BLE001 — Pillow 부재는 실패가 아니라 다른 동작이다
    Image = None


class CannotRun(Exception):
    """정직하게 실행 불가 — 종료 코드 2."""


def _log(message: str = "") -> None:
    print(message, flush=True)


@dataclass(frozen=True)
class Item:
    route: str
    surface_id: str
    theme: str
    viewport: str
    source: Path
    name: str


# --------------------------------------------------------------------------- #
# 입력
# --------------------------------------------------------------------------- #
def load_results(dist_root: Path, label: str) -> tuple[dict, Path]:
    run_dir = dist_root / label
    if not run_dir.is_dir():
        known = sorted(p.parent.name for p in dist_root.glob("*/results.json"))
        raise CannotRun(
            f"{run_dir} 없음 — 그 라벨로 실행한 QA 결과가 없다.\n"
            f"  결과가 있는 라벨: {', '.join(known) if known else '(없음)'}")
    path = run_dir / "results.json"
    if not path.is_file():
        raise CannotRun(f"{path} 없음 — 실행이 중간에 죽었을 수 있다. QA 를 다시 돌려라.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise CannotRun(f"{path} 를 읽지 못했다 ({type(exc).__name__}: {exc})") from exc
    if not payload.get("pages"):
        raise CannotRun(f"{path} 의 pages 가 0건이다 — 이 실행은 아무 화면도 찍지 못했다.")
    return payload, run_dir


def _source_surface_ids() -> dict[str, str]:
    """현재 소스가 말하는 route id → surface id. 읽지 못하면 빈 매핑."""
    try:
        from scripts.ui_qa.routes import ALL_ROUTES
    except Exception:  # noqa: BLE001 — 소스 없이도 route id 로 계속 갈 수 있다
        return {}
    return {r.id: (r.surface_id or r.id) for r in ALL_ROUTES}


def resolve_surface_ids(results: dict) -> tuple[dict[str, str], list[str]]:
    """route id → ROUTE_COVERAGE 의 surface id.

    `surface_id` 는 `route_inventory` 에 나중에 들어온 필드라, 그 이전 실행의
    `results.json` 에는 없다. 그때는 **현재 소스**에서 채우고 그 사실을 경고로 남긴다 —
    말없이 route id 를 쓰면 `admin_users-detail` / `admin_users-id` 처럼 표기가 다른
    Surface 가 조용히 어긋난다.
    """
    warnings: list[str] = []
    from_source = _source_surface_ids()
    out: dict[str, str] = {}
    filled = 0
    for entry in results.get("route_inventory") or []:
        route_id = entry.get("id")
        if not route_id:
            continue
        surface_id = entry.get("surface_id")
        if not surface_id:
            surface_id = from_source.get(route_id, route_id)
            filled += 1
        out[route_id] = surface_id
    if filled:
        warnings.append(
            f"results.json 의 route_inventory {filled}건에 surface_id 가 없다"
            "(그 필드가 생기기 전 실행) — 현재 소스 scripts/ui_qa/routes.py 에서 채웠다")
    return out, warnings


def build_warnings(results: dict) -> list[str]:
    run = results.get("run") or {}
    before = (run.get("build_before") or {}).get("index_sha256")
    after = (run.get("build_after") or {}).get("index_sha256")
    if before and after and before != after:
        return [f"실행 도중 프런트엔드 번들이 바뀌었다 ({before} → {after}) — "
                "이 증거는 두 빌드가 섞여 있다. 기준선으로 쓰기 전에 다시 찍어라."]
    return []


# --------------------------------------------------------------------------- #
# 계획
# --------------------------------------------------------------------------- #
def plan(results: dict, surfaces: dict[str, str], run_dir: Path, *,
         themes: set[str] | None = None,
         viewports: set[str] | None = None) -> tuple[list[Item], list[dict]]:
    items: list[Item] = []
    skipped: list[dict] = []
    for page in results.get("pages") or []:
        route = page.get("route") or "?"
        theme = page.get("theme") or "?"
        viewport = page.get("viewport") or "?"
        if themes and theme not in themes:
            continue
        if viewports and viewport not in viewports:
            continue
        surface_id = surfaces.get(route, route)
        entry = {"route": route, "surface_id": surface_id,
                 "theme": theme, "viewport": viewport}
        shot = page.get("screenshot")
        if not shot:
            entry["reason"] = (page.get("screenshot_error") or page.get("error")
                               or "이 실행에서 스크린샷을 남기지 못했다")
            skipped.append(entry)
            continue
        source = run_dir / shot
        if not source.is_file():
            entry["reason"] = f"{source} 가 디스크에 없다 (dist/ 가 지워졌을 수 있다)"
            skipped.append(entry)
            continue
        items.append(Item(route=route, surface_id=surface_id, theme=theme,
                          viewport=viewport, source=source,
                          name=f"{surface_id}__{theme}__{viewport}.png"))
    return items, skipped


def representative(items: list[Item]) -> tuple[list[Item], list[str]]:
    """Pillow 가 없을 때 Surface 당 1장만 남긴다."""
    warnings: list[str] = []
    chosen = [i for i in items if i.theme == FALLBACK_THEME and i.viewport == FALLBACK_VIEWPORT]
    if not chosen and items:
        theme, viewport = items[0].theme, items[0].viewport
        chosen = [i for i in items if i.theme == theme and i.viewport == viewport]
        warnings.append(
            f"이 실행에 {FALLBACK_THEME}/{FALLBACK_VIEWPORT} 조합이 없어 "
            f"{theme}/{viewport} 를 대표로 썼다")
    warnings.insert(0,
                    "Pillow 가 없어 썸네일을 만들지 못한다 — 원본 PNG 를 Surface 당 "
                    f"대표 조합 1개({FALLBACK_THEME}/{FALLBACK_VIEWPORT})만 옮겼다. "
                    f"전체 {len(items)}장 중 {len(chosen)}장.")
    return chosen, warnings


def find_collisions(items: list[Item]) -> dict[str, list[str]]:
    """같은 파일명을 노리는 항목. 덮어쓰면 화면 하나가 조용히 사라진다."""
    seen: dict[str, list[str]] = {}
    for item in items:
        seen.setdefault(item.name, []).append(item.route)
    return {name: routes for name, routes in seen.items() if len(routes) > 1}


# --------------------------------------------------------------------------- #
# 쓰기
# --------------------------------------------------------------------------- #
def _flatten(image):
    """알파를 흰 배경에 합성한다 — RGB 로 그냥 convert 하면 투명부가 검게 눌린다."""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return image if image.mode == "RGB" else image.convert("RGB")


def thumbnail_bytes(source: Path, max_width: int = THUMB_MAX_WIDTH) -> bytes:
    with Image.open(source) as opened:
        opened.load()
        image = _flatten(opened)
    width, height = image.size
    # 확대는 하지 않는다 — 390px 캡처를 480px 로 늘려 봐야 없던 선명함이 생기지 않는다.
    if width > max_width:
        image = image.resize((max_width, max(1, round(height * max_width / width))),
                             Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def collect(items: list[Item], dest_dir: Path, *, thumbnails: bool,
            max_width: int, dry_run: bool) -> tuple[list[dict], list[dict], int]:
    written: list[dict] = []
    failed: list[dict] = []
    total_bytes = 0
    for item in items:
        dest = dest_dir / item.name
        entry = {"route": item.route, "surface_id": item.surface_id,
                 "theme": item.theme, "viewport": item.viewport}
        try:
            if thumbnails:
                payload = thumbnail_bytes(item.source, max_width)
                size = len(payload)
                if not dry_run:
                    dest.write_bytes(payload)
            else:
                size = item.source.stat().st_size
                if not dry_run:
                    shutil.copyfile(item.source, dest)
        except Exception as exc:  # noqa: BLE001 — 한 장이 실패해도 나머지는 모은다
            entry["reason"] = f"{type(exc).__name__}: {exc} ({item.source})"
            failed.append(entry)
            continue
        total_bytes += size
        entry["bytes"] = size
        written.append(entry)
    return written, failed, total_bytes


def orphans(dest_dir: Path, keep: set[str]) -> list[str]:
    """이번 index 에 없는 기존 PNG. 지우지 않고 알리기만 한다 — 남의 증거일 수 있다."""
    if not dest_dir.is_dir():
        return []
    return sorted(p.name for p in dest_dir.glob("*.png") if p.name not in keep)


def _repo_relative(path: Path) -> str:
    """저장소 상대 경로. 저장소 밖이면 절대 경로 그대로 — 여기서 죽지는 않는다.

    `--out-dir` 로 저장소 밖 산출물을 가리킬 수 있으므로 `relative_to` 만 믿으면
    증거 수집 전체가 경로 하나 때문에 멈춘다.
    """
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def build_index(results: dict, run_dir: Path, into: str, *, written: list[dict],
                skipped: list[dict], warnings: list[str], thumbnails: bool,
                max_width: int) -> dict:
    run = results.get("run") or {}
    label = run.get("label") or run_dir.name
    build_sha = (run.get("build_before") or {}).get("index_sha256") or ""
    # results.json 에는 **페이지별 시각이 없다**. 실행 시작 시각이 가장 가까운 사실이므로
    # 그것을 적고, 더 정밀한 것을 아는 척하지 않는다.
    captured_at = run.get("started_at") or ""
    results_json = _repo_relative(run_dir / "results.json")
    rel_dir = _repo_relative(CAPTURES_ROOT / into)

    captures = []
    for entry in written:
        name = f"{entry['surface_id']}__{entry['theme']}__{entry['viewport']}.png"
        captures.append({
            "surface_id": entry["surface_id"],
            "route": entry["route"],
            "theme": entry["theme"],
            "viewport": entry["viewport"],
            "path": f"{rel_dir}/{name}",
            "build_index_sha256": build_sha,
            "label": label,
            "captured_at": captured_at,
            "results_json": results_json,
            "bytes": entry.get("bytes"),
        })
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "into": into,
        "label": label,
        "results_json": results_json,
        "build_index_sha256": build_sha,
        "captured_at": captured_at,
        "encoding": (f"thumbnail PNG, 가로 {max_width}px 상한" if thumbnails
                     else "원본 PNG (Pillow 없음 — 대표 조합만)"),
        "warnings": warnings,
        "captures": captures,
        "skipped": skipped,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts/collect_evidence.py",
        description="dist/ui-qa/<label>/ 의 캡처를 docs/ui-renewal/captures/<before|after>/ 로 옮긴다")
    parser.add_argument("--label", required=True, help="QA 실행 라벨 (dist/ui-qa/<label>/)")
    parser.add_argument("--into", required=True, choices=("before", "after"),
                        help="docs/ui-renewal/captures/ 아래 어느 쪽에 넣을지")
    parser.add_argument("--out-dir", default=str(DIST_DEFAULT), help="QA 산출물 루트")
    parser.add_argument("--max-width", type=int, default=THUMB_MAX_WIDTH,
                        help=f"썸네일 가로 상한 (기본 {THUMB_MAX_WIDTH})")
    parser.add_argument("--themes", nargs="*", default=None, help="이 테마만 옮긴다")
    parser.add_argument("--viewports", nargs="*", default=None, help="이 뷰포트만 옮긴다")
    parser.add_argument("--dry-run", action="store_true",
                        help="무엇이 옮겨질지와 예상 용량만 출력하고 파일은 만들지 않는다")
    return parser


def _split_csv(values: list[str] | None) -> set[str] | None:
    out = {part.strip() for value in values or [] for part in value.split(",") if part.strip()}
    return out or None


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:  # 한국어 라벨이 cp949 콘솔에서 살아남아야 한다
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    args = build_parser().parse_args(argv)
    if args.max_width < 1:
        # 그냥 두면 PIL 이 항목마다 예외를 뱉어 "증거 584장 유실" 로 끝난다 — 원인은
        # 유실이 아니라 플래그 오타다. 진단이 틀리면 다음 사람이 dist/ 부터 뒤진다.
        _log(f"[FATAL] --max-width 는 1 이상이어야 한다 (받은 값: {args.max_width}).")
        return EXIT_CANNOT_RUN

    try:
        results, run_dir = load_results(Path(args.out_dir), args.label)
    except CannotRun as exc:
        _log(f"[FATAL] {exc}")
        return EXIT_CANNOT_RUN

    surfaces, warnings = resolve_surface_ids(results)
    warnings.extend(build_warnings(results))

    items, skipped = plan(results, surfaces, run_dir,
                          themes=_split_csv(args.themes),
                          viewports=_split_csv(args.viewports))
    if not items:
        _log(f"[FATAL] {run_dir / 'results.json'} 의 {len(results['pages'])}개 기록 중 옮길 수 있는 "
             f"캡처가 0건이다 (필터 결과 또는 스크린샷 부재 {len(skipped)}건).")
        for entry in skipped[:5]:
            _log(f"        - {entry['route']} {entry['theme']}/{entry['viewport']}: "
                 f"{entry['reason']}")
        return EXIT_CANNOT_RUN

    thumbnails = Image is not None
    if not thumbnails:
        items, extra = representative(items)
        warnings.extend(extra)
        if not items:
            _log("[FATAL] Pillow 가 없고 대표 조합도 고르지 못했다.")
            return EXIT_CANNOT_RUN

    collisions = find_collisions(items)
    if collisions:
        _log("[FATAL] 파일명이 겹치는 Surface 가 있다 — 덮어쓰면 화면 하나가 조용히 사라진다:")
        for name, routes in sorted(collisions.items()):
            _log(f"        {name} ← {', '.join(routes)}")
        return EXIT_CANNOT_RUN

    dest_dir = CAPTURES_ROOT / args.into
    if not args.dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    written, failed, total_bytes = collect(items, dest_dir, thumbnails=thumbnails,
                                           max_width=args.max_width, dry_run=args.dry_run)
    skipped = skipped + failed
    index = build_index(results, run_dir, args.into, written=written, skipped=skipped,
                        warnings=warnings, thumbnails=thumbnails, max_width=args.max_width)

    left_over = orphans(dest_dir, {Path(c["path"]).name for c in index["captures"]})
    if left_over:
        index["warnings"].append(
            f"이 index 에 없는 기존 PNG {len(left_over)}장이 {dest_dir} 에 남아 있다 "
            f"(예: {', '.join(left_over[:3])}) — 지우지 않았다. 다른 라벨의 증거인지 확인하라.")

    _log("=" * 78)
    _log(f"증거 수집  label={index['label']}  → docs/ui-renewal/captures/{args.into}/"
         + ("  [DRY RUN]" if args.dry_run else ""))
    _log(f"방식: {index['encoding']}")
    _log(f"대상 {len(written)}장, 약 {total_bytes / 1024 / 1024:.1f} MB")
    _log("=" * 78)
    for capture in index["captures"][:10]:
        _log(f"  {capture['path']}")
    if len(index["captures"]) > 10:
        _log(f"  … 그리고 {len(index['captures']) - 10}장 더")

    if skipped:
        _log("")
        _log(f"[주의] 옮기지 못한 캡처 {len(skipped)}건 (index.json 의 skipped 에 사유가 있다):")
        for entry in skipped[:10]:
            _log(f"  - {entry['route']} {entry['theme']}/{entry['viewport']}: {entry['reason']}")
        if len(skipped) > 10:
            _log(f"  … 그리고 {len(skipped) - 10}건 더")
    for warning in index["warnings"]:
        _log(f"[WARN] {warning}")

    if args.dry_run:
        _log("")
        _log("[DRY RUN] 파일을 만들지 않았다. index.json 도 쓰지 않았다.")
        return EXIT_PARTIAL if skipped else EXIT_OK

    index_path = dest_dir / "index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    _log("")
    _log(f"index.json : {index_path} ({index_path.stat().st_size:,} bytes, "
         f"{len(index['captures'])}장)")
    if skipped:
        # 옮기다 실패한 것만 세면 **애초에 스크린샷이 없던 페이지**가 종료 코드에서 사라진다.
        # 그쪽이 오히려 흔하다(캡처가 타임아웃했거나 dist/ 가 지워진 경우) — 그걸 0 으로
        # 돌려주면 `collect_evidence … && git add` 같은 호출이 절반짜리 증거를 성공으로 커밋한다.
        lost = len(skipped) - len(failed)
        _log(f"[FAIL] 캡처 {len(skipped)}장이 빠졌다 — 증거가 불완전하다 "
             f"(옮기다 실패 {len(failed)}장 · 이 실행에 스크린샷 자체가 없음 {lost}장).")
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
