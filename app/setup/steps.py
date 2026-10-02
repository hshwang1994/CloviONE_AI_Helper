"""셋업 안내 항목과 **그 순서** (9-3, P3).

## 왜 순서를 자료로 두는가

설치 직후 관리자가 마주하는 질문은 일곱 개인데 서로 독립이 아니다. Notion 토큰이 없으면
사용자 매핑은 시작조차 못 하고, 매핑이 없으면 AI 도우미는 "내 티켓" 이 무엇인지 모른다.
그런데 화면이 이 일곱 개를 아무 순서로나 물으면, 사용자는 3번을 붙들고 30분을 쓴 뒤에야
1번이 안 돼 있어서 3번이 안 되는 것임을 알게 된다.

그래서 **안내 순서를 코드가 아니라 자료로** 둔다. 화면도, 사용자 배너도, 테스트도 이
목록 하나를 읽는다. 순서를 바꾸려면 여기만 고치면 되고, 고치면 전부 따라온다.

## `requires` 에 적는 것 / 안 적는 것

`requires` 는 **앞이 안 되면 뒤가 실제로 동작하지 않는** 관계만 적는다. 이유를
`requires_why` 에 쓰지 못하겠으면 그건 의존이 아니라 취향이고, 취향을 의존이라고 부르면
화면은 사실이 아닌 이유로 사람을 막는다(불변 6: 없는 것을 있는 척 그리지 않는다).

순서(`SETUP_STEPS` 의 나열)는 의존을 **위상정렬한 것**이되, 의존이 없는 항목들 사이에서는
안내하기 좋은 순서로 놓는다. 그래서 순서가 의존보다 촘촘할 수는 있어도 어긋나지는 않는다
(tests/integration/test_setup_checklist.py 가 그 성질을 못박는다).

## 필수와 선택 (계획 3.5, D-520)

예전에는 여섯 항목이 전부 끝나야 설치가 「완료」였다. 그래서 메일과 AI 를 쓰지 않는 설치는 영원히 미완료였고 사용자
배너가 계속 떴다. 제품이 실제로 요구하는 것은 셋이다:

  관리자 계정   이 사람이 없으면 아무도 설정을 못 한다
  조직과 부서   담당자 배정, 부서 범위 관리자, 회차(팀 소유)가 부서를 요구한다
  TLS 인증서    설치가 자체 서명 인증서를 만들어 처음부터 끝나 있다. 만료가 가까우면 다시 할 일이 된다

메일, AI, 외부 연동은 **선택**이다. 없으면 그 기능만 꺼지고 나머지는 그대로다. 메일과 AI 는 관리자가 「사용하지
않음」으로 표시할 수 있다(`setup_optional_choices`) - 그러면 설정이 비어 있어도 할 일로 세지 않는다. 설정을 채우면
선택과 무관하게 실제 상태를 보인다. 외부 연동은 하나도 없는 것이 이미 정상이다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SetupStep:
    """안내 항목 하나. 여기 있는 문구는 그대로 화면에 나간다."""

    key: str
    label: str
    # 이 항목이 안 되면 무슨 일이 벌어지는가. 키 이름만 보여 주면 운영자는 그게 문제인지
    # 원래 그런 건지 모른다(app/core/tenant_config.py 의 when_unset 과 같은 발상).
    why: str
    requires: tuple[str, ...] = ()
    requires_why: str = ""
    # 이 항목이 안 되면 **일반 사용자 화면이 빈다**. 그런 항목만 사용자 배너에 이유로
    # 쓴다. 관리자 계정과 TLS 는 사용자 화면이 비는 이유가 아니고, 사용자가 할 수 있는
    # 일도 아니므로 말하지 않는다(app/observability/router.py 와 같은 선).
    user_visible: bool = False
    # 설치가 「완료」이려면 끝나야 하는 항목인가(D-520). 선택 항목은 남아 있어도 완료를 막지 않는다.
    required: bool = True
    # 「사용하지 않음」을 고를 수 있는 선택 항목의 이름(`setup_optional_choices` 의 키). 없으면 고를 수 없다.
    optional_choice: str | None = None


SETUP_STEPS: tuple[SetupStep, ...] = (
    SetupStep(
        key="admin_account",
        label="관리자 계정",
        why=(
            "시스템 관리자 계정이 없으면 아래 항목을 채울 사람이 없습니다. "
            "초기 임시 비밀번호를 그대로 두면 그 계정은 아직 아무도 쓰지 않은 계정입니다."
        ),
    ),
    SetupStep(
        key="mail",
        label="메일 발송",
        # 화면에 그대로 나가는 문장이다. 내부 식별자나 배너 같은 구현 이야기를 넣지 않는다(최종 캡처에서 「(ADM-02R)」과
        # 「사용자 배너에는 쓰지 않지만」이 화면에 보였다).
        why=(
            "메일을 설정하지 않으면 사용자가 스스로 비밀번호를 재설정할 수 없어 관리자에게 요청해야 합니다. "
            "초대, 승인 요청, 백업 실패, 알림 메일도 나가지 않습니다. 나머지 기능은 그대로 동작합니다."
        ),
        required=False,
        optional_choice="mail",
        # 관리자 계정 화면과 같은 선: 화면이 비는 이유가 아니라 사용자가 할 수 있는 일도
        # 아니므로 user_visible=False (steps.py 클래스 docstring 참조).
    ),
    SetupStep(
        key="organization",
        label="조직과 부서",
        why=(
            "부서가 없으면 사용자를 어디에도 넣을 수 없고, 부서 범위 관리자와 조직도, "
            "담당자 배정이 전부 빈 채로 남습니다."
        ),
        requires=("admin_account",),
        requires_why="부서를 만들 수 있는 사람이 먼저 있어야 합니다.",
        user_visible=True,
    ),
    # 「Notion 토큰과 데이터베이스」 단계가 여기 있었다. 티켓·문서·리포트가 그 토큰으로
    # 노션을 읽었으니 비어 있으면 화면이 비었고, 그래서 설치 단계였다. 지금은 셋 다 이
    # 서버의 데이터베이스에서 나오므로 설치할 때 넣을 토큰이 없다.
    #
    # 🔴 그 뒤에 「사용자 매핑」 단계가 하나 더 남아 있었다. 그 단계가 재던 것은
    # `user_notion_mappings` 의 verified 행 수이고, 안내는 없어진 화면으로 가라고 말했다.
    # **새 설치에서는 그 행이 영원히 0 이다** — 만들 방법이 제품에 없다(S14). 그래서 이
    # 목록은 끝까지 갈 수 없었고, 뒤에 `requires` 로 매달린 「AI 러너」까지 함께 잠겼다.
    # 담당자 축은 이제 옛 짝이 없으면 자기 user id 로 선다(D-285)이라 연결이라는 설치
    # 단계 자체가 없다.
    # 🔴 이 단계의 이름이 「AI 러너」였다. 러너는 **S11 이 걷어낸 런타임**이고, 이 단계를
    # 판정하는 `probe_llm` 은 이미 오래전부터 러너 레지스트리가 아니라 AI Gateway 를 읽는다
    # (probes.py 의 그 함수 docstring 이 그 사실을 적어 뒀다). 즉 화면에 보이는 이름만
    # 없어진 부품을 가리키고 있었다 — 설치하는 사람은 그 이름을 찾아 헤맨다.
    SetupStep(
        key="llm",
        label="AI",
        why=(
            "AI 를 켜지 않으면 채팅 답변, 문서 요약, 오늘 브리핑의 문장 요약이 모두 비어 있습니다."
        ),
        requires=("organization",),
        requires_why=(
            "AI 가 답하는 사실은 이 포털의 사용자와 그 사람의 티켓에서 나옵니다. "
            "조직 단위가 없으면 AI 가 살아 있어도 답이 비어 있습니다."
        ),
        user_visible=True,
        required=False,
        optional_choice="llm",
    ),
    # 🔴 이 단계의 이유가 「자동화 워크플로가 호출할 곳이 없어 예약 실행과 웹훅이 …」였다.
    # 워크플로와 웹훅도 S11 이 걷었다. 그리고 `requires=("llm",)` 는 「연동 워크플로는 결국
    # 러너를 불러 일을 시킨다」는 옛 구조의 의존이었다 — 지금 연동은 AI 와 아무 관계가 없다.
    # 없는 의존을 남겨 두면 AI 를 안 켠 설치에서 연동이 영영 「막힘」으로 보인다.
    #
    # 연동은 **선택**이다(probe_integrations 가 하나도 없는 상태를 정상으로 판정한다).
    # 그래서 이 단계가 말하는 것은 「등록해야 한다」가 아니라 「등록한 것이 살아 있는가」다.
    SetupStep(
        key="integrations",
        label="외부 연동",
        why=(
            "등록한 연동이 응답하지 않으면 그 연동을 쓰는 기능만 조용히 실패합니다. "
            "연동을 하나도 안 쓰는 설치라면 이 단계는 그대로 넘어갑니다."
        ),
        user_visible=True,
        required=False,
    ),
    SetupStep(
        key="tls",
        label="TLS 인증서",
        why=(
            "사내망이라도 로그인 비밀번호와 세션 쿠키가 평문으로 오갑니다. "
            "인증서가 만료되면 브라우저가 경고를 띄우고 사용자는 접속을 포기합니다."
        ),
    ),
)

SETUP_ORDER: tuple[str, ...] = tuple(step.key for step in SETUP_STEPS)
STEP_BY_KEY: dict[str, SetupStep] = {step.key: step for step in SETUP_STEPS}

# 셋업이 안 끝났을 때 일반 사용자에게 이유로 말할 수 있는 항목.
USER_VISIBLE_KEYS: tuple[str, ...] = tuple(
    step.key for step in SETUP_STEPS if step.user_visible
)
# 설치가 「완료」이려면 끝나야 하는 항목(D-520).
REQUIRED_KEYS: tuple[str, ...] = tuple(step.key for step in SETUP_STEPS if step.required)
# 「사용하지 않음」을 고를 수 있는 선택 항목의 이름.
OPTIONAL_CHOICES: tuple[str, ...] = tuple(step.optional_choice for step in SETUP_STEPS if step.optional_choice)
# 초기 설정에서 고를 수 있는 값의 전부(`setup_optional_choices`, D-534). 메일 · AI 는 쓸지 말지, TLS 는 누가 맡는지다.
CHOICE_VALUES: dict[str, tuple[str, ...]] = {
    **{key: ("use", "unused") for key in OPTIONAL_CHOICES},
    "tls": ("app", "proxy"),
}
CHOICE_DEFAULTS: dict[str, str] = {**{key: "use" for key in OPTIONAL_CHOICES}, "tls": "app"}

__all__ = [
    "SetupStep",
    "SETUP_STEPS",
    "SETUP_ORDER",
    "STEP_BY_KEY",
    "USER_VISIBLE_KEYS",
    "REQUIRED_KEYS",
    "OPTIONAL_CHOICES",
    "CHOICE_VALUES",
    "CHOICE_DEFAULTS",
]
