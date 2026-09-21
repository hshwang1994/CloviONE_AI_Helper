"""S21 실행 결과를 Control Plane 원장에 적는다 (W14).

옮겨 적는 자리를 하나로 둔다 — S18 이 `pilot_record.py` 에 쓴 이유 그대로다. 팔백 건을
손으로 옮기면 반드시 두 가지가 일어난다: 옮기다 틀리고, 다시 돌렸을 때 어느 쪽이 최신인지
아무도 모른다.

## 세 가지를 적는다

1. **돌린 Flow 의 결과** — `flows.json` 의 판정을 `FUNCTIONAL_COVERAGE.json` 에 그대로.
   통과하지 않은 것을 통과로 적지 않는다.
2. **없어진 기능** — S11·S14·S15·S20 이 걷어낸 화면과 동작은 `exists: false` 로 적는다.
   「안 봤다」와 「없다」는 같은 칸에 적지 않는다(D-299 의 C1c).
3. **화면 단위 감사 결과** — `ROUTE_COVERAGE.json` 의 `functional_audit` 에 그 화면의
   Flow 집계를 적는다. 시각 축(capture)은 **건드리지 않는다** — 그것은 S22 의 몫이다.

    python -m scripts.ui_qa.s21_record --at 2026-08-25
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FUNC_LEDGER = REPO_ROOT / "docs" / "ui-renewal" / "FUNCTIONAL_COVERAGE.json"
ROUTE_LEDGER = REPO_ROOT / "docs" / "ui-renewal" / "ROUTE_COVERAGE.json"
FLOWS = REPO_ROOT / "dist" / "ui-qa" / "s21" / "flows.json"

HARNESS_BY = "S21 — scripts/ui_qa/s21_e2e.py (실 브라우저 Chromium · 로컬 PostgreSQL 씨앗)"
RUN_TOKEN = "ev:qa_run:s21 (dist/ui-qa/s21/flows.json)"

SERVER_KEYS = ("api_request", "backend_query", "api_response")

WHY_NO_SERVER = {
    "modal_action": "모달을 열고 닫는 것은 화면 안에서 끝난다 — 이 동작 자체는 서버에 아무것도 묻지 않는다(실측 요청 0건).",
    "form_validation": "필수값이나 형식이 어긋나면 보내지 않는 것이 계약이라 서버 왕복이 일어나지 않는다(실측 요청 0건).",
    "filter": "이 화면은 받아 둔 목록을 화면 안에서 거른다 — 조건을 바꿔도 서버를 다시 부르지 않는다(실측 요청 0건).",
    "search": "받아 둔 목록을 화면 안에서 거르는 검색이라 서버 왕복이 없다(실측 요청 0건).",
    "sort": "정렬은 받아 둔 목록의 순서만 바꾼다 — 서버를 다시 부르지 않는다(실측 요청 0건).",
    "pagination": "이 표본은 한 쪽뿐이라 넘길 것이 없다 — 서버를 부르지 않는 것이 맞다(실측 요청 0건).",
    "permission_state": "권한이 없으면 컨트롤 자체를 그리지 않는다 — 눌러서 거절당하는 왕복이 애초에 없다(실측 요청 0건).",
    "row_action": "행의 이 동작은 화면 안에서 끝난다 — 서버를 부르지 않는다(실측 요청 0건).",
    "overflow_action": "넘침 메뉴를 여는 것은 화면 안에서 끝난다 — 서버를 부르지 않는다(실측 요청 0건).",
    "attachment": "이 표본에는 첨부가 없어 올리거나 뗄 것이 없다 — 자리만 확인한다(실측 요청 0건).",
    "combobox": "선택지를 펼치는 것은 화면 안에서 끝난다 — 후보는 이미 받아 두었다(실측 요청 0건).",
    "navigation": "해시 라우팅이라 새 문서를 받지 않는다 — 이 동작 자체는 서버를 부르지 않는다(실측 요청 0건).",
    "back_forward": "뒤로가기는 캐시가 있으면 다시 묻지 않는다 — 요청이 없는 것이 정상이다(실측 요청 0건).",
    "deep_link": "주소를 그대로 다시 여는 것이라 이 동작에서 새 질의가 나가지 않는다(실측 요청 0건).",
    "refresh": "다시 그리는 데 새 질의가 필요 없었다 — 캐시가 답했다(실측 요청 0건).",
    "inline_edit": "화면 안에서 초안만 고친다 — 저장을 누르기 전에는 서버로 나가지 않는다(실측 요청 0건).",
    "read": "받아 둔 응답을 다시 그리는 것이라 이 동작에서 새 질의가 나가지 않는다(실측 요청 0건).",
    "settings_apply": "이 설정은 브라우저에만 남는다 — 서버 왕복이 없는 것이 계약이다(실측 요청 0건).",
    "admin_op": "이 회차는 확인 창까지만 보고 물러났다 — 실행을 안 했으므로 요청도 없다(실측 요청 0건).",
    "create": "이 표본에서는 만들 자리까지만 확인했다(실측 요청 0건).",
    "delete": "이 표본에서는 확인 창까지만 보고 물러났다(실측 요청 0건).",
    "status_change": "이 표본에서는 그 상태의 대상이 없어 부를 것이 없었다(실측 요청 0건).",
    "notification_action": "이 동작은 화면 안에서 끝났다(실측 요청 0건).",
    "approval_action": "이 표본에는 결재할 건이 없어 부를 것이 없었다(실측 요청 0건).",
}
DEFAULT_WHY = "이 동작은 화면 안에서 끝난다 — 실측에서 서버 요청이 한 건도 없었다."

# 제품에서 **없어진** 것들. 화면이 통째로 사라진 것과, 그 화면 안의 동작 하나가 사라진 것을
# 함께 적는다. 근거는 각각 그 회차의 결정이다.
RETIRED_SURFACES = {
    "user_team-docs": "S14·S19 — `/team-docs` 는 `/knowledge` 로 옮겼고 이 주소는 되보내기만 한다",
    "admin_documents": "S11 — 외부 자동화 문서 생성 회차를 걷었다",
    "admin_runners": "S11 — 외부 러너를 걷었다",
    "admin_templates": "S11 — 템플릿 바인딩을 걷었다",
    "admin_workflows": "S11 — n8n 워크플로를 걷었다",
    "admin_integrations": "S11 — 외부 연동 화면을 걷었다",
}
RETIRED_FLOWS = {
    "FF-0118": "S15 — 사용자 화면의 수동 동기화를 걷었다(미러가 없다)",
    "FF-0119": "S15 — 사용자 화면의 수동 동기화를 걷었다(미러가 없다)",
    "FF-0120": "S15 — 사용자 화면의 수동 동기화를 걷었다(미러가 없다)",
    "FF-0895": "S20 — 고를 것이 하나뿐인 「유형」 선택기를 내렸다(D-321)",
    "FF-0989": "S11 — 템플릿이 없어져 «이 정책을 쓰는 템플릿» 하위 목록도 없다",
    "FF-1035": "S11 — 러너가 없어져 그 링크도 없다",
    # 「저장된 뷰」는 **행이 유한하고 작은 화면에는 일부러 안 그린다**(registry `smallSet:
    # true` — 정책 2 · 기능 플래그 11 · 연동 4 · 권한 13행). 조건 조합을 이름 붙여 재사용할
    # 만큼 탐색이 반복되지 않는 자리라 그것은 기능이 아니라 소음이다(C2 의 판단).
    "FF-0978": "제품 판단 — policies 는 smallSet 이라 저장된 뷰를 안 그린다",
    "FF-0868": "제품 판단 — feature-flags 는 smallSet 이라 저장된 뷰를 안 그린다",
    "FF-0899": "제품 판단 — integrations 는 smallSet 이라 저장된 뷰를 안 그린다",
    "FF-1043": "제품 판단 — rbac 는 smallSet 이라 저장된 뷰를 안 그린다",
    # 정렬 컨트롤은 **날짜 열에만** 붙는다 — `data-screen/columnHelpers.jsx::dateCol` 이
    # `sortable: true` 를 주는 유일한 자리이고, `TableHeaderCell` 은 그 선언이 있을 때만
    # 화살표를 그린다(그리고 `canSort = !config.paginated` 라 서버가 쪽을 자르는 목록에는
    # 아예 없다 — 한 쪽만 정렬해 놓고 「가장 오래된 것」이라 말하지 않기 위해서다).
    # 아래 넷은 날짜 열이 없는 표다. 「정렬을 눌러 본다」는 그 화면에 없는 동작이다.
    "FF-0682": "제품 판단 — 정책 사용 통계 표에는 날짜 열이 없어 정렬 컨트롤 자체가 없다",
    "FF-0694": "제품 판단 — 프롬프트 사용 통계 표에는 날짜 열이 없어 정렬 컨트롤이 없다",
    "FF-1000": "제품 판단 — 정책 사용 통계(단독 주소)도 같은 표라 정렬 컨트롤이 없다",
    "FF-1012": "제품 판단 — 프롬프트 사용 통계(단독 주소)도 같은 표라 정렬 컨트롤이 없다",
    "FF-0869": "제품 판단 — 기능 플래그 표에는 날짜 열이 없어 정렬 컨트롤이 없다",
    "FF-1041": "제품 판단 — 권한 매트릭스는 역할이 곧 열이라 정렬할 날짜 열이 없다",
    # 조직 콘솔의 오른쪽 판은 `inSplitView` 로 그려진다(`frontend/src/screens/OrgConsole.jsx`).
    # 그 한 줄이 **검색 상자와 저장된 뷰를 둘 다 내린다** — 왼쪽 트리가 이미 찾는 자리라,
    # 같은 일을 하는 상자를 하나 더 두면 어느 쪽이 지금 걸린 조건인지 알 수 없게 된다.
    "FF-0520": "제품 판단 — 조직도는 분할 뷰의 상세 판이라 저장된 뷰를 안 그린다",
    "FF-0555": "제품 판단 — 부서 목록은 분할 뷰의 상세 판이라 저장된 뷰를 안 그린다",
    "FF-0540": "제품 판단 — 부서 목록은 분할 뷰의 상세 판이라 검색 상자를 안 그린다(왼쪽 트리가 찾는다)",
    # 알림 화면은 `onQuery` 도 `hasIdRoute` 도 선언하지 않는다 — `?id=` 를 주소에 붙여도
    # 소비하는 코드가 없어 상세가 열리지 않고, 제품 어디에도 그런 주소를 만드는 자리가 없다.
    # 「안 봤다」가 아니라 **그 동작이 없다**. 남길 가치가 있는 사실이라 BACKLOG 로도 보낸다.
    "FF-0357": "제품 현황 — 사용자 알림 화면은 ?id= 딥링크를 소비하지 않는다(onQuery 없음)",
    "FF-1184": "제품 현황 — 관리자 알림 화면은 ?id= 딥링크를 소비하지 않는다(onQuery 없음)",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def flow_evidence(record: dict) -> list[str]:
    out = [RUN_TOKEN]
    for shot in record.get("screenshots") or []:
        out.append("ev:capture:%s" % str(shot).replace("\\", "/"))
    return out


def write_flows(ledger: dict, records: list[dict], *, at: str) -> dict:
    by_surface = {s.get("surface"): s for s in ledger.get("surfaces") or []}
    stats = {"written": 0, "passed": 0, "failed": [], "missing": [], "surfaces": set()}
    for rec in records:
        entry = by_surface.get(rec["surface"])
        flow = None
        if entry:
            flow = next((f for f in entry.get("flows") or []
                         if f.get("id") == rec["id"]), None)
        if flow is None:
            stats["missing"].append("%s/%s" % (rec["surface"], rec["id"]))
            continue
        # **없어졌다고 적은 것 위에 판정을 덮지 않는다.** `write_retired` 가 먼저 돌면서
        # `exists: false` 로 적은 Flow 는, 하네스가 그 자리를 눌러 보고 실패로 적어 두었어도
        # 「없는 것을 못 찾았다」는 뜻이다 — 그것을 FAIL 로 남기면 「안 봤다·없다·봤고
        # 통과했다」 셋 중 둘이 한 칸에서 섞인다(D-299 의 C1c · CLAUDE.md §11).
        if flow.get("exists") is False:
            stats["retired_skip"] = stats.get("retired_skip", 0) + 1
            continue
        chain = dict(rec.get("chain") or {})
        flow["status"] = "PASS" if rec["status"] == "PASS" else "FAIL"
        flow["chain"] = chain
        flow["expected"] = rec.get("expected") or {}
        flow["cross_surface"] = rec.get("cross_surface") or []
        flow["evidence"] = flow_evidence(rec)
        flow["audited_at"] = at
        flow["by"] = HARNESS_BY
        if any(chain.get(k) for k in SERVER_KEYS):
            flow.pop("server_free", None)
        else:
            flow["server_free"] = WHY_NO_SERVER.get(rec.get("category"), DEFAULT_WHY)
        if rec["status"] == "PASS":
            stats["passed"] += 1
        else:
            flow["findings"] = [{"note": "; ".join(rec.get("notes") or [])[:400]}]
            stats["failed"].append("%s/%s — %s"
                                   % (rec["surface"], rec["id"],
                                      "; ".join(rec.get("notes") or [])[:160]))
        stats["written"] += 1
        stats["surfaces"].add(rec["surface"])
    return stats


def write_retired(ledger: dict, *, at: str) -> dict:
    """**없어진 것은 «안 봤다» 가 아니라 «없다» 로 적는다** (D-299 의 C1c)."""
    stats = {"surfaces": 0, "flows": 0}
    for entry in ledger.get("surfaces") or []:
        why_surface = RETIRED_SURFACES.get(entry.get("surface"))
        for flow in entry.get("flows") or []:
            why = why_surface or RETIRED_FLOWS.get(flow.get("id"))
            if not why or not flow.get("exists"):
                continue
            flow["exists"] = False
            flow["status"] = "NOT_AUDITED"
            flow["chain"] = {}
            flow["expected"] = {}
            flow["evidence"] = []
            flow["findings"] = []
            flow["audited_at"] = at
            flow["by"] = "S21 — 이 기능이 제품에서 없어졌다(RETIRED): %s" % why
            stats["flows"] += 1
        if why_surface:
            stats["surfaces"] += 1
    return stats


def write_route(route_cov: dict, func_cov: dict, *, at: str, touched: set) -> dict:
    """화면 단위 `functional_audit` 를 그 화면의 Flow 집계로 적는다.

    **시각 축은 안 건드린다.** `visual_audit`·`after_capture`·`responsive_audit` 는 캡처가
    소유하고, 그 회차는 S22 다(§9.4-B). 여기서 그 칸을 채우면 「안 찍었는데 찍었다」가 된다.
    """
    by_id = {s.get("id"): s for s in route_cov.get("surfaces") or []}
    stats = {"pass": 0, "fail": 0, "retired": 0, "skipped": []}
    for entry in func_cov.get("surfaces") or []:
        surface = entry.get("surface")
        row = by_id.get(surface)
        if row is None:
            continue
        # **이 회차가 안 만진 화면의 판정을 다시 쓰지 않는다.** S18 이 감사한 17 화면은
        # 그 회차의 기록이고, 여기서 덮으면 누가 언제 무엇을 봤는지가 사라진다.
        if surface not in touched and surface not in RETIRED_SURFACES:
            continue
        flows = [f for f in entry.get("flows") or [] if f.get("exists")]
        audited = [f for f in flows if f.get("status") in ("PASS", "FAIL")]
        if not audited:
            if surface in RETIRED_SURFACES:
                # **`status` 는 안 건드린다.** 그 칸은 C1c 가 소스와 맞대 보는 자리이고,
                # `/team-docs` 처럼 주소가 되보내기로 살아 있는 화면을 `RETIRED` 로 적으면
                # 게이트가 「RETIRED 인데 소스에 있다」로 되받는다. 여기서 적을 사실은
                # 「이 화면의 기능은 제품에서 없어졌다」 하나다.
                row["functional_audit"] = {
                    "result": "RETIRED", "by": HARNESS_BY, "at": at,
                    "evidence": [], "flows": [],
                    "note": RETIRED_SURFACES[surface]}
                stats["retired"] += 1
            else:
                stats["skipped"].append(surface)
            continue
        failed = [f for f in audited if f.get("status") == "FAIL"]
        row["functional_audit"] = {
            "result": "FAIL" if failed else "PASS",
            "by": HARNESS_BY, "at": at, "evidence": [RUN_TOKEN],
            "flows": [f["id"] for f in audited],
            "passed": len(audited) - len(failed), "failed": len(failed),
        }
        # 화면 상태는 **기능 축만 봤다**는 뜻으로 적는다. `DONE` 은 시각 축(캡처)까지
        # 끝나야 하는 값이고 그 회차는 S22 다(§9.4-B) — 여기서 `DONE` 을 적으면
        # 「안 찍었는데 찍었다」가 된다.
        if not failed and row.get("status") in ("NOT_AUDITED", "IN_PROGRESS", None):
            row["status"] = "FUNCTIONAL_PASS"
        elif failed and row.get("status") == "NOT_AUDITED":
            row["status"] = "IN_PROGRESS"
        if failed:
            stats["fail"] += 1
        else:
            stats["pass"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="S21 결과를 원장에 적는다 (W14)")
    ap.add_argument("--at", required=True, help="감사한 날 (YYYY-MM-DD)")
    ap.add_argument("--flows", default=str(FLOWS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    payload = load(Path(args.flows))
    records = payload.get("flows") or []
    func_cov = load(FUNC_LEDGER)
    route_cov = load(ROUTE_LEDGER)

    retired = write_retired(func_cov, at=args.at)
    flows = write_flows(func_cov, records, at=args.at)
    routes = write_route(route_cov, func_cov, at=args.at, touched=flows["surfaces"])

    left = []
    for entry in func_cov.get("surfaces") or []:
        for fl in entry.get("flows") or []:
            if fl.get("exists") and fl.get("status") == "NOT_AUDITED":
                left.append("%s/%s" % (entry["surface"], fl.get("id")))

    print("Flow 기록: %d건 (통과 %d · 실패 %d)"
          % (flows["written"], flows["passed"], len(flows["failed"])))
    print("RETIRED 로 적은 Flow: %d건 (화면 %d개)" % (retired["flows"], retired["surfaces"]))
    print("화면 판정: PASS %d · FAIL %d · RETIRED %d · 결과 없음 %d"
          % (routes["pass"], routes["fail"], routes["retired"], len(routes["skipped"])))
    if flows["missing"]:
        print("원장에 없는 Flow %d건: %s" % (len(flows["missing"]), flows["missing"][:10]))
    print("남은 NOT_AUDITED(exists:true): %d건" % len(left))
    if left[:20]:
        print("  " + ", ".join(left[:20]))

    if args.dry_run:
        print("(--dry-run — 파일은 안 고쳤다)")
        return 0
    dump(FUNC_LEDGER, func_cov)
    dump(ROUTE_LEDGER, route_cov)
    print("적었다: %s · %s" % (FUNC_LEDGER, ROUTE_LEDGER))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
