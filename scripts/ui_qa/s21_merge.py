"""표적 재검증 결과를 전수 결과 위에 겹친다 (S21 · W14).

## 왜 필요한가

§7 이 정한 순서는 «전수 1회 → 분류 → 한 번에 고침 → 표적 재검증 → 마지막 전수 1회» 다.
마지막 전수를 돌린 **뒤에** 진단이 깊어져 나온 수정(제품 결함 하나 포함)은 전수를 또
돌려서 확인하지 않는다 — 그 규칙이 «실패 하나 고칠 때마다 전수를 다시 돌리지 마라» 다.
대신 **그 수정이 닿는 화면만** 실브라우저로 다시 돌리고, 그 결과를 전수 결과 위에 겹친다.

겹치는 규칙은 하나다: **같은 Flow 는 나중에 실제로 돌린 결과가 이긴다.** 통과를 남기려고
고르지 않는다 — 나중 회차가 실패했으면 실패가 남는다.

    python -m scripts.ui_qa.s21_merge --base dist/ui-qa/s21 \
        --over dist/ui-qa/s21-r2 dist/ui-qa/s21-chat
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dir(path: Path) -> list[dict]:
    out: list[dict] = []
    for f in sorted(path.glob("flows*.json")):
        if f.name == "flows.json" and len(list(path.glob("flows-*.json"))) > 0:
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        out += data["flows"] if isinstance(data, dict) else data
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="S21 표적 재검증 결과 겹치기")
    ap.add_argument("--base", default="dist/ui-qa/s21")
    ap.add_argument("--over", nargs="+", required=True)
    args = ap.parse_args()

    base_dir = (REPO_ROOT / args.base).resolve()
    base = json.loads((base_dir / "flows.json").read_text(encoding="utf-8"))
    records = base["flows"] if isinstance(base, dict) else base
    index = {r["id"]: i for i, r in enumerate(records)}

    replaced, added = 0, 0
    for name in args.over:
        for rec in load_dir((REPO_ROOT / name).resolve()):
            if rec["id"] in index:
                records[index[rec["id"]]] = rec
                replaced += 1
            else:
                index[rec["id"]] = len(records)
                records.append(rec)
                added += 1

    if isinstance(base, dict):
        base["flows"] = records
        base["merged_over"] = list(args.over)
        payload = base
    else:
        payload = records
    (base_dir / "flows.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    failed = [r for r in records if r.get("status") != "PASS"]
    print("겹쳤다: 덮어쓴 Flow %d · 새로 넣은 Flow %d" % (replaced, added))
    print("합계 %d Flow · 실패 %d건 → %s"
          % (len(records), len(failed), base_dir / "flows.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
