"""성공 토스트 기본 문구 라벨 사전 회귀 방지 검사 (PA-RC-0025).

`scripts/check_success_toast_labels.py`가 실제 `frontend/src/screens/registry`가 아니라
**격리된 임시 디렉터리**를 보게 해서 시험한다 — 진짜 소스를 건드리지 않는다
(`test_typography_literals_scan.py`와 동일한 관용).
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.unit

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_success_toast_labels.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_success_toast_labels", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_dict(tmp_path: pathlib.Path, keys: list[str]) -> pathlib.Path:
    entries = "\n".join(f'  "{k}": "{k} 문장입니다.",' for k in keys)
    (tmp_path / "successMessages.js").write_text(
        "export const GENERIC_SUCCESS_MESSAGE = \"작업을 완료했습니다.\";\n"
        "export const ACTION_SUCCESS_MESSAGES = {\n"
        f"{entries}\n"
        "};\n",
        encoding="utf-8",
    )
    return tmp_path / "successMessages.js"


def test_the_real_repository_currently_passes():
    """진짜 저장소가 지금 이 검사를 통과하는지 직접 확인한다(사전이 실제 registry/*.js와
    맞는지의 최종 근거) — 다른 시험들은 격리된 디렉터리만 쓰므로 이 확인이 유일하게 실물을
    본다."""
    mod = _load()
    assert mod.main() == 0, "실제 registry/*.js가 사전에 없는 기본 경로 라벨을 갖고 있다"


def test_a_new_unregistered_label_is_caught(tmp_path):
    """revert-to-verify — result/navigate/download/info/subList/localInfo가 전혀 없는(=기본
    경로를 타는) 새 라벨은 사전에 없으면 반드시 걸린다."""
    mod = _load()
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "example.js").write_text(
        'export const EXAMPLE_SCREENS = {\n'
        '  widgets: {\n'
        '    key: "widgets",\n'
        '    actions: [\n'
        '      { label: "새로운액션", variant: "danger", roles: WRITE_ROLES,\n'
        '        path: (r) => "/api/admin/widgets/" + r.id, confirm: "정말?" },\n'
        '    ],\n'
        '  },\n'
        '};\n',
        encoding="utf-8",
    )
    dict_path = _write_dict(tmp_path, ["삭제"])  # "새로운액션"은 등록 안 함
    assert mod.main(registry_dir, dict_path) == 1, "사전에 없는 새 기본 경로 라벨을 놓쳤다"


def test_registered_label_passes(tmp_path):
    mod = _load()
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "example.js").write_text(
        'export const EXAMPLE_SCREENS = {\n'
        '  widgets: {\n'
        '    actions: [\n'
        '      { label: "삭제", variant: "danger", path: (r) => "/x/" + r.id, confirm: "정말?" },\n'
        '    ],\n'
        '  },\n'
        '};\n',
        encoding="utf-8",
    )
    dict_path = _write_dict(tmp_path, ["삭제"])
    assert mod.main(registry_dir, dict_path) == 0


def test_action_with_result_is_excluded(tmp_path):
    """`a.result`가 있는 액션은 finishAction()이 이 기본 경로 자체를 안 타므로, 사전에
    없어도 실패하면 안 된다 — 이게 안 지켜지면 /users의 대량 활성화 같은 opt-out 액션마다
    억지로 사전 항목을 만들어야 한다(요구사항 위반)."""
    mod = _load()
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "example.js").write_text(
        'export const EXAMPLE_SCREENS = {\n'
        '  widgets: {\n'
        '    actions: [\n'
        '      { label: "자체메시지", path: (r) => "/x/" + r.id,\n'
        '        result: (res) => ({ ok: true, msg: "자체 문구: " + res.count }) },\n'
        '    ],\n'
        '  },\n'
        '};\n',
        encoding="utf-8",
    )
    dict_path = _write_dict(tmp_path, [])
    assert mod.main(registry_dir, dict_path) == 0, "result가 있는 액션이 잘못 걸렸다"


@pytest.mark.parametrize("shape", ["navigate", "download", "info", "subList", "localInfo"])
def test_non_mutating_or_self_reporting_shapes_are_excluded(tmp_path, shape):
    """navigate/download/info/subList/localInfo가 있으면 이 기본 토스트 경로를 타지 않는다
    (각각 다른 화면 이동, 파일 다운로드, 조회 전용 안내 모달, 하위 리소스 드로어, 로컬 데이터
    안내 — DataScreen.jsx runAction/SubListDrawer.act()가 전부 toast 없이 return한다)."""
    mod = _load()
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    body = {
        "navigate": '{ label: "이동", navigate: (r) => "#/x/" + r.id }',
        "download": '{ label: "내려받기", download: (qs) => "/x/export.csv?" + qs }',
        "info": '{ label: "안내보기", path: (r) => "/x/" + r.id, info: (res) => String(res) }',
        "subList": '{ label: "하위목록", subList: { title: "t", columns: [] } }',
        "localInfo": '{ label: "로컬안내", localInfo: (sub) => String(sub) }',
    }[shape]
    (registry_dir / "example.js").write_text(
        f'export const EXAMPLE_SCREENS = {{\n  widgets: {{\n    actions: [\n      {body},\n    ],\n  }},\n}};\n',
        encoding="utf-8",
    )
    dict_path = _write_dict(tmp_path, [])
    assert mod.main(registry_dir, dict_path) == 0, f"{shape} 있는 액션이 잘못 걸렸다"


def test_nested_row_action_inside_sublist_is_caught_but_container_is_not(tmp_path):
    """가장 까다로운 경우 — `versionsAction()`류(actions.js) 모양. 바깥 컨테이너
    (`label: "버전 기록"`, own-path 없음, subList만 있음)는 안 걸리고, 그 **안의**
    `rowAction`(own-path 있음, own-result 없음)만 걸려야 한다. 바깥 객체의 `subList` 값
    안에 있는 `path:`가 바깥 객체 자신의 own-key로 잘못 합산되면(중첩 flatten 실패) 이
    시험이 깨진다."""
    mod = _load()
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "example.js").write_text(
        'export const EXAMPLE_SCREENS = {\n'
        '  widgets: {\n'
        '    actions: [\n'
        '      { label: "버전 기록",\n'
        '        subList: {\n'
        '          title: "버전 기록",\n'
        '          endpoint: (r) => "/x/" + r.id + "/versions",\n'
        '          columns: [],\n'
        '          rowAction: {\n'
        '            label: "이 버전으로 롤백", variant: "danger",\n'
        '            path: (sub, r) => "/x/" + r.id + "/rollback",\n'
        '            body: (sub) => ({ version: sub.version }),\n'
        '            confirm: (sub) => "버전 " + sub.version + "(으)로 롤백할까요?",\n'
        '          },\n'
        '        },\n'
        '      },\n'
        '    ],\n'
        '  },\n'
        '};\n',
        encoding="utf-8",
    )
    dict_path = _write_dict(tmp_path, [])  # 사전이 비어 있으니 걸리는 라벨이 있으면 바로 드러난다
    mod2 = mod  # readability
    labels_found = set()
    for path in mod2._iter_registry_files(registry_dir):
        for _lineno, label in mod2._iter_default_path_labels(path):
            labels_found.add(label)
    assert labels_found == {"이 버전으로 롤백"}, (
        "바깥 컨테이너('버전 기록')가 잘못 걸렸거나 중첩 rowAction('이 버전으로 롤백')을 놓쳤다: "
        f"{labels_found!r}"
    )
    # 사전이 비어 있으므로 main()은 정확히 그 하나의 라벨 때문에 실패해야 한다(레지스트리
    # 스캔 자체가 완전히 죽어서 0건 통과하는 거짓 성공이 아님을 함께 확인).
    assert mod.main(registry_dir, dict_path) == 1


def test_action_with_fields_still_reaches_default_path(tmp_path):
    """`a.fields`(입력 폼)가 있는 액션도 제출 후 finishAction()을 그대로 탄다(actionForm
    submit — DataScreen.jsx) — result가 없으면 여전히 사전이 있어야 한다."""
    mod = _load()
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "example.js").write_text(
        'export const EXAMPLE_SCREENS = {\n'
        '  widgets: {\n'
        '    actions: [\n'
        '      { label: "복제", path: (r) => "/x/" + r.id + "/clone",\n'
        '        fields: [{ name: "name", label: "새 이름", type: "text", required: true }] },\n'
        '    ],\n'
        '  },\n'
        '};\n',
        encoding="utf-8",
    )
    dict_path = _write_dict(tmp_path, [])
    assert mod.main(registry_dir, dict_path) == 1, "fields가 있는 기본 경로 액션을 놓쳤다"
    dict_path2 = _write_dict(tmp_path, ["복제"])
    assert mod.main(registry_dir, dict_path2) == 0
