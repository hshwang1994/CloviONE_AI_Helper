"""프로젝트 엑셀 내보내기 — 화면이 보여 주는 것과 **같은 표본, 같은 함수**의 파일판 (D-403).

## 무엇을 담는가

시트 셋: 「개요」(이름·코드·상태·기간·진행률과 그 근거·Health) · 「WBS」(트리를 펼친
행들 — 화면의 `/wbs` 와 같은 `service.project_wbs()` 결과) · 「마일스톤」(서버 정렬
그대로). 파일명은 ASCII 뿐이라(브라우저 인코딩 문제 — users export 와 같은 이유) 한글
프로젝트 이름은 **파일 안** 개요 시트가 든다.

## 담는 값의 계약

* 진행률 `None` 은 **빈 칸**이다 — 0 이 아니다(`project-format.js` 의 네 문구와 같은 계약).
* `unplaced`(순환·깊이 초과로 못 그린 작업)도 **포함**한다 — 화면이 조용히 빼지 않는
  것과 같은 원칙이다. 비고 열이 이유를 말한다.
* 「기한 넘김」은 `models.milestone_unmet` 하나로 판정한다(D-390 — 여섯 번째 사본을
  만들지 않는다).

## 상한

WBS 행은 `EXPORT_MAX_WBS_ROWS` 에서 자른다. 잘리면 마지막 행이 그 사실을 말하고
(audit export 의 잘림 안내와 같은 관례), 파일명에 `-partial` 이 붙는다.
"""

from __future__ import annotations

from app.core.dates import iso_date
from app.core.xlsx import Sheet, build_xlsx
from app.projects.models import Project, milestone_unmet
from app.projects.weekly import MILESTONE_STATUS_LABELS

__all__ = ["EXPORT_MAX_WBS_ROWS", "build_project_workbook", "export_filename"]

#: WBS 시트의 행 상한 — 읽기 상한(`MAX_SHEET_ROWS`)과 같은 값이다.
EXPORT_MAX_WBS_ROWS = 5000

#: 프로젝트 상태의 한국어 표기 — `frontend/src/screens/project-format.js::PROJECT_STATUS_KO`
#: 와 같은 표다. 서버에 이 표가 없어 파일에 계약 값(영어)이 그대로 실리면 받은 사람이
#: 'on_hold' 가 무슨 뜻인지 알 수 없다.
PROJECT_STATUS_KO = {
    "planned": "계획",
    "active": "진행",
    "on_hold": "보류",
    "done": "완료",
}

_TRUNCATION_NOTE = (
    "여기서 잘렸습니다. 전체는 화면의 WBS 탭에서 볼 수 있습니다."
)


def _status_ko(value: str | None) -> str:
    return PROJECT_STATUS_KO.get(value or "", value or "")


def _walk_wbs(nodes, out: list, limit: int) -> bool:
    """트리를 화면과 같은 순서(pre-order)로 편다. 상한에 닿으면 True 를 돌려준다."""
    for node in nodes:
        if len(out) >= limit:
            return True
        indent = "  " * node.depth
        percent = node.progress.percent if node.progress else None
        basis = node.progress.basis if node.progress else None
        out.append((
            node.depth + 1,
            node.ticket_key or "",
            indent + (node.title or ""),
            node.status or "",
            node.est_wd,
            percent,
            basis.done_tasks if basis else None,
            basis.counted_tasks if basis else None,
            "",
        ))
        if _walk_wbs(node.children, out, limit):
            return True
    return False


def build_project_workbook(project: Project, wbs, milestones, health, *, today: str):
    """(bytes, meta) — meta 는 감사 로그의 after 에 그대로 실린다."""
    progress = wbs.progress
    basis = progress.basis
    overdue_count = sum(
        1 for m in milestones
        if m.due_on is not None and iso_date(m.due_on) < today and milestone_unmet(m.status)
    )

    period = " ~ ".join(
        part for part in (iso_date(project.starts_on), iso_date(project.ends_on)) if part
    )
    overview_rows = [
        ("프로젝트 이름", project.name),
        ("코드", project.code or ""),
        ("상태", _status_ko(project.status)),
        ("기간", period or "기간이 아직 없습니다"),
        ("진행률(%)", progress.percent),
        ("진행률 근거", (
            f"작업 {basis.counted_tasks}건 가운데 {basis.done_tasks}건 완료"
            if basis.counted_tasks else "집계할 작업이 없습니다"
        )),
        ("건강도 점수", health.score),
        ("기한 넘긴 마일스톤", overdue_count),
        ("내보낸 날짜", today),
    ]

    wbs_rows: list[tuple] = []
    truncated = _walk_wbs(wbs.roots, wbs_rows, EXPORT_MAX_WBS_ROWS)
    for item in wbs.unplaced:
        if len(wbs_rows) >= EXPORT_MAX_WBS_ROWS:
            truncated = True
            break
        reason_ko = {
            "cycle": "상위 작업 관계가 고리를 이룹니다",
            "too_deep": "계층이 너무 깊어 WBS에 넣지 못했습니다",
        }.get(item.reason, item.reason)
        wbs_rows.append((
            None, item.key or "", item.title or "", "", None, None, None, None, reason_ko,
        ))
    if truncated:
        wbs_rows.append((None, "", _TRUNCATION_NOTE, "", None, None, None, None, ""))

    milestone_rows = [
        (
            m.name,
            iso_date(m.due_on) or "",
            MILESTONE_STATUS_LABELS.get(m.status, m.status),
            m.sort_order,
            "예" if (
                m.due_on is not None and iso_date(m.due_on) < today and milestone_unmet(m.status)
            ) else "",
        )
        for m in milestones
    ]

    body = build_xlsx([
        Sheet("개요", ("항목", "값"), overview_rows, widths=(18, 44)),
        Sheet(
            "WBS",
            ("깊이", "티켓 키", "제목", "상태", "예상 WD", "진행률(%)", "완료", "집계 작업", "비고"),
            wbs_rows,
            widths=(6, 12, 48, 10, 9, 10, 7, 9, 30),
        ),
        Sheet(
            "마일스톤",
            ("이름", "기한", "상태", "순번", "기한 넘김"),
            milestone_rows,
            widths=(36, 12, 8, 6, 9),
        ),
    ])
    meta = {
        "wbs_rows": len(wbs_rows),
        "milestones": len(milestone_rows),
        "truncated": truncated,
    }
    return body, meta


def export_filename(project: Project, now, *, truncated: bool) -> str:
    """ASCII 파일명 — `project-{code|id 앞 8자}-{시각}.xlsx`. 잘렸으면 `-partial`."""
    code = project.code or ""
    ident = code if code and all(
        ch.isascii() and (ch.isalnum() or ch == "-") for ch in code
    ) else str(project.id)[:8]
    suffix = "-partial" if truncated else ""
    return f"project-{ident}{suffix}-{now.strftime('%Y%m%d-%H%M%S')}.xlsx"
