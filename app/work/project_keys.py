"""확정된 Project Key 20건 — **사용자가 확인한 표** (U11 · D-197 · D-243).

## 왜 코드에 있는가

확정표가 문서에만 있으면 S13 이 그것을 **손으로 옮겨 적는다.** 20줄을 옮기다 한 줄을
틀리면 그 프로젝트의 티켓 전부가 다른 이름으로 불리고, Key 소유는 영구라 되돌릴 수
없다(D-196). 그래서 기계가 읽는 자리를 정본으로 두고 문서와 맞물려 둔다 —
`tests/unit/test_project_keys_confirmed.py` 가 두 곳이 같은지 확인한다.

S5 의 `permissions.py` · S6 의 `workflow.py` 와 같은 배치다: 코드가 정본이고, 표(문서)는
그 결과이며, 시험이 둘을 묶는다.

## 이름으로 잇는다 — 그리고 **못 찾으면 배정하지 않는다**

`projects.id` 로 못 적는다. 확정 시점에 PostgreSQL 의 `projects` 는 비어 있고(데이터는
아직 SQLite 에 있다) id 는 S13 이 적재할 때 생긴다. 그래서 이름으로 잇되, **추측하지
않는다**: 정확히 일치하거나 공백만 다른 경우만 같은 것으로 보고, 나머지는 «못 찾음»
으로 보고한다. 이름이 비슷하다고 골라 주면 그 티켓들이 남의 프로젝트로 새고, 그 사고는
화면이 정상으로 보이기 때문에 아무도 신고하지 않는다(U11 이 금지한 그것이다).

## 이름은 바뀌었고 Key 는 안 바뀌었다 (2026-08-23 · S13)

확정 당시(2026-08-22) Notion 프로젝트 제목에는 `P. `·`M. `·`D. ` 접두사가 붙어 있었고
14번은 `M. 현대모비스 [OKE KVM 윈도우 기능 개` 로 **잘려 있었다.** 하루 뒤 소스에서
그 접두사가 전부 사라지고 14번 이름도 완성됐다 — 그 상태로는 20건 **전부**가
«못 찾음» 이다(실측: 0/21 일치).

이 파일의 앞 판이 이미 그때 할 일을 적어 두었다: 「소스에서 이름을 고치면 그때 이 줄도
함께 고친다.」 그래서 아래 표의 **이름만** 지금 실측으로 갈고 **Key 는 한 글자도 안
바꿨다.** Key 소유는 영구이고 이름은 그 Key 를 프로젝트에 처음 붙일 때 쓰는 손잡이일
뿐이다 — 한 번 붙고 나면 `projects.code` 가 정본이라 이름이 또 바뀌어도 상관없다.

짝이 맞는지는 이름이 아니라 **티켓 수**로 확인했다(20/20). 이름만 보고 「비슷하니까」로
정하면 그것이 U11 이 금지한 임의 배정이다.

## 옛 이름도 함께 든다 — 추측이 아니라 기록이다

`SUPERSEDED_NAMES` 는 앞 판의 이름 20건이다. 소스가 되돌아가거나 아직 안 따라온 미러를
만나도 같은 Key 로 붙는다. 「비슷한 이름」을 고르는 것이 아니라 **사람이 확인한 정확한
문자열 둘**을 둘 다 아는 것이다.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.core.models_base import utcnow
from app.projects.models import Project
from app.work import keys as keys_mod

# 확정일. 문서(`docs/platform/PROJECT_KEYS.md`)와 같은 날짜여야 한다.
CONFIRMED_ON = "2026-08-22"

# (Key, 프로젝트 이름). **이름은 실측 문자열 그대로**다 — 다듬지 않는다.
#
# 같은 고객사가 여러 줄인 자리(SK하이닉스·굿모닝아이텍·NH손해보험·현대모비스)는 고객사가
# 아니라 그 프로젝트의 시스템/제품 이름으로 갈랐다. 고객사 약어에 번호를 붙이면
# (`SKH1`·`SKH2`) 사람이 말할 때 어느 쪽인지 알 수 없다.
CONFIRMED: tuple[tuple[str, str], ...] = (
    ("SKH", "SK하이닉스 [용인 클러스터 대비]"),
    ("GMDS", "굿모닝아이텍 [사내 디자인 개선]"),
    ("PDX", "포스코DX [P-Cloud 2.0 포털 구축]"),
    ("BRCM", "브로드컴 [VCF9 Value Pack 제작]"),
    ("SGH", "스마일게이트홀딩스 [ClovirONE 2.0 포털 구축]"),
    ("CLV", "굿모닝아이텍 [ClovirONE 2.0 제품 개발]"),
    ("NHFC", "NH손해보험 [금융소비자보호 포털 구축]"),
    ("IIAC", "인천국제공항공사 [클라우드 인프라 고도화]"),
    ("ITAP", "SK하이닉스 [ITAP 포털 유지보수]"),
    ("NHUB", "굿모닝아이텍 [NEXTHub ERP 시스템 개발]"),
    ("MDIP", "현대모비스 [MDIP 시스템 운영/개선]"),
    ("NCDC", "암센터 [NCDC 데이터 분석 포털 구축]"),
    ("NHSM", "NH손해보험 [ClovirSM 구축]"),
    ("OKE", "현대모비스 [OKE KVM 윈도우 기능 개선]"),
    ("NCSP", "엔씨소프트 [NCSpace 포털 구축]"),
    ("KBBD", "KB국민카드 [빅데이터 포털 내부시스템 EOS/디자인 변경]"),
    ("HRFC", "한강홍수통제소 [통합운영관리시스템 구축]"),
    ("MGSM", "새마을금고 [ClovirSM 구축]"),
    ("KISA", "KISA, 한국인터넷진흥원 [ClovirSM 구축]"),
    ("KHNP", "한국수력원자력 [포털 구축]"),
)

# 확정 당시(2026-08-22)의 이름. **버리지 않는다** — 이 문자열을 지우면 「무엇이 무엇으로
# 바뀌었는가」가 이 저장소에서 사라지고, 옛 이름을 든 미러를 만났을 때 붙일 근거도 없다.
SUPERSEDED_NAMES: tuple[tuple[str, str], ...] = (
    ("SKH", "P. SK하이닉스 [용인 클러스터 대비]"),
    ("GMDS", "D. 굿모닝아이텍 [사내 디자인 개선]"),
    ("PDX", "P. 포스코DX [P-Cloud 2.0 포털 구축]"),
    ("BRCM", "M. 브로드컴 [VCF9 Value Pack 제작]"),
    ("SGH", "M. 스마일게이트홀딩스 [ClovirONE 2.0 포털 구축]"),
    ("CLV", "D. 굿모닝아이텍 [ClovirONE 2.0 제품 개발]"),
    ("NHFC", "M. NH손해보험 [금융소비자보호 포털 구축]"),
    ("IIAC", "P. 인천국제공항공사 [클라우드 인프라 고도화]"),
    ("ITAP", "M. SK하이닉스 [ITAP 포털 유지보수]"),
    ("NHUB", "D. 굿모닝아이텍 [NEXTHub ERP 시스템 개발]"),
    ("MDIP", "M. 현대모비스 [MDIP 시스템 운영/개선]"),
    ("NCDC", "M. 암센터 [NCDC 데이터 분석 포털 구축]"),
    ("NHSM", "P. NH손해보험 ClovirSM"),
    # 잘린 채로 확정됐던 이름. 소스가 완성했다.
    ("OKE", "M. 현대모비스 [OKE KVM 윈도우 기능 개"),
    ("NCSP", "M. 엔씨소프트 [NCSpace 포털 구축]"),
    ("KBBD", "M. KB국민카드 [빅데이터 포털 내부시스템 EOS/디자인 변경]"),
    ("HRFC", "M. 한강홍수통제소 [통합운영관리시스템 구축]"),
    ("MGSM", "M. 새마을금고 [ClovirSM 구축]"),
    ("KISA", "M. KISA, 한국인터넷진흥원"),
    ("KHNP", "M. 한국수력원자력 [포털 구축]"),
)

# 적용 결과의 갈래. 「했다/안 했다」 둘로 뭉치면 **왜 안 했는지**를 못 읽는다.
APPLIED = "applied"          # Key 를 새로 잡았다
ALREADY = "already"          # 이미 같은 Key 다 (재실행)
NOT_FOUND = "not_found"      # 그 이름의 프로젝트가 없다
AMBIGUOUS = "ambiguous"      # 같은 이름이 둘 이상이다
OTHER_KEY = "other_key"      # 이미 다른 Key 를 쓰고 있다


def normalize_name(raw: str | None) -> str:
    """이름 비교용 정규형. **공백과 유니코드 합성만** 다듬는다.

    한글은 자모 분리(NFD)로도 저장될 수 있고 그때 눈으로는 같은 글자가 다른 문자열이다.
    공백은 소스에서 두 칸이 되거나 끝에 붙는 일이 흔하다. 그 둘만 맞추고, **철자는
    건드리지 않는다** — 「비슷한 이름」을 같다고 보기 시작하면 U11 이 금지한 임의 배정이
    이름 비교 안으로 숨어 들어온다.
    """
    text = unicodedata.normalize("NFC", raw or "")
    return " ".join(text.split())


BY_NAME: dict[str, str] = {normalize_name(name): key for key, name in CONFIRMED}
BY_KEY: dict[str, str] = {key: name for key, name in CONFIRMED}
BY_OLD_NAME: dict[str, str] = {
    normalize_name(name): key for key, name in SUPERSEDED_NAMES
}


def key_for_name(name: str | None) -> str | None:
    """이 이름의 확정 Key. 표에 없으면 `None` — **비슷한 것을 고르지 않는다.**

    옛 이름도 본다. 옛 이름은 추측이 아니라 **앞 판에 적혀 있던 정확한 문자열**이다.
    """
    normalized = normalize_name(name)
    return BY_NAME.get(normalized) or BY_OLD_NAME.get(normalized)


def apply_confirmed(db: Session, *, now: datetime | None = None) -> dict:
    """확정표를 실제 프로젝트에 적용한다. **재실행해도 같은 결과다.**

    이미 그 Key 를 쓰는 프로젝트는 건너뛰고, **다른 Key 를 쓰는 프로젝트는 건드리지
    않는다** — Key 를 바꾸는 것은 옛 canonical 을 별칭으로 남겨야 하는 별도 동작이고
    (D-195), 그 판단을 이 함수가 대신하면 옛 링크가 조용히 죽는다.

    표에 없는 이름의 프로젝트도 건드리지 않는다. 「이 프로젝트에도 뭔가 붙여 주자」가
    정확히 U11 이 금지한 임의 배정이다.
    """
    stamp = now or utcnow()
    rows = db.execute(select(Project).where(Project.archived_at.is_(None))).scalars().all()

    by_name: dict[str, list[Project]] = {}
    for project in rows:
        by_name.setdefault(normalize_name(project.name), []).append(project)

    report: dict[str, list[dict]] = {
        APPLIED: [], ALREADY: [], NOT_FOUND: [], AMBIGUOUS: [], OTHER_KEY: [],
    }
    superseded = dict(SUPERSEDED_NAMES)
    for key, name in CONFIRMED:
        found = by_name.get(normalize_name(name), [])
        entry = {"key": key, "name": name}
        if not found and key in superseded:
            # 지금 이름으로 못 찾았다. 앞 판의 이름으로 한 번 더 본다 — 소스가 아직
            # 안 따라왔거나 되돌아간 경우다. 이것은 추측이 아니라 기록 조회다.
            found = by_name.get(normalize_name(superseded[key]), [])
            if found:
                entry["matched_name"] = superseded[key]
        if not found:
            report[NOT_FOUND].append(entry)
            continue
        if len(found) > 1:
            # 같은 이름이 둘이면 어느 쪽인지 사람만 안다. 골라 주지 않는다.
            report[AMBIGUOUS].append({**entry, "count": len(found)})
            continue
        project = found[0]
        entry["project_id"] = project.id
        if project.code and keys_mod.normalize(project.code) == key:
            report[ALREADY].append(entry)
            continue
        if project.code:
            report[OTHER_KEY].append({**entry, "current": project.code})
            continue
        try:
            keys_mod.claim(db, project_id=project.id, key=key, now=stamp)
        except ConflictError as exc:
            report[OTHER_KEY].append({**entry, "error": str(getattr(exc, "message", exc))})
            continue
        report[APPLIED].append(entry)
    db.flush()
    return report


def summarize(report: dict) -> str:
    """사람이 한 줄로 읽는 결과. 숫자만 주면 「무엇이 안 됐나」를 다시 물어야 한다."""
    return " · ".join(
        f"{kind} {len(report.get(kind, []))}"
        for kind in (APPLIED, ALREADY, NOT_FOUND, AMBIGUOUS, OTHER_KEY)
    )
