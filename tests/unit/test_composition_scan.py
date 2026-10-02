"""조합 검사 두 벌의 계약 (UI 3차 · 조합 계약 C-7).

- `scripts/check_composition.py` — 화면 소스가 목록 · 필터 · 발을 낱개로 조립하는 자국을 잡는다.
  진짜 소스를 건드리지 않고 **격리된 임시 디렉터리**에 Known Bad · Known Good 화면을 써서 시험한다
  (`test_button_hierarchy_scan.py` 와 같은 관용). 진짜 소스가 지금 통과하는지는 한 시험이 직접 본다.
- `scripts/ui_qa/composition_checks.py` — 실브라우저 조합 검사의 표(검사 이름 · 경로 기대 · 자기검증 기대)가
  서로 어긋나지 않는가. 브라우저 없이 볼 수 있는 부분만 여기서 고정한다(실측 자기검증은
  `local_capture --harness kit_measure --selftest`).

qa-contract-change: 줄 칸 자유 입력 폭을 고정 11rem 에서 「이름 + 값 자리 6rem, 11rem 바닥 · 24rem 상한」으로 옮긴다. 감사 로그 「작업(정확히, 예: user.update)」 칸이 11rem 에서 이름만으로 칸을 다 먹어 친 글자가 안 보이던 것을 캡처 눈 대조로 찾았다. 표의 상한 18 은 자유 입력만 24 로 풀고, 나머지 종류 값과 프런트 ROW_KIND 와의 일치를 새로 고정한다.
qa-contract-change: 닫힌 집합 칸의 상한을 13rem 에서 16rem 으로 올리고(선택지로 폭을 잰다, D-530), 「기간」 칸 하나(13rem)와 검색 칸 계단(면 64rem 이상 20 · 44 ~ 64rem 16 · 그 아래 줄 전체)과 표 안 빈 띠 검사를 더한다. 「문제 종류」 값이 13rem 칸에서 여섯 글자 뒤로 잘렸고, 날짜 칸 둘이 필터 줄에서 혼자 높이가 달랐다.
qa-contract-change: 줄 칸 Entity 폭을 「13rem 하나」에서 「기본 13rem, 값이 긴 축의 wide 칸은 필터 면 폭의 계단 13 · 16 · 20rem」으로 옮긴다. 1920 팀 티켓의 프로젝트 칸이 208px 이라 긴 이름이 앞에서 잘렸다. 표에 `entityWide` [13, 20] 과 계단 표 `entityWideSteps` 를 더하고 고정 폭 18rem 상한에서 wide 칸을 뺀다. 프런트 `ROW_KIND.entityWide` 의 컨테이너 질의 · 면의 크기 컨테이너 선언과 같은 수를 말하는지 새로 대조한다.
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


def test_ghost_button_in_message_box_footer_and_plate_head_is_caught():
    """글자 단추(ghost)는 메시지 박스 · 발 · 판 머리 · 페이지 머리 동작의 자리가 아니다(RULES §1 · §3 · §8, 조합 계약 C-4)."""
    mod = _load()
    ghost = '<Button size="sm" variant="ghost" onClick={go}>닫기</Button>'
    cases = {
        "메시지 박스 동작": 'export const A = () => <Callout tone="warn" action={' + ghost + '}>안내</Callout>;\n',
        "메시지 박스 본문": 'export const A = () => <Callout tone="info"><KitButton size="sm" variant="ghost" href={h}>자세히 보기</KitButton></Callout>;\n',
        "판 머리 동작": 'export const A = () => <SectionTitle title="첨부" action={' + ghost + '} />;\n',
        "판 머리(Section)": 'export const A = () => <Section title="첨부" action={' + ghost + '}><Box /></Section>;\n',
        "모달 발": 'export const A = () => <Modal open title="t" footer={<Button variant={"ghost"}>닫기</Button>}>몸</Modal>;\n',
        "카드 발": 'export const A = () => <Card><ActionFooter placement="card">' + ghost + '</ActionFooter></Card>;\n',
        "페이지 머리 동작": 'export const A = () => <PageHeader title="t" actions={' + ghost + '} />;\n',
    }
    for label, text in cases.items():
        assert _rules(mod, "screens/A.jsx", text) == ["ghost-slot"], label
    # app/ 셸 부품도 화면 규칙을 받는다(알림함 · 상태 알림 · AI 도우미 서랍).
    assert _rules(mod, "app/StatusNotices.jsx", cases["메시지 박스 동작"]) == ["ghost-slot"]


def test_ghost_button_inside_lists_and_modal_body_passes():
    """목록 안 부수 동작(첨부 줄 「떼기」 · 전체 보기)과 모달 몸 · 판 자식의 글자 단추는 자리 규칙 밖이다."""
    mod = _load()
    text = (
        "export const A = () => (\n"
        '  <Section title="첨부" action={<Button size="small">파일 올리기</Button>}>\n'
        '    <Stack><Button size="small" variant="ghost" onClick={drop}>떼기</Button></Stack>\n'
        '    <Modal open title="t" footer={<Button>닫기</Button>}><Button size="sm" variant="ghost">전체 보기</Button></Modal>\n'
        '    <Callout tone="info" action={<Button size="sm" startIcon={<Glyph variant="ghost" />}>자세히</Button>}>안내</Callout>\n'
        "  </Section>\n"
        ");\n"
    )
    assert _rules(mod, "screens/A.jsx", text) == []


def test_jsx_after_block_or_line_comment_is_still_read():
    """`return ( /* 설명 */ <Callout …` 의 요소를 주석 끝 글자 뒤로 읽어 놓치지 않는다 — 알림함 · 상태 알림 · 하위 목록 창이 그 자리였다."""
    mod = _load()
    block = (
        "export function A() {\n"
        "  return (\n"
        "    /* 설명 한 줄 */\n"
        "    /* 설명 두 줄 */\n"
        "    <ListFooter total={1} loaded={1} />\n"
        "  );\n"
        "}\n"
    )
    line = (
        "export function A() {\n"
        "  return cond\n"
        "    ? (\n"
        "      // 한 줄 설명\n"
        "      <ListFooter total={1} loaded={1} />\n"
        "    ) : null;\n"
        "}\n"
    )
    assert _rules(mod, "screens/A.jsx", block) == ["list-footer"]
    assert _rules(mod, "screens/A.jsx", line) == ["list-footer"]
    # 주석 안의 태그 글자는 여전히 요소가 아니다.
    assert _rules(mod, "screens/A.jsx", "/* <ListFooter /> */\nexport const A = 1;\n") == []


def test_primary_is_the_last_page_header_action():
    """페이지 머리 동작의 채움은 오른쪽 끝이다(D-501) — 보조 → 더 보기 → 주 동작."""
    mod = _load()
    first = 'export const A = () => <PageHeader title="진단" actions={<><Button variant="primary">진단 수집</Button><Button>복사</Button></>} />;\n'
    last = ('export const A = () => <PageHeader title="백업" actions={<><Button>복원 안내</Button><OverflowMenu items={[]} />'
            '<Button variant="primary">백업 실행</Button></>} />;\n')
    assert _rules(mod, "screens/A.jsx", first) == ["primary-last"]
    assert _rules(mod, "screens/A.jsx", last) == []
    # 머리 밖(본문)의 단추 순서는 이 규칙의 일이 아니다.
    body = 'export const A = () => <Box><Button variant="primary">저장</Button><Button>취소</Button></Box>;\n'
    assert _rules(mod, "screens/A.jsx", body) == []


def test_primary_last_compares_one_branch_at_a_time():
    """삼항의 두 갈래는 각자 한 묶음이다 — 휴지통 문서의 머리와 살아 있는 문서의 머리를 섞지 않는다."""
    mod = _load()
    good = ('export const A = () => <PageHeader title="t" actions={off ? (<><Button>이력</Button><Button variant="primary">복원</Button></>)'
            ' : (<><Button>이동</Button><Button variant="primary">저장</Button></>)} />;\n')
    bad = ('export const A = () => <PageHeader title="t" actions={off ? (<>{can ? <Button variant="primary">복원</Button> : null}'
           '<Button>목록으로</Button></>) : (<><Button variant="primary">저장</Button></>)} />;\n')
    assert _rules(mod, "screens/A.jsx", good) == []
    # 조건부 채움 뒤에 늘 서는 단추가 있으면 둘이 함께 서는 날이 있다.
    assert _rules(mod, "screens/A.jsx", bad) == ["primary-last"]
    # 반례 — 조건부 채움 뒤의 조건부 단추는 함께 서지 않는 갈래일 수 있어 판정하지 않는다(회차 열기 · 회차 닫기).
    exclusive = ('export const A = () => <PageHeader title="t" actions={<>{planned ? <Button variant="primary">회차 열기</Button> : null}'
                 '{active ? <Button>회차 닫기</Button> : null}</>} />;\n')
    assert _rules(mod, "screens/A.jsx", exclusive) == []


def test_primary_last_follows_header_actions_into_their_component(tmp_path):
    """머리 동작을 옆 부품으로 뺀 자리(진단 `DiagnosticActions`)도 본다 — 쓰는 화면과 정의한 파일이 달라도."""
    mod = _load()
    src = tmp_path / "src" / "screens"
    src.mkdir(parents=True)
    (src / "Page.jsx").write_text(
        'export const Page = () => <PageHeader title="진단" actions={<HeadParts onRun={run} />} />;\n', encoding="utf-8")
    (src / "HeadParts.jsx").write_text(
        "export function HeadParts({ onRun }) {\n"
        '  return (<><Button variant="primary" onClick={onRun}>진단 수집</Button>{text ? <Button>복사</Button> : null}</>);\n'
        "}\n"
        "export function Unused() {\n"
        '  return (<><Button variant="primary">머리 밖</Button><Button>보조</Button></>);\n'
        "}\n", encoding="utf-8")
    ledger = tmp_path / "ledger.md"
    ledger.write_text("", encoding="utf-8")
    new, _waiting, _stale, _dead = mod.scan(tmp_path / "src", ledger, set())
    hits = new.get(("screens/HeadParts.jsx", "primary-last"), [])
    assert len(hits) == 1 and "HeadParts(머리 동작 부품)" in hits[0], hits
    # 머리 식 안에 서지 않는 부품(`Unused`)은 묶지 않는다.
    assert not any("Unused" in h for h in hits)


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
    # 열 배분(`column_balance`)과 같은 줄 컨트롤(`control_row`)이 더해져 열넷이다(계획 8.2).
    assert len(cc.COMPOSITION_CHECKS) == len(set(cc.COMPOSITION_CHECKS)) == 14
    unknown = sorted(set(cc.ROUTE_EXPECT) - route_ids)
    assert unknown == [], f"ROUTE_EXPECT 에 없는 경로 id: {unknown}"
    allowed = {"listSurface", "editorBox", "pageFill", "chat", "skipBudget", "callerWidths", "filterExempt", "footerExempt"}
    for rid, flags in cc.ROUTE_EXPECT.items():
        assert set(flags) <= allowed, (rid, flags)
    # 줄 칸 폭 표 — 최솟값이 최댓값을 넘지 않고, 늘어나는 종류가 없다(검색 슬롯은 이 표 밖이다).
    # 고정 폭 종류는 18rem 을 넘지 않는다. 자유 입력은 이름 길이를 따라 11~24rem 사이에 서고(값 자리 6rem),
    # wide Entity 는 필터 면 폭의 계단이라 13~20rem 사이에 선다.
    row_kind = cc.COMPOSITION_CONTRACT["rowKind"]
    assert set(row_kind) == {"entity", "entityWide", "tag", "enum", "text", "date", "datetime", "period"}
    for kind, (lo, hi) in row_kind.items():
        assert 0 < lo <= hi, kind
        if kind not in ("text", "entityWide"):
            assert hi <= 18, kind
    assert row_kind["entity"] == [13, 13] and row_kind["tag"] == [13, 13]
    assert row_kind["entityWide"] == [13, 20]
    assert row_kind["enum"] == [8, 16]
    assert row_kind["period"] == [13, 13]
    assert row_kind["date"] == [11, 11] and row_kind["datetime"] == [18, 18]
    assert row_kind["text"] == [11, 24]
    # wide 계단 — 큰 계단부터 적는다. 면이 넓을수록 칸이 넓고, 가장 넓은 계단이 표의 상한이며, 계단 밖(좁은 면)은 기본 칸과
    # 같은 바닥이다. 그래서 1366(면 1,070px = 66.9rem)은 13rem 그대로다.
    steps = cc.COMPOSITION_CONTRACT["entityWideSteps"]
    assert steps == [[96, 20], [76, 16]]
    assert steps == sorted(steps, reverse=True)
    assert steps[0][1] == row_kind["entityWide"][1]
    assert row_kind["entityWide"][0] == row_kind["entity"][0]
    assert all(row_kind["entityWide"][0] < cell_rem for _surface_rem, cell_rem in steps)
    assert 1070 / 16 < steps[-1][0], "1366 의 필터 면이 wide 계단에 걸리면 기존 줄바꿈이 바뀐다"
    # 브라우저 검사의 표와 프런트 ROW_KIND 가 같은 수를 말한다 — 한쪽만 옮기면 여기서 멈춘다.
    whole_src = (ROOT / "frontend" / "src" / "ui" / "filters.jsx").read_text(encoding="utf-8")
    # 흐름 치수 표(CONTROL_KIND)에도 `text:` 가 있다 — 줄 칸 표(ROW_KIND) 블록만 본다.
    start = whole_src.index("export const ROW_KIND = {")
    filters_src = whole_src[start : whole_src.index("\n};", start)]
    text_line = next(line for line in filters_src.splitlines() if line.strip().startswith("text: {"))
    assert 'minWidth: "11rem"' in text_line and 'maxWidth: "min(24rem, 100%)"' in text_line, text_line
    assert 'width: "6rem"' in text_line and 'flex: "0 0 auto"' in text_line, text_line
    assert 'entity: { flex: "0 0 13rem", width: "13rem"' in filters_src
    assert 'date: { flex: "0 0 11rem", width: "11rem"' in filters_src
    assert 'datetime: { flex: "0 0 18rem", width: "18rem"' in filters_src
    assert 'enum: { flex: "0 0 auto", minWidth: "8rem", maxWidth: "16rem" }' in filters_src
    assert 'period: { flex: "0 0 13rem", width: "13rem"' in filters_src
    # 선택지 폭의 크기 표와 범위가 브라우저 검사의 enum 범위와 같다.
    assert 'export const FILTER_SELECT_SIZES = Object.freeze({ S: 8, M: 10, L: 13, XL: 16 });' in whole_src
    assert 'export const SELECT_WIDTH_RANGE_REM = Object.freeze([8, 16]);' in whole_src
    # wide 칸 — 바닥은 기본 칸과 같은 13rem 이고, 계단은 필터 면(이름 붙은 크기 컨테이너)의 폭을 묻는다. 폭은 사용자 정의 속성
    # 하나로 말한다(계단이 `width` 를 직접 말하면 호출부 sx 의 폭까지 덮는다).
    wide_start = filters_src.index("entityWide: {")
    wide_block = filters_src[wide_start : filters_src.index("\n  },", wide_start)]
    assert '"--filter-wide": "13rem"' in wide_block, wide_block
    assert 'flex: "0 0 var(--filter-wide)", width: "var(--filter-wide)"' in wide_block, wide_block
    for surface_rem, cell_rem in sorted(steps):
        rule = f'"@container filter-surface (min-width: {surface_rem}rem)": {{ "--filter-wide": "{cell_rem}rem" }}'
        assert rule in wide_block, rule
    assert wide_block.index("min-width: 76rem") < wide_block.index("min-width: 96rem"), "넓은 계단이 뒤에 실려야 이긴다"
    assert 'export const FILTER_SURFACE_CONTAINER = { containerType: "inline-size", containerName: "filter-surface" };' in whole_src
    bar_src = (ROOT / "frontend" / "src" / "ui" / "FilterBar.jsx").read_text(encoding="utf-8")
    surface_at = bar_src.index("export function FilterSurface(")
    surface_fn = bar_src[surface_at : bar_src.index("export function", surface_at + 1)]
    assert "...FILTER_SURFACE_CONTAINER," in surface_fn, "필터 면이 크기 컨테이너를 열지 않으면 wide 계단이 늘 바닥에 머문다"
    # 검색 칸 계단 — 프런트 `SEARCH_SLOT_STEPS` 와 같은 수이고, 필터 면의 컨테이너 질의로 선다(남는 폭을 먹지 않는다).
    assert cc.COMPOSITION_CONTRACT["searchSlotSteps"] == [[64, 20], [44, 16]]
    assert 'export const SEARCH_SLOT_STEPS = Object.freeze([[64, "20rem"], [44, "16rem"]]);' in bar_src
    assert 'flexGrow: 0, flexShrink: 0, flexBasis: "var(--search-slot, 20rem)"' in bar_src
    assert cc.COMPOSITION_CONTRACT["emptyBand"] == [56, 72]
    assert cc.COMPOSITION_CONTRACT["filterCell"] == 34
    assert cc.COMPOSITION_CONTRACT["prefixInset"] == 14 and cc.COMPOSITION_CONTRACT["prefixGap"] == 6
    assert cc.COMPOSITION_CONTRACT["rowAction"] == 30 and cc.COMPOSITION_CONTRACT["cardPadding"] == 20


def test_kit_measure_reports_both_tables():
    from scripts.ui_qa import kit_measure

    assert kit_measure.ALL_CHECKS[: len(kit_measure.CHECKS)] == kit_measure.CHECKS
    assert set(kit_measure.ALL_CHECKS) >= {"filter_composition", "list_surface", "primary_budget", "chat_composition"}


def test_kit_measure_switch_contract_matches_the_theme():
    """스위치 프로브의 계약값은 `theme.js::SWITCH` 와 같은 숫자다(D-525) — vitest 가 테마 쪽을, 이 시험이 프로브 쪽을
    못박는다. 한쪽만 바뀌면 프로브가 맞는 스위치를 틀렸다고 하거나 틀린 스위치를 통과시킨다."""
    from scripts.ui_qa import kit_measure

    assert kit_measure.CONTRACT["switch"] == {"trackW": 38, "trackH": 22, "thumb": 16, "hit": 44, "layoutH": 34, "ring": 4}
    assert "switch_geometry" in kit_measure.CHECKS
    # 자체 시험의 기대는 실제 검사 이름만 가리킨다 — 오타 난 이름은 「틀린 견본을 못 잡음」을 영영 못 낸다.
    assert set(kit_measure.SELFTEST_EXPECT_BAD) <= set(kit_measure.CHECKS)
    assert kit_measure.SELFTEST_EXPECT_BAD["switch_geometry"] >= 6
