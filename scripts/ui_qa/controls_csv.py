"""조작 요소 대장 (r23 §3A ③) — `screen_ledger` 가 화면 · 상태마다 모은 조작 요소(접근성 트리)를 CSV 한 장으로 편다.

한 줄은 「화면 · 상태 × 역할 · 이름」이다(같은 요소가 여러 폭에 서면 폭을 한 칸에 모은다). 판정은 이 대장이 **잰 것만** 말한다:

  정상(점검)        이름이 있고, 덮이지 않았고, 누름 영역이 24px 이상이고, 비활성이면 까닭이 보인다.
  정상(빈 입력)     입력이 비어 꺼진 보내기 · 저장 단추 — 보낼 것이 없다는 뜻이 화면에 이미 있다(입력 칸 바로 곁).
  정상(창 뒤)       열린 창(모달 · 서랍) 뒤에서 덮인 요소 — 창의 뜻이다.
  확인(까닭 없는 비활성) · 확인(덮임) · 확인(이름 없음)   사람이 PNG 로 다시 볼 줄.
  보류(작은 누름 영역)   24px 미만 — 표 머리 필터 아이콘 · 접힌 「기술 정보」 같은 기존 부품(이번 회차 범위 밖, BACKLOG).

**동작(누른 뒤의 결과)** 은 이 대장이 재지 않는다. 그것은 하네스가 따로 쟀다 — 설정 저장 왕복(`settings_roundtrip`), 구슬 맵 흐름
(`games_e2e --map`), 권한 API(`s21_permission`), 키보드 순회(`keyboard`). 그 하네스가 다룬 화면이면 「동작 확인」 칸에 이름을 적고,
아니면 「미검증(동작)」이다.

    python -m scripts.ui_qa.controls_csv --ledger dist/ui-qa/r23-after-text/ledger.json --out docs/platform/EVIDENCE/ui/2026-10-16-controls.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# 입력이 비면 꺼지는 단추 — 꺼진 까닭(보낼 글이 없다)이 곁의 빈 입력 칸이다.
EMPTY_INPUT_BUTTONS = {"댓글 추가", "답글 추가", "보내기", "질문 전송", "회의록에 추가", "추가", "저장", "되돌리기", "시간 저장",
                       "AI 도우미에게 묻기", "문서 찾기", "API 키 저장하고 확인"}

# 동작까지 하네스가 잰 화면(화면 대장 번호) — 하네스 이름.
BEHAVIOR = {
    "43": "settings_roundtrip(메일)", "43-relay": "settings_roundtrip(메일)", "61": "settings_roundtrip(AI)",
    "28": "settings_roundtrip(프로필) · keyboard", "46": "settings_roundtrip(시스템 정책)", "47": "settings_roundtrip(OS · 미검증 외부)",
    "52": "settings_roundtrip(사용자 · 역할) · s21_permission", "EX-G8": "games_e2e --map · settings_roundtrip(게임방)",
    "27": "games_e2e --map(게임방 추가)", "EX-G0": "games_e2e --map",
    "01": "keyboard", "03": "keyboard", "04": "keyboard", "EX-T1": "keyboard", "05": "keyboard", "30": "keyboard", "26": "keyboard",
    "20": "keyboard", "45": "keyboard", "32": "keyboard", "35": "keyboard", "34": "keyboard", "36": "keyboard", "67": "keyboard",
    "69": "keyboard",
}


def classify(c: dict, modal_open: bool) -> tuple[str, str]:
    role, name = c.get("role") or "", (c.get("name") or "").strip()
    w, h = c.get("w") or 0, c.get("h") or 0
    if not name:
        if w <= 1 and h <= 1:
            return "정상(초점 표지)", "1px 의 보이지 않는 초점 표지(창의 초점 가둠)"
        return "확인(이름 없음)", "접근 이름이 없다"
    if c.get("covered"):
        if modal_open:
            return "정상(창 뒤)", "열린 창 뒤의 요소"
        return "확인(덮임)", "가운데 점을 다른 요소가 덮는다"
    if c.get("disabled") and not c.get("reason"):
        if name in EMPTY_INPUT_BUTTONS or role in ("switch", "textbox", "combobox", "checkbox"):
            return "정상(빈 입력)", "입력 전이거나 위 설정이 꺼져 있어 꺼짐 — 곁의 입력 · 상위 스위치가 까닭이다"
        return "확인(까닭 없는 비활성)", "비활성인데 까닭(설명 · 툴팁)이 없다"
    if role in ("button", "link", "tab", "checkbox", "switch", "radio") and min(w, h) < 24 and c.get("y", 0) >= 0:
        return "보류(작은 누름 영역)", f"{w}×{h}px — 24px 미만"
    return "정상(점검)", ""


def build(ledgers: list[Path], out: Path) -> dict:
    rows: dict[tuple, dict] = {}
    for ledger in ledgers:
        data = json.loads(Path(ledger).read_text(encoding="utf-8"))
        for r in data.get("rows", []):
            for v in r.get("views") or []:
                ov = v.get("overlap") or {}
                # 열린 창 · 메뉴 · 옆 판(사용자 메뉴 · 클로비 패널)이 있으면 그 뒤의 요소가 덮이는 것은 그 창의 뜻이다.
                modal = bool(ov.get("dialogs") or ov.get("popups"))
                for c in ((v.get("controls") or {}).get("items") or []):
                    verdict, note = classify(c, modal)
                    key = (r["id"], c.get("role") or "", (c.get("name") or "").strip()[:80])
                    row = rows.setdefault(key, {
                        "화면": r["id"], "상태 이름": r.get("name", ""), "역할(계정)": r.get("role", ""),
                        "조작 역할": key[1], "이름": key[2], "판정": verdict, "까닭": note,
                        "폭": set(), "동작 확인": BEHAVIOR.get(r["id"], "미검증(동작)"),
                        "확인 방법": "접근성 트리 · 가림 · 크기 · 비활성 까닭 프로브(screen_ledger)",
                    })
                    row["폭"].add(f"{v.get('theme', 'light')}/{v.get('viewport', '')}")
                    # 같은 요소가 폭마다 다르게 판정되면 더 나쁜 쪽을 남긴다(정상 < 보류 < 확인).
                    rank = lambda s: 0 if s.startswith("정상") else (1 if s.startswith("보류") else 2)
                    if rank(verdict) > rank(row["판정"]):
                        row["판정"], row["까닭"] = verdict, note
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["화면", "상태 이름", "역할(계정)", "조작 역할", "이름", "판정", "까닭", "폭", "동작 확인", "확인 방법"]
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for key in sorted(rows):
            row = dict(rows[key])
            row["폭"] = " ".join(sorted(row["폭"]))
            w.writerow(row)
    counts: dict[str, int] = {}
    for row in rows.values():
        counts[row["판정"]] = counts.get(row["판정"], 0) + 1
    behav = sum(1 for row in rows.values() if row["동작 확인"] != "미검증(동작)")
    print("CONTROLS_CSV 줄 %d · %s · 동작 하네스가 다룬 화면의 줄 %d → %s"
          % (len(rows), json.dumps(counts, ensure_ascii=False), behav, out))
    return counts


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="조작 요소 대장(r23)")
    ap.add_argument("--ledger", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    build([Path(x) for x in args.ledger], Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
