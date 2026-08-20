"""W5 가 고친 세 Assertion 을 **반례로** 검증한다.

## 왜 필요한가

이 저장소의 규율은 두 방향이다 — 측정값이 이상하면 프로브를 먼저 의심하고
(`scripts/ui_qa/README.md`), 동시에 **통과한 검사는 표본 수를 확인한다**(F-W4-15: 판독 슬롯
검사가 아무것도 안 재면서 통과하고 있었다). W5 는 세 검사의 판정 규칙을 고쳤는데, 규칙을
고치는 일은 그 두 실패 모드를 **동시에** 만들 수 있다: 위양성을 없애려다 진짜 결함까지
못 보게 되는 것이다.

그래서 판정 규칙을 고친 그 커밋에서 **일부러 결함을 심은 DOM** 과 **일부러 정상인 DOM** 을
같은 프로브에 통과시켜, 전자는 잡히고 후자는 안 잡히는 것을 확인한다. 제품 화면이 아니라
**합성 DOM** 을 쓰는 이유는 제품이 고쳐지면 반례가 사라지기 때문이다 — 반례는 제품과
독립적으로 살아 있어야 다음 사람이 규칙을 되돌릴 때 걸린다.

## 쓰는 법

    python -m scripts.ui_qa.probe_selftest            # 전부
    python -m scripts.ui_qa.probe_selftest --json     # 기계 판독용

종료 코드: 0 전부 기대대로 · 1 하나라도 어긋남 · 2 브라우저를 못 띄움(정직하게 실행 불가).
"""

from __future__ import annotations

import argparse
import json
import sys

from . import assertions

