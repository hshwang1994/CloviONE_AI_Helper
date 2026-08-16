"""버튼 위계 회귀 방지 검사 (PA-RC-0023 acceptance_criteria 3, 7).

`scripts/check_button_hierarchy.py`가 실제 `frontend/src/screens/registry`가 아니라
**격리된 임시 디렉터리**를 보게 해서 시험한다 — 진짜 소스를 건드리지 않는다
(`test_typography_literals_scan.py`와 같은 관용).
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.unit

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_button_hierarchy.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_button_hierarchy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_real_registry_currently_passes():
    """진짜 저장소가 지금 이 검사를 통과하는지 직접 확인한다 — 다른 시험들은 격리된
    디렉터리만 쓰므로 이 확인이 유일하게 실물을 본다."""
    mod = _load()
    assert mod.main() == 0, "실제 registry/*.js가 버튼 위계 규범을 어기는 새 항목을 갖고 있다"


def test_danger_labeled_delete_passes(tmp_path):
    mod = _load()
    (tmp_path / "ok.js").write_text(
        '{ label: "삭제", variant: "danger", method: "DELETE" },\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def test_primary_and_variant_paired_passes(tmp_path):
    mod = _load()
    (tmp_path / "ok.js").write_text(
        '{ label: "+ 백업 실행", variant: "primary", primary: true, path: () => "/api/admin/backups" },\n',
        encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def test_a_destructive_action_styled_primary_is_caught(tmp_path):
    """🔴 revert-to-verify — 이 실측(2026-08-16)이 실제로 잡았던 모양 그대로 재현한다:
    activeToggle()의 '활성화'가 한때 이 형태였다(그때는 라벨이 달랐지만, 파괴적 라벨이
    실수로 primary가 되는 것과 같은 종류의 결함이다)."""
    mod = _load()
    (tmp_path / "new.js").write_text(
        '{ label: "삭제", variant: "primary", method: "DELETE" },\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 1, "파괴적 라벨이 primary인 새 항목을 놓쳤다"


def test_each_destructive_label_individually_is_caught(tmp_path):
    """DESTRUCTIVE_LABELS 목록의 여덟 라벨 전부가 실제로 걸리는지(목록에 넣기만 하고 정규식이
    한둘만 매칭하는 실수를 방지) 하나씩 확인한다."""
    mod = _load()
    for i, label in enumerate(_load().DESTRUCTIVE_LABELS):
        f = tmp_path / f"case{i}.js"
        f.write_text(f'{{ label: "{label}", variant: "primary" }},\n', encoding="utf-8")
    assert mod.main(tmp_path) == 1


def test_primary_true_without_variant_is_caught(tmp_path):
    """🔴 revert-to-verify — notion-mapping의 '자동 동기화'가 실제로 이 모양이었다:
    primary:true만 있고 variant:"primary"가 없어 평소 툴바에서는 외곽선으로 보였다."""
    mod = _load()
    (tmp_path / "new.js").write_text(
        '{ label: "자동 동기화", primary: true, path: () => "/api/x" },\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 1, "primary:true인데 variant:\"primary\"가 짝지어 있지 않은 항목을 놓쳤다"


def test_non_destructive_primary_is_fine(tmp_path):
    """'재시도'처럼 파괴적이지 않은 동작은 primary여도 정당하다(잡을 이유가 없다)."""
    mod = _load()
    (tmp_path / "ok.js").write_text(
        '{ label: "재시도", variant: "primary", roles: OPS_ROLES },\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def test_comment_mentioning_a_destructive_label_is_not_flagged(tmp_path):
    """오탐 회귀 — 주석 안에서 '삭제'/'primary'를 함께 설명하는 문장을 코드로 오판하지 않는다."""
    mod = _load()
    (tmp_path / "documented.js").write_text(
        "// '삭제' 액션은 절대 variant: \"primary\"로 두면 안 된다.\n"
        '{ label: "삭제", variant: "danger" },\n',
        encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0, "주석 안의 언급을 코드로 오판했다"


def test_test_files_are_not_scanned(tmp_path):
    """`.test.js` 안의 픽스처(일부러 나쁜 값을 넣어 검사 자체를 시험하는 코드)는 대상이
    아니다 — check_typography_literals.py와 같은 관용."""
    mod = _load()
    (tmp_path / "fixture.test.js").write_text(
        '{ label: "삭제", variant: "primary" },\n', encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0


def _screens_file(tmp_path, name, body):
    (tmp_path / name).write_text(
        f"export const X_SCREENS = {{\n{body}\n}};\n", encoding="utf-8",
    )


def test_screen_with_zero_primary_and_no_exception_is_caught(tmp_path):
    """🔴 revert-to-verify — notifications/org-tree가 실제로 이 모양이었다(2026-08-16
    화면 단위 검사를 처음 켰을 때 걸린 두 실물). 예외 등재가 안 된 화면이 primary를
    하나도 안 가지면 대개 실수(액션 하나를 primary로 못 올림)다."""
    mod = _load()
    _screens_file(tmp_path, "new.js", (
        '  widgets: {\n'
        '    key: "widgets", title: "위젯",\n'
        '    actions: [\n'
        '      { label: "새로고침", path: () => "/api/widgets/refresh" },\n'
        '    ],\n'
        '  },\n'
    ))
    assert mod.main(tmp_path) == 1, "0-primary 화면(예외 미등재)을 놓쳤다"


def test_screen_with_zero_primary_but_registered_exception_passes(tmp_path):
    """실제 ZERO_PRIMARY_EXCEPTIONS에 등재된 화면(예: audit)과 같은 key를 쓰면 통과한다 —
    등재는 전역 사전이라 화면 key로 맞춰야 시험할 수 있다."""
    mod = _load()
    _screens_file(tmp_path, "new.js", (
        '  audit: {\n'
        '    key: "audit", title: "감사 로그",\n'
        '    actions: [\n'
        '      { label: "관련 항목 보기", navigate: (r) => "#/x" },\n'
        '    ],\n'
        '  },\n'
    ))
    assert mod.main(tmp_path) == 0


def test_screen_with_edit_block_is_not_flagged_even_without_explicit_variant(tmp_path):
    """`edit:`가 있으면 DataScreen.jsx가 상세 footer에 고정 primary '수정'을 항상 그린다 —
    registry에 variant:"primary"가 한 글자도 없어도 실제로는 primary 버튼이 있다."""
    mod = _load()
    _screens_file(tmp_path, "new.js", (
        '  things: {\n'
        '    key: "things", title: "것들",\n'
        '    edit: { roles: WRITE_ROLES, fields: [] },\n'
        '    actions: [\n'
        '      { label: "삭제", variant: "danger", method: "DELETE" },\n'
        '    ],\n'
        '  },\n'
    ))
    assert mod.main(tmp_path) == 0


def test_screen_with_create_block_is_not_flagged(tmp_path):
    """`create:`가 있으면 헤더에 고정 primary '+ 추가'가 항상 뜬다 — 같은 이유로 안전하다."""
    mod = _load()
    _screens_file(tmp_path, "new.js", (
        '  things: {\n'
        '    key: "things", title: "것들",\n'
        '    create: { roles: WRITE_ROLES, fields: [] },\n'
        '    actions: [],\n'
        '  },\n'
    ))
    assert mod.main(tmp_path) == 0


def test_shared_fragment_without_its_own_key_field_is_not_treated_as_a_screen(tmp_path):
    """actions.js의 `subList` 같은 공유 조각(2-space 블록이지만 자기 key가 없다)을 화면으로
    오판해 0-primary로 잘못 잡지 않는다."""
    mod = _load()
    _screens_file(tmp_path, "new.js", (
        '  subList: {\n'
        '    title: "버전 기록",\n'
        '    columns: [],\n'
        '  },\n'
    ))
    assert mod.main(tmp_path) == 0, "화면이 아닌 공유 조각을 0-primary 화면으로 오판했다"


def test_two_header_actions_both_primary_is_caught(tmp_path):
    """acceptance_criteria 2 — 화면·오버레이당 contained는 정확히 1개. 헤더 툴바에
    variant:"primary" 액션이 둘이면(둘 다 '핵심 동작'을 주장) 사용자가 뭘 눌러야 하는지
    다시 헷갈린다."""
    mod = _load()
    _screens_file(tmp_path, "new.js", (
        '  widgets: {\n'
        '    key: "widgets", title: "위젯",\n'
        '    headerActions: [\n'
        '      { label: "가져오기", variant: "primary", path: () => "/api/x" },\n'
        '      { label: "내보내기", variant: "primary", path: () => "/api/y" },\n'
        '    ],\n'
        '  },\n'
    ))
    assert mod.main(tmp_path) == 1, "헤더에 primary 2개인 화면을 놓쳤다"


def test_create_block_plus_header_action_primary_is_caught(tmp_path):
    """`create:`(암묵 primary "+ 추가")와 headerActions의 명시적 primary가 같은 툴바에
    동시에 뜨면 역시 2개다."""
    mod = _load()
    _screens_file(tmp_path, "new.js", (
        '  widgets: {\n'
        '    key: "widgets", title: "위젯",\n'
        '    create: { roles: WRITE_ROLES, fields: [] },\n'
        '    headerActions: [\n'
        '      { label: "가져오기", variant: "primary", path: () => "/api/x" },\n'
        '    ],\n'
        '  },\n'
    ))
    assert mod.main(tmp_path) == 1


def test_edit_block_plus_row_action_primary_is_caught(tmp_path):
    """🔴 revert-to-verify — actions.js의 activeToggle() '활성화'가 실제로 이 모양이었다:
    `edit:`가 상세 footer에 고정 primary '수정'을 그리는데 행 액션도 variant:"primary"면
    같은 footer에 채운 버튼이 2개 뜬다(D-95)."""
    mod = _load()
    _screens_file(tmp_path, "new.js", (
        '  widgets: {\n'
        '    key: "widgets", title: "위젯",\n'
        '    edit: { roles: WRITE_ROLES, fields: [] },\n'
        '    actions: [\n'
        '      { label: "활성화", variant: "primary", path: () => "/api/x" },\n'
        '    ],\n'
        '  },\n'
    ))
    assert mod.main(tmp_path) == 1, "edit:의 고정 '수정'과 충돌하는 행 primary를 놓쳤다"


def test_one_primary_per_region_passes(tmp_path):
    """헤더에 하나, 상세 행 액션에 하나(각기 다른 영역)는 정상이다 — 영역별로 세어야
    한다(전체 화면 합계로 세면 이 정상 사례를 오탐한다)."""
    mod = _load()
    _screens_file(tmp_path, "new.js", (
        '  widgets: {\n'
        '    key: "widgets", title: "위젯",\n'
        '    create: { roles: WRITE_ROLES, fields: [] },\n'
        '    actions: [\n'
        '      { label: "삭제", variant: "danger", method: "DELETE" },\n'
        '    ],\n'
        '  },\n'
    ))
    assert mod.main(tmp_path) == 0


def test_screen_block_outside_screens_export_is_ignored(tmp_path):
    """`*_SCREENS` export 밖에 있는 2-space 블록(예: 이 파일 자체에 섞인 다른 헬퍼)은
    화면 검사 대상이 아니다."""
    mod = _load()
    (tmp_path / "new.js").write_text(
        '  loose: {\n'
        '    key: "loose", title: "밖",\n'
        '    actions: [],\n'
        '  };\n',
        encoding="utf-8",
    )
    assert mod.main(tmp_path) == 0
