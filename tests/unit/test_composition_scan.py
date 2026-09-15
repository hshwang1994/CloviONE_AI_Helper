"""조합 검사 두 벌의 계약 (UI 3차 · 조합 계약 C-7).

- `scripts/check_composition.py` — 화면 소스가 목록 · 필터 · 발을 낱개로 조립하는 자국을 잡는다.
  진짜 소스를 건드리지 않고 **격리된 임시 디렉터리**에 Known Bad · Known Good 화면을 써서 시험한다
  (`test_button_hierarchy_scan.py` 와 같은 관용). 진짜 소스가 지금 통과하는지는 한 시험이 직접 본다.
- `scripts/ui_qa/composition_checks.py` — 실브라우저 조합 검사의 표(검사 이름 · 경로 기대 · 자기검증 기대)가
  서로 어긋나지 않는가. 브라우저 없이 볼 수 있는 부분만 여기서 고정한다(실측 자기검증은
  `local_capture --harness kit_measure --selftest`).
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_composition.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_composition", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rules(mod, rel, text):
    return sorted({rule for rule, _line, _what in mod.scan_file(rel, text)})


def test_the_real_source_currently_passes():
    mod = _load()
    assert mod.main([]) == 0, "화면 소스에 대기 목록 · 대장 예외 밖의 새 조합 위반이 있거나 stale 항목이 남았다"


def test_selftest_is_green():
    assert _load().selftest() == 0


def test_filter_parts_import_is_caught_but_composite_and_toggle_pass():
    mod = _load()
    bad = 'import { FilterSurface, ResultLine } from "../ui/FilterBar.jsx";\n'
    good = 'import { FilterBar, FilterToggle, filterGroupOf } from "../ui/FilterBar.jsx";\n'
    assert _rules(mod, "screens/A.jsx", bad) == ["filter-parts"]
    assert _rules(mod, "screens/A.jsx", good) == []
    # 부품을 구현하는 자리(ui/)는 화면 규칙을 받지 않는다.
    assert _rules(mod, "ui/Other.jsx", bad) == []


def test_card_wrapped_table_depends_on_placement():
    mod = _load()
    wrapped = "export const A = () => (<Card><Stack><DataTable columns={c} rows={r} /></Stack></Card>);\n"
    bleed = 'export const A = () => (<Card><DataTable placement="card" columns={c} rows={r} /></Card>);\n'
    plain = 'export const A = () => (<ListCard><GroupedTickets placement="plain" rows={r} /></ListCard>);\n'
    surface = 'export const A = () => (<Box><DataTable placement="surface" columns={c} rows={r} /></Box>);\n'
    assert _rules(mod, "screens/A.jsx", wrapped) == ["card-wrapped-table"]
    assert _rules(mod, "screens/A.jsx", bleed) == []
    assert _rules(mod, "screens/A.jsx", plain) == []
    assert _rules(mod, "screens/A.jsx", surface) == []


def test_row_button_inside_render_unless_row_actions():
    mod = _load()
    bad = ('const cols = [{ key: "x", render: (r) => (\n'
           '  <Box sx={{ display: "flex", gap: 1 }}>\n'
           '    <Button variant="primary" onClick={() => claim(r)}>나에게 배정</Button>\n'
           '  </Box>\n'
           '), }];\n')
    good = ('const cols = [{ key: "x", render: (r) => <RowActions items={[{ label: "복원", onClick: () => restore(r) }]} /> },\n'
            '  { key: "y", render: (r) => <RowActions><IconButton aria-label="더 보기" /></RowActions> }];\n'
            'export const Page = () => <PageHeader actions={<Button variant="primary">새 문서</Button>} />;\n')
    assert _rules(mod, "screens/A.jsx", bad) == ["row-button"]
    assert _rules(mod, "screens/A.jsx", good) == []


def test_render_span_does_not_leak_past_its_column():
    """`render:` 식은 그 열 객체의 쉼표에서 끝난다 — 다음 열 · 화면 본문의 단추를 render 안으로 세지 않는다."""
    mod = _load()
    text = ('const cols = [\n'
            '  { key: "a", render: (r) => <DotLabel label={r.a} /> },\n'
            '  { key: "b", label: "b" },\n'
            '];\n'
            'export function Page() { return <Button variant="primary">추가</Button>; }\n')
    assert _rules(mod, "screens/A.jsx", text) == []


def test_tag_in_render_list_footer_and_fab_clearance():
    mod = _load()
    assert _rules(mod, "screens/A.jsx", 'const c = [{ render: (r) => <Tag label={r.category} /> }];\n') == ["table-tag"]
    assert _rules(mod, "screens/A.jsx", "export const A = () => <ListFooter total={1} loaded={1} />;\n") == ["list-footer"]
    assert _rules(mod, "screens/A.jsx", 'import { FAB_CLEARANCE } from "../ui/theme.js";\n') == ["fab-clearance"]
    assert _rules(mod, "ui/theme.js", 'export const FAB_CLEARANCE = "5rem";\n') == ["fab-clearance"]


def test_strings_regex_and_jsx_text_do_not_open_elements():
    mod = _load()
    text = ("const a = '<Button>'; const b = \"<ListFooter />\"; const re = /<Tag/;\n"
            "const t = `<DataTable ${x}>`;\n"
            "export const A = () => <Box>don't <b>stop</b> — a < b</Box>;\n")
    assert _rules(mod, "screens/A.jsx", text) == []


def test_ledger_exception_and_dead_exception(tmp_path):
    mod = _load()
    src = tmp_path / "src" / "screens"
    src.mkdir(parents=True)
    (src / "Keep.jsx").write_text("export const A = () => <ListFooter total={1} loaded={1} />;\n", encoding="utf-8")
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        "| 파일 | 조합 규칙 | 이유 | 대체 불가 근거 |\n|---|---|---|---|\n"
        "| `screens/Keep.jsx` | `list-footer` | 보호 화면 백로그 | 보호 화면은 치환만 한다 |\n"
        "| `screens/Gone.jsx` | `row-button` | 사라진 자리 | 없음 |\n", encoding="utf-8")
    new, waiting, stale, dead = mod.scan(tmp_path / "src", ledger, {("screens/Nowhere.jsx", "table-tag")})
    assert new == {}
    assert waiting == {}
    assert stale == [("screens/Nowhere.jsx", "table-tag")]
    assert dead == [("screens/Gone.jsx", "row-button")]


def test_browser_composition_tables_agree():
    from scripts.ui_qa import composition_checks as cc
    from scripts.ui_qa.routes import ALL_ROUTES

    route_ids = {r.id for r in ALL_ROUTES}
    assert set(cc.SELFTEST_EXPECT_BAD) <= set(cc.COMPOSITION_CHECKS)
    assert set(cc.SELFTEST_EXPECT_REASONS) <= set(cc.COMPOSITION_CHECKS)
    assert len(cc.COMPOSITION_CHECKS) == len(set(cc.COMPOSITION_CHECKS)) == 11
    unknown = sorted(set(cc.ROUTE_EXPECT) - route_ids)
    assert unknown == [], f"ROUTE_EXPECT 에 없는 경로 id: {unknown}"
    allowed = {"listSurface", "editorBox", "pageFill", "chat", "skipBudget", "callerWidths", "filterExempt", "footerExempt"}
    for rid, flags in cc.ROUTE_EXPECT.items():
        assert set(flags) <= allowed, (rid, flags)
    # 줄 칸 폭 표 — 최솟값이 최댓값을 넘지 않고, 늘어나는 종류가 없다(검색 슬롯은 이 표 밖이다).
    for kind, (lo, hi) in cc.COMPOSITION_CONTRACT["rowKind"].items():
        assert 0 < lo <= hi <= 18, kind
    assert cc.COMPOSITION_CONTRACT["filterCell"] == 34
    assert cc.COMPOSITION_CONTRACT["prefixInset"] == 14 and cc.COMPOSITION_CONTRACT["prefixGap"] == 6
    assert cc.COMPOSITION_CONTRACT["rowAction"] == 30 and cc.COMPOSITION_CONTRACT["cardPadding"] == 20


def test_kit_measure_reports_both_tables():
    from scripts.ui_qa import kit_measure

    assert kit_measure.ALL_CHECKS[: len(kit_measure.CHECKS)] == kit_measure.CHECKS
    assert set(kit_measure.ALL_CHECKS) >= {"filter_composition", "list_surface", "primary_budget", "chat_composition"}