# 각 사례는 `#main-content` 안에 그대로 꽂히는 조각이다. 프로브가 `MAIN` 밖은 보지 않는다.
CASES: list[dict] = [
    {
        "name": "isolated_control_row/고아 줄은 잡힌다",
        "assertion": "isolated_control_row",
        "expect": "fail",
        "why": ("지시 76 이 이름으로 지목한 형태 — **격자가 줄바꿈을 강제하는데 윗줄에는 자리가 "
                "남아 있다**. `/board` 의 실제 원인이 정확히 이 모양이었다: 검색창이 2칸을 "
                "차지해 정렬 select 가 혼자 다음 줄로 밀렸고, 격자 오른쪽은 그대로 비어 있었다. "
                "**flex-wrap 에서는 이 모양이 나올 수 없다** — 줄이 끝나는 이유가 «꽉 찼기 때문» "
                "뿐이라서다. 그래서 W5 가 격자를 흐름으로 바꾼 것 자체가 이 결함의 제거다."),
        "html": """
        <div style="width:1200px">
          <div style="display:grid;grid-template-columns:repeat(2,200px);gap:12px;width:100%">
            <input style="grid-column:span 2;height:36px">
            <select style="height:36px"><option>혼자</option></select>
          </div>
        </div>""",
    },
    {
        "name": "isolated_control_row/오른쪽 끝에 놓은 묶음은 안 잡힌다",
        "assertion": "isolated_control_row",
        "expect": "pass",
        "why": "`ToolbarEnd` 관용 — 밀려난 것이 아니라 놓은 것이다. 고아는 왼쪽에 남는다.",
        "html": """
        <div style="width:1200px">
          <div style="display:flex;flex-wrap:wrap;gap:12px;width:100%">
            <div style="flex:1 1 100%;height:36px">머리줄</div>
            <div style="margin-inline-start:auto"><button style="height:36px">정렬</button></div>
          </div>
        </div>""",
    },
    {
        "name": "isolated_control_row/좁은 화면의 정상 wrap 은 안 잡힌다",
        "assertion": "isolated_control_row",
        "expect": "pass",
        "why": ("390 에서 컨트롤 하나가 줄을 통째로 쓰는 것은 밀려난 것이 아니라 **접힌** 것이다. "
                "윗줄에 여유가 없으면 그 줄은 고아가 아니다 — 실브라우저에서 `/policies` 390 이 "
                "이 모양이었다(윗줄 여유 0)."),
        "html": """
        <div style="width:360px">
          <div style="display:flex;flex-wrap:wrap;gap:12px;width:100%">
            <input style="flex:1 1 100%;height:36px">
            <select style="width:128px;height:36px"><option>상태</option></select>
          </div>
        </div>""",
    },
    {
        "name": "control_baseline_mismatch/같은 줄의 높이 차는 잡힌다",
        "assertion": "control_baseline_mismatch",
        "expect": "fail",
        "why": "한 줄에 선 버튼 둘의 높이가 12px 갈린다 — 4K 에서 실제로 일어나던 형태.",
        "html": """
        <div style="display:flex;gap:12px;align-items:center;width:800px">
          <button style="height:34px;width:120px">가</button>
          <button style="height:46px;width:120px">나</button>
        </div>""",
    },
    {
        "name": "control_baseline_mismatch/세로로 쌓인 둘은 안 잡힌다",
        "assertion": "control_baseline_mismatch",
        "expect": "pass",
        "why": "2단 레이아웃의 서로 다른 열에서 첫 후손 컨트롤을 뽑아 짝짓던 위양성(최대 257px).",
        "html": """
        <div style="display:flex;gap:12px;width:900px">
          <div style="width:440px"><button style="height:34px">위</button>
            <div style="height:200px"></div></div>
          <div style="width:440px"><div style="height:200px"></div>
            <button style="height:46px">아래</button></div>
        </div>""",
    },
    {
        "name": "control_baseline_mismatch/화면을 덮는 서랍은 본문과 짝지어지지 않는다",
        "assertion": "control_baseline_mismatch",
        "expect": "pass",
        "why": ("`position:absolute` 인 아이는 형제와 나란히 선 것이 아니라 그 **위에 덮여** 있다. "
                "세로로 겹친다는 이유만으로 한 줄로 묶으면 서랍의 40px 버튼과 제목줄의 34px 아이콘 "
                "버튼이 «높이 6px 차이» 가 된다 — `/chat` 390px 에서 실제로 그렇게 잡혔다."),
        "html": """
        <div style="position:relative;width:390px;height:300px">
          <div style="display:flex;align-items:center;gap:8px;height:56px;padding:0 8px">
            <button style="height:34px;width:34px"></button>
            <span style="flex:1">대화 제목</span>
            <button style="height:34px;width:34px"></button>
          </div>
          <div style="position:absolute;top:0;left:0;width:300px;height:300px;background:#fff">
            <button style="height:40px;width:200px">새 대화</button>
          </div>
        </div>""",
    },
    {
        "name": "control_baseline_mismatch/닫혀서 화면 밖에 선 서랍은 아예 안 재진다",
        "assertion": "control_baseline_mismatch",
        "expect": "pass",
        "why": ("`translateX(-100%)` 로 왼쪽 밖에 나간 서랍은 사용자가 볼 수 없다. `visibility` 도 "
                "`display` 도 정상이라 예전 판정은 «보인다» 였고, 그래서 390px 에서 닫힌 앱 "
                "사이드바(left −248)의 버튼들이 본문 컨트롤과 함께 재졌다."),
        "html": """
        <div style="display:flex;align-items:center;gap:8px;width:390px;height:56px;overflow:hidden;
                    margin-left:-24px"><!-- main 의 좌측 패딩을 상쇄해 서랍이 문서 x=0 에서 시작하게 한다 -->
          <div style="transform:translateX(-100%);width:248px;flex:0 0 248px">
            <button style="height:48px;width:200px">메뉴</button>
          </div>
          <button style="height:34px;width:34px"></button>
          <button style="height:34px;width:34px"></button>
        </div>""",
    },
    {
        "name": "control_baseline_mismatch/카드 격자의 키 차이는 잡히지 않는다",
        "assertion": "control_baseline_mismatch",
        "expect": "pass",
        "why": ("누를 수 있다고 다 컨트롤은 아니다. 문서 카드는 격자에 놓인 **판**이고 제목이 "
                "두 줄이면 옆 카드보다 당연히 높다 — `/team-docs` 1920 에서 26.6px 로 잡혔다."),
        # 실제 `/team-docs` 의 모양대로 **도구 줄 + 카드 격자**를 함께 둔다 — 카드만 두면
        # 잴 것이 없어 `skip` 이 되어 "정상을 통과시킨다" 를 보이지 못한다.
        "html": """
        <div style="display:flex;gap:8px;align-items:center;width:900px;margin-bottom:16px">
          <input style="flex:1;height:36px" value="검색어">
          <button style="height:36px;width:80px">정렬</button>
        </div>
        <div style="display:flex;gap:16px;width:900px;align-items:flex-start">
          <button style="width:280px;height:150px;text-align:left">Tanzu Kubernetes 클러스터 버전
            업그레이드 및 마이그레이션 지원 가이드</button>
          <button style="width:280px;height:120px;text-align:left">1.Docker 교육</button>
        </div>""",
    },
    {
        "name": "control_baseline_mismatch/아래를 맞춘 입력줄은 잡히지 않는다",
        "assertion": "control_baseline_mismatch",
        "expect": "pass",
        "why": ("키가 다른 둘은 보통 **아래를 맞춘다**(채팅 입력줄). 그때 중심선이 갈리는 것은 "
                "결함이 아니라 배치다 — `/chat` 390 에서 10.5px 로 잡혔다."),
        "html": """
        <div style="display:flex;gap:8px;align-items:flex-end;width:390px;padding:8px">
          <textarea style="flex:1;height:56px"></textarea>
          <button style="height:34px;width:64px">전송</button>
        </div>""",
    },
    {
        "name": "control_baseline_mismatch/두 줄로 접힌 제목은 컨트롤로 안 센다",
        "assertion": "control_baseline_mismatch",
        "expect": "pass",
        "why": ("문서 카드의 제목은 접근성 때문에 `<button>` 이지만 높이를 정하는 것은 padding 이 "
                "아니라 **글이 몇 줄로 접히느냐**다. 긴 제목 두 줄(53.2) vs 짧은 제목 한 줄(26.6) 을 "
                "«버튼 높이가 어긋났다» 로 읽으면 카드 목록이 통째로 결함이 된다 — `/team-docs` 실측."),
        "html": """
        <div style="display:flex;gap:8px;align-items:center;width:900px;margin-bottom:16px">
          <input style="flex:1;height:36px" value="검색어">
          <button style="height:36px;width:80px">정렬</button>
        </div>
        <div style="display:flex;gap:16px;width:900px;align-items:flex-start">
          <div style="width:280px"><button style="width:260px;font:16px/26.6px system-ui;
            padding:0;border:0;background:none;text-align:left">Tanzu Kubernetes 클러스터 버전 업그레이드 및
            마이그레이션 지원 가이드</button></div>
          <div style="width:280px"><button style="width:260px;font:16px/26.6px system-ui;
            padding:0;border:0;background:none;text-align:left">1.Docker 교육</button></div>
        </div>""",
    },
    {
        "name": "plain_dropdown_for_entity/Entity 를 맨 텍스트 상자로 받으면 잡힌다",
        "assertion": "plain_dropdown_for_entity",
        "expect": "fail",
        "why": ("이 제품에서 **가장 나쁜 형태**다 — 「‘사용자’ 화면에서 ID를 복사해 붙여 넣으세요」. "
                "예전 순회 대상은 select/combobox 셋뿐이라 이런 자리 9곳이 전부 skip 이었다."),
        "html": """
        <div style="width:600px">
          <label for="u1">담당자</label>
          <input id="u1" type="text" style="width:280px;height:36px">
        </div>""",
    },
    {
        "name": "plain_dropdown_for_entity/이유를 선언한 자유 텍스트는 안 잡힌다",
        "assertion": "plain_dropdown_for_entity",
        "expect": "pass",
        "why": ("후보 목록이 존재하지 않는 값(외부 시스템 식별자)이 있다. 그때는 선언이 "
                "`data-free-text=\"<이유>\"` 로 말한다 — 끄는 것이 아니라 **종류를 선언**하는 것이다."),
        "html": """
        <div style="width:600px">
          <label for="u2">담당자</label>
          <input id="u2" type="text" data-free-text="외부 워크스페이스의 식별자다" style="width:280px;height:36px">
          <!-- 검사가 실제로 돌았음을 보이려고 통과하는 자리를 하나 둔다(전부 빠지면 skip 이다). -->
          <label for="u3">프로젝트</label>
          <input id="u3" role="combobox" aria-autocomplete="list" style="width:200px;height:36px">
        </div>""",
    },
    {
        "name": "plain_dropdown_for_entity/새로 적는 이름 칸은 안 잡힌다",
        "assertion": "plain_dropdown_for_entity",
        "expect": "pass",
        "why": ("「부서 **이름**」은 기존 부서를 가리키는 참조가 아니라 새로 적는 값이다. "
                "여기에 선택기를 요구하면 «부서를 만들려면 먼저 부서를 골라야 한다» 가 된다."),
        "html": """
        <div style="width:600px">
          <label for="n1">부서 이름</label>
          <input id="n1" type="text" style="width:280px;height:36px">
          <label for="n2">러너 버전</label>
          <input id="n2" type="text" style="width:280px;height:36px">
          <label for="n3">프로젝트</label>
          <input id="n3" role="combobox" aria-autocomplete="list" style="width:200px;height:36px">
        </div>""",
    },
    {
        "name": "plain_dropdown_for_entity/후보를 주는 입력(datalist)은 안 잡힌다",
        "assertion": "plain_dropdown_for_entity",
        "expect": "pass",
        "why": "칠 수 있고 **후보도 나온다**. 이 검사가 요구하는 것은 검색 가능성이지 위젯 종류가 아니다.",
        "html": """
        <div style="width:600px">
          <label for="d1">담당자</label>
          <input id="d1" type="text" list="dl1" style="width:280px;height:36px">
          <datalist id="dl1"><option value="김"></option><option value="이"></option></datalist>
        </div>""",
    },
    {
        "name": "plain_dropdown_for_entity/검색 상자는 검색 그 자체다",
        "assertion": "plain_dropdown_for_entity",
        "expect": "pass",
        "why": ("「템플릿 검색」이라고 이름 붙은 입력을 «템플릿을 검색 없이 고르게 한다» 로 읽으면 "
                "정확히 거꾸로다 — `/templates` 의 검색창이 실제로 그렇게 잡혔다."),
        "html": """
        <div style="width:600px">
          <label for="s1">템플릿 검색</label>
          <input id="s1" type="search" style="width:280px;height:36px">
          <label for="s2">문서 찾기</label>
          <input id="s2" type="text" style="width:280px;height:36px">
          <label for="s3">프로젝트</label>
          <input id="s3" role="combobox" aria-autocomplete="list" style="width:200px;height:36px">
        </div>""",
    },
    {
        "name": "control_baseline_mismatch/노치 라벨이 붙은 입력은 여전히 컨트롤이다",
        "assertion": "control_baseline_mismatch",
        "expect": "fail",
        "why": ("MUI 의 노치 라벨은 `position:absolute` 인 `<fieldset><legend>` 다. 요소 전체의 줄상자를 "
                "세면 **모든 MUI 입력이 «두 줄»** 이 되어 검사가 통째로 눈이 먼다 — 실측으로 `/team-docs` "
                "7/7 · `/my-tickets` 7/7 이 탈락했다. 흐름 밖 글은 세지 않으므로 아래 두 입력은 "
                "여전히 비교 대상이고, 높이 8px 차이가 잡혀야 한다."),
        "html": """
        <div style="display:flex;gap:12px;align-items:center;width:900px">
          <div style="position:relative;height:36px;width:240px;border:1px solid #ccc">
            <fieldset style="position:absolute;inset:-5px 0 0 0;border:1px solid #ccc;margin:0">
              <legend style="font-size:10px">부서</legend></fieldset>
            <input style="border:0;height:34px;width:220px" value="ClovirONE팀">
          </div>
          <div style="position:relative;height:44px;width:240px;border:1px solid #ccc">
            <fieldset style="position:absolute;inset:-5px 0 0 0;border:1px solid #ccc;margin:0">
              <legend style="font-size:10px">프로젝트</legend></fieldset>
            <input style="border:0;height:42px;width:220px" value="P. 클로비">
          </div>
        </div>""",
    },
    {
        "name": "control_baseline_mismatch/2단 격자의 다른 칸끼리는 짝지어지지 않는다",
        "assertion": "control_baseline_mismatch",
        "expect": "pass",
        "why": ("격자 트랙은 **열**이지 줄이 아니다. 34px 버튼 둘이 14px 어긋나면 세로로 59% 겹쳐 "
                "«같은 줄» 로 묶이는데, 서로 다른 칸에 있는 둘은 같은 기준선에 설 이유가 없다 — "
                "`/profile` dark 1366 에서 「다른 기기 모두 로그아웃」과 「비밀번호 변경」이 그랬다."),
        "html": """
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;width:900px;align-items:start">
          <div><div style="height:100px"></div><button style="height:34px">비밀번호 변경</button></div>
          <div><div style="height:114px"></div><button style="height:34px">다른 기기 모두 로그아웃</button></div>
        </div>
        <div style="display:flex;gap:12px;align-items:center;width:900px;margin-top:24px">
          <button style="height:36px;width:90px">검색</button>
          <button style="height:36px;width:90px">정렬</button>
        </div>""",
    },
    {
        "name": "oversized_empty_surface/넓고 낮은 띠도 잡힌다",
        "assertion": "oversized_empty_surface",
        "expect": "fail",
        "why": "지시 80 이 지목한 형태 — 페이지 폭 판인데 내용은 왼쪽 일부만 쓴다(옛 높이 문턱이 못 보던 자리).",
        "html": """
        <div style="width:1400px;height:110px;background:#fff;border:1px solid #ddd">
          <div style="width:380px;height:36px;background:#eee">컨트롤 셋</div>
        </div>""",
    },
    {
        "name": "oversized_empty_surface/내용이 폭을 채우는 띠는 안 잡힌다",
        "assertion": "oversized_empty_surface",
        "expect": "pass",
        "why": ("같은 크기의 판이라도 **잉크가** 폭을 쓰면 결함이 아니다. 잉크는 «칠해진 상자»가 "
                "아니라 «보이는 잎 노드»로 잰다(F-W4-12 가 남긴 규율) — 그래서 반례도 큰 빈 상자가 "
                "아니라 실제로 폭에 걸친 컨트롤이어야 한다."),
        "html": """
        <div style="width:1400px;height:110px;background:#fff;border:1px solid #ddd;
                    display:flex;align-items:center;gap:16px;padding:0 16px;box-sizing:border-box">
          <input style="flex:1 1 auto;height:36px" value="검색어">
          <button style="height:36px">정렬</button>
          <button style="height:36px">카드</button>
          <button style="height:36px">표</button>
        </div>""",
    },
]

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
  body { margin:0; font: 14px system-ui; background:#EEF0F7; }
  #main-content { padding: 24px; }
</style></head><body><main id="main-content">%s</main></body></html>"""


def run(headed: bool = False) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        print("[FATAL] playwright 를 불러올 수 없다: %s" % exc)
        raise SystemExit(2) from exc

    out: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        for case in CASES:
            page.set_content(PAGE % case["html"])
            probe = assertions.evaluate(page, expected_theme="light", viewport_width=1600)
            verdicts = assertions.classify(
                probe, expected_theme="light", viewport_width=1600,
                final_url="https://example.invalid/#/selftest",
                console_errors=[], page_errors=[],
            )
            got = (verdicts.get(case["assertion"]) or {}).get("status")
            out.append({
                "name": case["name"],
                "assertion": case["assertion"],
                "expect": case["expect"],
                "got": got,
                "ok": got == case["expect"],
                "why": case["why"],
            })
        browser.close()
    return out


def main() -> int:
    # 콘솔이 cp949 면 인용부호에서 죽는다 — 결과를 못 읽는 실패는 실패보다 나쁘다.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="W5 프로브 반례 검증")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    rows = run(headed=args.headed)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for r in rows:
            mark = "OK " if r["ok"] else "NG "
            print("[%s] %-52s 기대 %-4s 실제 %-4s" % (mark, r["name"], r["expect"], r["got"]))
            if not r["ok"]:
                print("      %s" % r["why"])
    bad = [r for r in rows if not r["ok"]]
    if bad:
        print("PROBE_SELFTEST_FAILED (%d/%d)" % (len(bad), len(rows)))
        return 1
    print("PROBE_SELFTEST_OK (%d 사례 — 결함은 잡히고 정상은 안 잡힌다)" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
