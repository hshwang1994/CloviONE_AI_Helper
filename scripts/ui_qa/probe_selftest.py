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
        "name": "control_baseline_mismatch/세그먼티드 트랙의 안쪽 칸은 옆 단추와 짝지어지지 않는다",
        "assertion": "control_baseline_mismatch",
        "expect": "pass",
        "why": ("세그먼티드는 트랙(34) 안에 칸(28)이 선다(계획 P-2). 칸을 옆 34 단추와 짝지으면 "
                "6px 차이로 잡혔다 — 작업 보드 칸반/백로그 전환 옆 「보류 펴기」에서 실제로 그랬다."),
        "html": """
        <div style="display:flex;gap:12px;align-items:center;width:800px">
          <div class="k-segmented" role="tablist" style="display:flex;height:34px;padding:3px;box-sizing:border-box">
            <button role="tab" style="height:28px;width:80px">칸반</button>
            <button role="tab" style="height:28px;width:80px">백로그</button>
          </div>
          <button style="height:34px;width:120px">보류 펴기</button>
        </div>""",
    },
    {
        "name": "control_baseline_mismatch/세그먼티드 트랙 자체의 높이가 다르면 잡힌다",
        "assertion": "control_baseline_mismatch",
        "expect": "fail",
        "why": "트랙을 컨트롤 하나로 재도 트랙이 옆 단추보다 12px 크면 그대로 결함이다(반례).",
        "html": """
        <div style="display:flex;gap:12px;align-items:center;width:800px">
          <div class="k-segmented" role="tablist" style="display:flex;height:46px;padding:3px;box-sizing:border-box">
            <button role="tab" style="height:40px;width:80px">칸반</button>
            <button role="tab" style="height:40px;width:80px">백로그</button>
          </div>
          <button style="height:34px;width:120px">보류 펴기</button>
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
        "name": "optical_alignment/한 줄 입력의 여백이 아래에만 있으면 잡힌다",
        "assertion": "optical_alignment",
        "expect": "fail",
        "why": ("native textarea 는 첫 줄을 내용 상자 위에 붙인다. 한 줄인데 상자가 글보다 크면 "
                "남는 칸이 전부 아래로 가서 글이 위에 붙어 보인다 — 채팅 입력은 그 한 예일 뿐이다."),
        "html": """
        <textarea rows="1" placeholder="메시지를 입력하세요"
          style="width:320px;height:48px;padding:6px 12px;line-height:20px;font-size:14px;
                 box-sizing:border-box;border-radius:24px"></textarea>""",
    },
    {
        "name": "optical_alignment/버튼 안 아이콘이 치우치면 잡힌다",
        "assertion": "optical_alignment",
        "expect": "fail",
        "why": "상자 중심이 아니라 자식 잉크 중심을 본다. 아이콘이 위에 붙으면 글이 위에 붙은 것과 같은 부류다.",
        "html": """
        <button style="height:44px;width:44px;padding:0;display:flex;align-items:flex-start;
                       justify-content:center;box-sizing:border-box">
          <svg width="16" height="16" style="display:block;margin-top:2px">
            <circle cx="8" cy="8" r="6" fill="#333"/></svg>
        </button>""",
    },
    {
        "name": "optical_alignment/아무 축도 안 맞는 이웃은 잡힌다",
        "assertion": "optical_alignment",
        "expect": "fail",
        "why": ("키가 다른 입력과 버튼이 위도 아래도 가운데도 안 맞으면 «기준이 없다». "
                "아래를 맞춘 입력줄(flex-end)은 아래 축을 공유하므로 이쪽이 아니다."),
        "html": """
        <div style="display:flex;align-items:flex-start;gap:8px;width:400px">
          <input style="flex:1;height:48px;margin-top:12px;box-sizing:border-box">
          <button style="height:32px;width:72px;margin-top:0;box-sizing:border-box">확인</button>
        </div>""",
    },
    {
        "name": "optical_alignment/글 높이에 맞춘 한 줄 입력은 안 잡힌다",
        "assertion": "optical_alignment",
        "expect": "pass",
        "why": "여백이 거의 없으면 글이 위에 붙었다고 말할 칸이 없다.",
        "html": """
        <textarea rows="1" placeholder="검색"
          style="width:280px;height:32px;padding:4px 8px;line-height:22px;font-size:14px;
                 box-sizing:border-box"></textarea>""",
    },
    {
        "name": "optical_alignment/아래를 맞춘 여러 줄 입력은 안 잡힌다",
        "assertion": "optical_alignment",
        "expect": "pass",
        "why": ("커진 입력 + 전송은 아래를 맞추는 것이 정상이다. 한 줄짜리 휴식 상태의 여백과 "
                "구별해야 한다 — 이 면제가 없으면 채팅 입력줄이 글을 쓰는 순간마다 결함이 된다."),
        "html": """
        <div style="display:flex;gap:8px;align-items:flex-end;width:400px">
          <textarea rows="4" style="flex:1;height:80px;padding:8px;line-height:20px;
            font-size:14px;box-sizing:border-box">가&#10;나&#10;다</textarea>
          <button style="height:34px;width:64px;display:flex;align-items:center;
                         justify-content:center">전송</button>
        </div>""",
    },
    {
        "name": "optical_alignment/가운데를 맞춘 도구 줄은 안 잡힌다",
        "assertion": "optical_alignment",
        "expect": "pass",
        "why": "같은 줄이 가운데 축을 공유하면 기준이 있다.",
        "html": """
        <div style="display:flex;gap:8px;align-items:center;width:600px">
          <input style="flex:1;height:36px;box-sizing:border-box">
          <button style="height:36px;width:80px;display:flex;align-items:center;
                         justify-content:center">정렬</button>
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


# ─────────────────────────────────────────────────────────────────────────────
# 판정 «규칙» 반례 — DOM 이 아니라 로직이다 (S1 · 12_PROBE #4 · #8)
#
# 위 `CASES` 는 합성 DOM 을 태워 Assertion 을 검증한다. 하지만 W5 가 실제로 아팠던 자리
# 둘은 DOM 이 아니었다:
#
#   * `--fail-on` 으로 걸어 둔 검사가 **한 번도 돌지 않았는데** 종료 코드 0 이 나갔다.
#   * 프로브 19개가 TLS 검증을 각자 꺼 두어 호스트 불일치가 **구조적으로** 안 보였다.
#
# 둘 다 브라우저 없이 증명된다. 브라우저가 없는 기계에서도 이 절은 돌아야 하므로
# `--logic-only` 를 둔다.
# ─────────────────────────────────────────────────────────────────────────────

def _logic_cases() -> list[dict]:
    import os  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from . import run as run_mod  # noqa: PLC0415
    from . import tls  # noqa: PLC0415

    ug = run_mod.unverified_gates
    modal = assertions.MODAL_CLASSES
    all_classes = list(assertions.CLASSES)
    rows: list[dict] = []

    def case(name: str, got, want, why: str) -> None:
        rows.append({"name": name, "assertion": "(로직)",
                     "expect": repr(want), "got": repr(got),
                     "ok": got == want, "why": why})

    # ── #4 미실행 게이트 ──────────────────────────────────────────────────
    case("unverified_gates/기록조차 없으면 미실행이다",
         ug({}, ["tiny_text"]), ["tiny_text"],
         "`--modals` 없이 건 모달 검사가 이 모양이었다 — classify 가 키를 아예 안 넣는다")
    case("unverified_gates/전부 skip 이어도 미실행이다",
         ug({"tiny_text": {"pass": 0, "fail": 0, "skip": 60}}, ["tiny_text"]), ["tiny_text"],
         "QA-10: 폭 2200 미만에서 전부 skip 인데 요약은 «문제 없음» 으로 읽혔다")
    case("unverified_gates/한 번이라도 판정했으면 미실행이 아니다",
         ug({"tiny_text": {"pass": 6, "fail": 0}}, ["tiny_text"]), [],
         "위양성이면 이 규칙은 첫날 꺼진다")
    case("unverified_gates/`--modals` 없는 실행의 모달 7종은 면제다",
         ug({}, list(modal), exempt=modal), [],
         "실행 설정이 애초에 만들 수 없는 판정 — 이것까지 실패로 만들면 규칙이 죽는다")
    # 🔴 회귀 잠금. 예전에는 `--fail-on all` 이면 이 판정을 통째로 껐고, 그 한 줄이
    #    뷰포트 게이트 검사까지 함께 면제했다.
    case("unverified_gates/`all` 로 걸어도 뷰포트 게이트 미실행은 남는다",
         "tiny_text" in ug({}, all_classes, exempt=modal), True,
         "면제는 이름을 적은 것만이다 — 1366/1920 만 찍은 실행이 `--fail-on all` 로 초록을 "
         "받던 자리")
    case("unverified_gates/`all` 로 걸어도 모달은 면제로 빠진다",
         any(c in ug({}, all_classes, exempt=modal) for c in modal), False,
         "좁힌 면제가 실제로 좁게 동작하는지 — 양방향")

    # ── #8 TLS 정책 ─────────────────────────────────────────────────────
    saved = os.environ.pop(tls.ENV_VAR, None)
    try:
        case("tls/기본값은 정책 파일 한 곳에서 온다",
             tls.insecure(), not tls.DEFAULT_VERIFY,
             "S3 이 `DEFAULT_VERIFY` 하나를 바꾸면 19개가 함께 켜져야 한다")
        case("tls/`--verify-tls` 는 검증을 켠다",
             tls.insecure(cli_verify=True), False,
             "인증서를 재발급한 뒤 S3 이 쓰는 스위치")
        os.environ[tls.ENV_VAR] = "1"
        case("tls/환경변수로도 켤 수 있다", tls.insecure(), False,
             "CI·스크립트에서 플래그 없이 켜는 경로")
        case("tls/명시가 둘이면 검증이 이긴다", tls.insecure(cli_insecure=True), True,
             "`--insecure` 는 명시적 요청이다 — 환경변수보다 가깝다")
        os.environ[tls.ENV_VAR] = "0"
        case("tls/환경변수로 끌 수도 있다", tls.insecure(), True,
             "자체서명 설치처를 겨눌 때")
    finally:
        os.environ.pop(tls.ENV_VAR, None)
        if saved is not None:
            os.environ[tls.ENV_VAR] = saved

    # ── #8 TLS 신뢰 기준점 (S3) ──────────────────────────────────────────
    # 자체서명 설치처에서는 「검증을 켰다」와 「검증할 근거가 있다」가 다른 사실이다.
    # 기준점을 못 찾은 실행이 조용히 시스템 저장소로 내려가면, 무엇을 믿고 통과했는지
    # 실행 로그만 보고는 알 수 없다.
    saved_ca = os.environ.pop(tls.CA_ENV_VAR, None)
    try:
        case("tls/기준점을 안 주면 빈 값이다", tls.ca_file(), "",
             "시스템 저장소만 쓰는 정상 경로")
        os.environ[tls.CA_ENV_VAR] = str(Path(__file__).resolve())
        case("tls/실재하는 파일이면 그 경로를 준다",
             tls.ca_file(), str(Path(__file__).resolve()),
             "설치 스크립트가 남기는 인증서 사본을 그대로 받는 자리")
        case("tls/기준점을 주면 실행 로그가 그것을 말한다",
             tls.CA_ENV_VAR in tls.describe(), False,
             "기준점이 있는 실행은 «기준점을 달라» 고 말하면 안 된다")
        os.environ[tls.CA_ENV_VAR] = str(Path(__file__).resolve().parent / "없는파일.crt")
        case("tls/오타 난 경로는 통과시키지 않는다", tls.ca_file(), "",
             "없는 경로를 조용히 무시하면 «검증했다» 가 거짓이 된다")
        case("tls/기준점이 없으면 실행 로그가 달라고 말한다",
             tls.CA_ENV_VAR in tls.describe(), True,
             "위 사례의 반대 방향 — 두 문장이 실제로 갈리는지 본다")
    finally:
        os.environ.pop(tls.CA_ENV_VAR, None)
        if saved_ca is not None:
            os.environ[tls.CA_ENV_VAR] = saved_ca

    # ── #8 Node 쪽 기준점 (S3 · P-10a) ───────────────────────────────────
    # Playwright 의 `context.request` 는 Node 위에서 돌고 운영체제 신뢰 저장소를 안 본다.
    # 안 심으면 `page.goto` 만 200 이고 `_fetch_me` 는 조용히 None 이라, 하네스가 TLS 를
    # 한 마디도 안 하고 「인증을 인정하지 않습니다」로 죽는다 — 실제로 그렇게 한 번 죽었다.
    saved_ca = os.environ.pop(tls.CA_ENV_VAR, None)
    saved_node = os.environ.pop(tls.NODE_CA_ENV_VAR, None)
    try:
        here = str(Path(__file__).resolve())
        os.environ[tls.CA_ENV_VAR] = here
        tls.apply_default_https_context()
        case("tls/검증을 켜면 Node 기준점도 함께 심는다",
             os.environ.get(tls.NODE_CA_ENV_VAR), here,
             "파이썬만 심고 끝내면 context.request 가 조용히 실패한다")

        os.environ[tls.NODE_CA_ENV_VAR] = "이미-사람이-정한-값"
        tls.apply_default_https_context()
        case("tls/사람이 정해 둔 Node 기준점을 덮지 않는다",
             os.environ.get(tls.NODE_CA_ENV_VAR), "이미-사람이-정한-값",
             "명시가 정책보다 가깝다 — 사설 CA 번들을 쓰는 설치처가 있다")

        os.environ.pop(tls.NODE_CA_ENV_VAR, None)
        tls.apply_default_https_context(cli_insecure=True)
        case("tls/검증을 끄면 Node 기준점을 심지 않는다",
             tls.NODE_CA_ENV_VAR in os.environ, False,
             "끈 실행이 조용히 무언가를 신뢰하게 만들지 않는다 — 반대 방향")
    finally:
        for key, saved in ((tls.CA_ENV_VAR, saved_ca), (tls.NODE_CA_ENV_VAR, saved_node)):
            os.environ.pop(key, None)
            if saved is not None:
                os.environ[key] = saved
        # 이 블록이 전역 HTTPS 컨텍스트를 만졌다 — 원래대로 돌려놓는다.
        tls.apply_default_https_context()

    # ── W6 이 바꾼 brand 판정 (D-288 · D-289) ────────────────────────────
    # 「판정 규칙을 고치면 반례로 검증한다」. brand 판정은 측정과 분리돼 있어서
    # (`brand_verdict` 는 dict 만 받는다) 브라우저 없이 양방향을 전부 보일 수 있다.
    from . import brand  # noqa: PLC0415

    def probe(**roles) -> dict:
        """light 테마 · 캔버스 `#EEF0F7` 위에서 잰 것으로 꾸민 측정값."""
        out = {"theme": "light", "canvas": "rgb(238, 240, 247)", "canvasFrom": "body", "roles": {}}
        for name in brand.ROLES:
            spec = roles.get(name)
            if spec is None:
                out["roles"][name] = {"found": False, "note": "이 사례에 없음"}
                continue
            what, value = spec[0], spec[1]
            entry = {
                "found": True, "kind": "bg" if name in brand.BG_ROLES else "ink",
                "selector": "(사례)", "element": "(사례)",
                "candidates": [{"what": what, "value": value}],
                "backdrop": spec[2] if len(spec) > 2 else "rgb(255, 255, 255)",
            }
            if len(spec) > 3:
                entry["tone"] = spec[3]
            out["roles"][name] = entry
        return out

    BRAND_INK = ("color", "rgb(76, 88, 200)")          # brand.core light — 색상각 232도
    GREY_INK = ("color", "rgb(22, 26, 44)")            # text.primary — 눈에는 검정
    RAIL = ("border-bottom-color", "rgb(76, 88, 200)")  # 판독 줄 활성 칸의 Brand 레일
    GREY_RAIL = ("border-bottom-color", "rgb(128, 128, 128)")   # 순수 회색 레일
    WARN_INK = ("color", "rgb(106, 69, 22)", "rgb(255,255,255)", "warn")

    def coverage(**roles) -> str:
        return brand.brand_coverage_verdict(brand.brand_verdict(probe(**roles)))["status"]

    # D-289 ─ 선택은 레일로도 말할 수 있다. 단 **무채색 레일은 여전히 실패**다.
    case("brand/선택을 Brand 레일로 말해도 «있는 자리» 다",
         coverage(nav_active=BRAND_INK, primary_action=BRAND_INK, selected_state=RAIL), "pass",
         "이 제품은 선택을 면이 아니라 레일로 말한다(D-184·W4) — 면만 세면 «선택 색이 없다» 는 "
         "정반대 결론이 나온다")
    case("brand/무채색 레일은 그대로 실패다",
         coverage(nav_active=BRAND_INK, primary_action=BRAND_INK, selected_state=GREY_RAIL), "fail",
         "🔴 반대 방향 — 규칙을 느슨하게 한 것이 아님을 이 사례가 증명한다. 회색 선택은 결함이다")
    case("brand/선택이 아무 것도 안 칠하면 실패다",
         coverage(nav_active=BRAND_INK, primary_action=BRAND_INK,
                  selected_state=("background-color", "rgba(0, 0, 0, 0)")), "fail",
         "`/my-approvals` 의 선택된 탭이 정확히 이 상태였다. 「요소는 찾았는데 아무 색도 "
         "안 나른다」 는 모르는 것이 아니라 알아낸 사실이라 `unknown` 으로 빠지면 안 된다")

    # D-288 ─ 심각도가 칠한 판독값은 «있는 자리» 가 아니다. 선언이 없으면 그냥 회색 결함이다.
    case("brand/심각도로 칠한 판독값은 회색으로 세지 않는다",
         coverage(nav_active=BRAND_INK, primary_action=BRAND_INK, highlight=WARN_INK), "pass",
         "「지연 3건」을 인디고로 칠할 수는 없다 — 색이 뜻을 나르는 자리다")
    case("brand/그 판독값을 통과로 세지도 않는다",
         brand.brand_verdict(probe(nav_active=BRAND_INK, primary_action=BRAND_INK,
                                   highlight=WARN_INK))["present_brand"], 2,
         "🔴 정족수를 공짜로 채우면 `brand_presence` 가 무력해진다 — unknown 은 통과가 아니다")
    case("brand/선언 없는 회색 판독값은 그대로 실패다",
         coverage(nav_active=BRAND_INK, primary_action=BRAND_INK, highlight=GREY_INK), "fail",
         "🔴 반대 방향 — `/my-stats`·`/sprint` 의 판독값이 본문 잉크였던 그 상태다")
    case("brand/Brand 잉크 판독값은 통과다",
         coverage(nav_active=BRAND_INK, primary_action=BRAND_INK, highlight=BRAND_INK), "pass",
         "고친 뒤의 모습 — 이 사례가 없으면 «전부 unknown» 으로도 초록이 된다")

    # ── S22 · P-40 ─ 유채색 문턱은 절벽이 아니라 경사다 ──────────────────
    # 예전 규칙은 「L>0.90 이면 폭 0.15, 아니면 0.06」이라 문턱 **바로 아래**가 공짜로
    # 통과했다. 아래 여섯이 그 경사를 양방향으로 못 박는다 — 중립 램프 둘은 떨어지고,
    # 진짜 Brand 색 둘은 통과하고, 잉크와 종이는 예전 판정을 그대로 유지한다.
    def chromatic(hexcode: str) -> bool:
        rgb = (int(hexcode[1:3], 16), int(hexcode[3:5], 16), int(hexcode[5:7], 16))
        _hue, sat, _light = brand._hsl(rgb)
        return brand._is_chromatic(sat, brand._spread(rgb), rgb)

    case("brand/divider 는 Brand 로 세지 않는다", chromatic("#DCDFEC"), False,
         "🔴 P-40 이 잡은 그 자리 — L 0.894 로 옛 절벽(0.90) 바로 아래라 색상각·채도만 맞으면 "
         "어떤 role 이든 통과했다. 눈에는 아주 옅은 회선이다")
    case("brand/dividerStrong 도 Brand 로 세지 않는다", chromatic("#BCC2D9"), False,
         "평평한 구간을 두면 그 가장자리가 새 절벽이 되고 이 색이 정확히 그 자리에 앉는다 — "
         "경사에 평평한 구간을 두지 않는 이유")
    case("brand/rail 은 통과한다", chromatic("#A9BAFF"), True,
         "🔴 반대 방향 — 문턱을 올린 것이 진짜 Brand 색까지 떨어뜨리지 않았음을 보인다")
    case("brand/focusRing 도 통과한다", chromatic("#C3CEFF"), True,
         "밝은 쪽에서 가장 아슬아슬한 진짜 Brand 색이다(L 0.882 · 폭 0.235)")
    case("brand/본문 잉크는 여전히 무채색이다", chromatic("#161A2C"), False,
         "이 판정이 뒤집히면 `highlight` 가 본문 글자를 Brand 로 세고 지표가 부풀어 오른다")
    case("brand/brandTint 는 사람이 정한 대로 무채색이다", chromatic("#E9ECFA"), False,
         "옛 규칙에서도 무채색이었다(L 0.947). AI 면은 배경 role 이라 캔버스와의 ΔE 가 따로 "
         "판정하므로 이 값이 그 자리를 막지 않는다")
    case("brand/Shell 은 어두운 쪽에서 통과한다", chromatic("#1E2758"), True,
         "어두운 쪽 경사도 진짜 Brand 색을 떨어뜨리지 않는지 — 양방향")

    # ── S22 · P-43 ─ 판독 슬롯이 없는 줄은 «회색인 자리» 가 아니다 ────────
    # 제품(`kit.jsx::MetricStrip`)이 `data-readout-slot="none"` 으로 그 사실을 선언하고,
    # 프로브의 `notInside` 가 그 줄과 그 안의 칸을 함께 건너뛴다. 여기서는 그 결과 —
    # 「자리가 없다」가 `unknown` 으로 읽히고, 정말 회색인 판독값은 **여전히 실패** — 를
    # 양방향으로 못 박는다.
    case("brand/판독 슬롯이 없으면 회색 결함이 아니다",
         coverage(nav_active=BRAND_INK, primary_action=BRAND_INK, selected_state=RAIL), "pass",
         "🔴 P-43 — 할 일이 없는 날의 홈이 그 상태다. 값이 0 이면 `MetricStrip` 이 판독 슬롯을 "
         "안 주므로 그 화면에는 지배 판독값이 없다. 없는 것은 `unknown` 이다")
    case("brand/그렇다고 정족수를 공짜로 채우지도 않는다",
         brand.brand_verdict(probe(nav_active=BRAND_INK, primary_action=BRAND_INK,
                                   selected_state=RAIL))["present_brand"], 3,
         "unknown 은 통과가 아니다 — 슬롯이 없는 화면은 세 자리로만 정족수를 채운다")
    case("brand/슬롯이 있는데 회색이면 여전히 실패다",
         coverage(nav_active=BRAND_INK, primary_action=BRAND_INK, highlight=GREY_INK), "fail",
         "🔴 반대 방향 — 이 사례가 없으면 P-43 의 고침이 「판독값 검사를 통째로 껐다」와 "
         "구별되지 않는다")
    case("brand/`notInside` 는 판독 role 에만 걸린다",
         "data-readout-slot" in brand.BRAND_PROBE_JS
         and brand.BRAND_PROBE_JS.count("notInside: '[data-readout-slot=\"none\"]'"), 1,
         "다른 role 까지 함께 건너뛰면 그 화면의 다른 결함이 조용히 사라진다")

    # ── S22 ─ 화면이 「여기는 그 자리가 아니다」라고 말할 수 있다 ──────────
    case("brand/`data-brand-role=\"none\"` 은 모든 role 에서 한 번만 걸린다",
         brand.BRAND_PROBE_JS.count("el.closest('[data-brand-role=\"none\"]')"), 1,
         "🔴 role 마다 따로 적으면 어느 role 이 그 선언을 존중하는지 갈린다 — `pickOne` 한 "
         "자리에서만 본다")
    case("brand/그 선언은 마크업에 남아 셀 수 있다",
         '[data-brand-role="none"]' in brand.BRAND_PROBE_JS, True,
         "억제가 아니라 선언이다 — grep 으로 어느 화면이 무엇을 선언했는지 셀 수 있어야 한다")
    case("brand/선언 없는 회색 header 는 여전히 실패다",
         coverage(nav_active=BRAND_INK, primary_action=BRAND_INK,
                  header=("background-color", "rgb(236, 237, 238)")), "fail",
         "🔴 반대 방향 — 이 사례가 없으면 새 opt-out 이 「header 검사를 통째로 껐다」와 "
         "구별되지 않는다")

    # ── W7 이 고친 마스코트 판정 (지시 71) ────────────────────────────────
    # `mascot_verdict` 도 측정과 분리돼 있어(dict 만 받는다) 브라우저 없이 양방향을 보인다.
    # 여기서 못 박는 것은 셋이다: 잉크 비율이 부풀면 작은 마스코트가 통과한다 · 자리를
    # 선언하지 않으면 판정 자체가 뒤집힌다 · 못 잰 것은 통과가 아니다.
    from . import mascot  # noqa: PLC0415

    def seen(context: str, box: float, ink: float, *, container=None) -> str:
        """자산 하나가 한 자리에 그려진 것으로 꾸민 측정값 → 판정."""
        src = "http://x/static/brand/mascot/clovi-talking.png"
        probe_dict = {
            "items": [{
                "src": src, "context": context, "boxW": box, "boxH": box,
                "natW": 1024, "natH": 1024, "objectFit": "contain",
                "containerH": container,
            }],
            "ink": {src: {"natW": 1024, "natH": 1024, "inkFracH": ink, "inkFracW": ink}},
            "failed": {},
        }
        return mascot.mascot_verdict(probe_dict)["status"]

    # 🔴 이 저장소에서 실제로 있었던 상태다. 프로브가 알파 문턱 8 에 부유 픽셀 제거 없이
    #    재서 `clovi-talking` 의 잉크 비율을 1.000 으로 봤다 — 참값은 0.817 이다.
    case("mascot/부풀린 잉크 비율은 작은 마스코트를 통과시킨다",
         seen("inline", 28, 1.000), "pass",
         "🔴 고치기 전의 상태. 28px 상자가 «보이는 캐릭터 28px» 로 세어져 하한을 만족했다")
    case("mascot/참값으로 재면 같은 상자가 실패한다",
         seen("inline", 28, 0.817), "fail",
         "실제로는 22.9px 다. 같은 DOM 인데 잉크 정의 하나로 판정이 뒤집힌다 — 그래서 "
         "`gen_mascot_bounds.py` 와 프로브가 같은 정의를 쓰는지 회귀가 따로 본다")
    case("mascot/여백을 보정한 상자는 통과한다",
         seen("inline", 35, 0.817), "pass",
         "반대 방향 — 규칙을 엄하게만 한 것이 아니다. 28/0.817 ≈ 35 가 «보이는 28px» 이고 "
         "그 계산을 화면이 아니라 `Mascot.jsx` 가 한다")

    case("mascot/자리를 선언하면 그 밴드로 판정한다",
         seen("hero", 180, 0.817), "pass",
         "히어로는 하한 140 이다. 같은 상자를 `empty_state` 로 선언하면 아래처럼 갈린다")
    case("mascot/같은 상자도 자리가 다르면 판정이 다르다",
         seen("empty_state", 180, 0.817, container=200), "fail",
         "147px 캐릭터가 200px 짜리 빈 화면 안에 있으면 «빈 공간을 캐릭터로 때우는» 것이다 — "
         "하한(96)은 넘지만 위쪽 절반에서 걸린다")
    case("mascot/넉넉한 빈 화면에서는 같은 캐릭터가 통과한다",
         seen("empty_state", 180, 0.817, container=600), "pass",
         "반대 방향 — 컨테이너가 레이아웃이 정한 높이(`layout=\"page\"`)면 순환이 아니다")

    case("mascot/모르는 자리는 통과가 아니라 «판정 못 함» 이다",
         seen("떠있는버튼", 28, 0.817), "skip",
         "선언에 오타가 나면 조용히 초록이 되면 안 된다 — 잰 것이 하나도 없으므로 skip 이다")
    case("mascot/잉크를 못 잰 자산도 통과가 아니다",
         mascot.mascot_verdict({"items": [{"src": "a.png", "context": "topbar",
                                           "boxW": 28, "boxH": 28, "natW": 1024, "natH": 1024}],
                                "ink": {}, "failed": {"a.png": "자산을 불러오지 못함"}})["status"],
         "skip",
         "교차 출처 캔버스 오염 등으로 못 재면 «모른다» 다. 이것이 pass 로 새면 자산을 "
         "못 불러오는 실행이 전부 초록이 된다")

    # ── optical_alignment 판정 배선 ────────────────────────────────────────
    # DOM 반례는 위 CASES 가 브라우저로 본다. 여기는 classify 가 프로브 키를 실제로
    # 읽는지 — 키 이름을 바꾸면 검사가 영원히 skip 이 되는 함정.
    def oa_status(items, checked):
        return assertions.classify(
            {"opticalAlignment": items, "opticalAlignmentChecked": checked},
            expected_theme="light", viewport_width=1600,
            final_url="https://example.invalid/#/selftest",
            console_errors=[], page_errors=[],
        )["optical_alignment"]["status"]

    case("optical_alignment/CLASSES 에 등록돼 있다",
         "optical_alignment" in all_classes, True,
         "등록하지 않으면 요약표와 --fail-on 이 이 검사를 모른다")
    case("optical_alignment/SEVERITY 표에도 있다",
         "optical_alignment" in run_mod.SEVERITY_BY_CLASS, True,
         "표에 없으면 매 실행이 «표에 없는 검사» 경고를 찍고 기본 심각도로 흘려보낸다")
    case("optical_alignment/후보가 없으면 skip 이다",
         oa_status([], 0), "skip",
         "재지 않은 화면을 통과로 세면 커버리지가 거짓말을 한다")
    case("optical_alignment/재 보고 결함이 없으면 pass 다",
         oa_status([], 3), "pass",
         "후보를 봤는데 깨끗하면 통과다")
    case("optical_alignment/표본이 있으면 fail 이다",
         oa_status([{"selector": "textarea", "kind": "안쪽", "reason": "위에 붙음",
                     "delta": 8, "a": "메시지", "b": ""}], 1), "fail",
         "프로브가 담은 표본을 classify 가 버려서는 안 된다")
    return rows


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
    ap.add_argument("--logic-only", action="store_true",
                    help="브라우저 없이 판정 «규칙» 반례만 돌린다")
    args = ap.parse_args()

    rows = _logic_cases()
    if not args.logic_only:
        rows += run(headed=args.headed)
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
    print("PROBE_SELFTEST_OK (%d 사례%s — 결함은 잡히고 정상은 안 잡힌다)"
          % (len(rows), " · 로직만" if args.logic_only else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
