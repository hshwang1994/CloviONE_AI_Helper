"""Job lanes (D-118) — which job types run on the conversational worker.

낮은 위험(Phase 1, D-118): 이 모듈은 아직 아무 실행 경로도 안 바꾼다. 대화형 잡(채팅·LLM
연결 테스트)을 배치 잡(스케줄 실행·문서 생성·Notion 동기화·메일 등)과 분리된 워커
프로세스에서 돌리기 위한 배선의 첫 조각일 뿐이고, 실제로 분리된 워커를 띄우는 것은
`worker_conversational_lane_enabled` 설정(기본 꺼짐)이 켜진 뒤의 일이다.

**이 한 곳이 정본인 이유**: claim 필터·recover_stuck 필터·리스 파일 경로·liveness
컴포넌트 이름 네 곳이 전부 "대화형 job_type이 무엇인가"를 알아야 한다. 따로 두면 나중에
대화형 job_type을 하나 추가할 때 한 곳만 빠뜨리는 함정이 생긴다(이 저장소가 이미 여러 번
겪은 패턴 — docs/DECISIONS.md D-22).
"""

from __future__ import annotations

from app.llm_console.service import JOB_TYPE_TEST

LANE_BATCH = "batch"
LANE_CONVERSATIONAL = "conversational"
# 스케줄러 레인(S4 · D-225). 다른 둘과 성격이 다르다 — **잡을 하나도 클레임하지 않는다.**
# 하는 일은 만기 스케줄 평가와 좀비 실행 스윕뿐이고, 그래서 `CONVERSATIONAL_JOB_TYPES`
# 같은 job_type 목록이 없다. 배치 워커의 tick 이던 것을 프로세스로 꺼낸 것이다:
# 3600초짜리 schedule_run 하나가 도는 동안 워커 루프가 그 잡 안에 있어 스케줄 발화가
# 통째로 밀렸다(화면상 «다음 실행» 은 지났는데 아무 일도 안 일어난다).
LANE_SCHEDULER = "scheduler"
# 색인 레인(S9 · D-203). 스케줄러와 성격이 같다 — **잡을 하나도 클레임하지 않는다.**
# 할 일 목록이 이미 `ai_index_state` 표이기 때문이다: 문서를 저장할 때 그 행이
# `pending` 이 되고, 레인은 그 행을 훑는다. 잡 큐를 하나 더 두면 「큐에서는 사라졌는데
# 결과가 없는」 상태가 만들어지고 그 상태는 아무 화면에도 안 나온다.
#
# 배치 레인과 나누는 이유는 하나다 — **임베딩이 배치 틱을 굶기지 않게.** 한 문서의
# 첨부를 파싱하고 임베딩하는 데 수 초가 걸리는데, 그것이 배치 워커 안에 있으면 그동안
# 메일·동기화·스케줄 발화가 통째로 밀린다.
LANE_INDEX = "index"

# 대화형 job_type. chat_message는 사용자가 화면 앞에서 기다리는 요청이고, llm_connection_test도
# 같은 이유로 최근 이 큐로 옮겨졌다(핸들러 자신의 주석 참고 — 웹 요청에서 기다리면 처리 칸이
# 수십 초 잠긴다). 배치 잡(schedule_run·mail_send·
# project_weekly_summary)은 전부 여기 없다 — 기본값(제외 목록 없음)이 배치 레인이 된다.
CONVERSATIONAL_JOB_TYPES: tuple[str, ...] = ("chat_message", JOB_TYPE_TEST)


def lock_filename(lane: str) -> str:
    """레인별 워커 리스 파일 이름. 배치 레인은 기존 `worker.lock`을 그대로 쓴다 —
    in-place 업그레이드 중 기존 리스가 고아가 되거나, 배포 순간 배치 워커가 잠깐
    둘로 보이는 창을 만들지 않기 위해서다."""
    if lane == LANE_CONVERSATIONAL:
        return "worker-conversational.lock"
    if lane == LANE_SCHEDULER:
        return "scheduler.lock"
    if lane == LANE_INDEX:
        return "index.lock"
    return "worker.lock"


def liveness_component(lane: str) -> str:
    """레인별 헬스 대시보드 liveness 컴포넌트 이름.

    스케줄러 레인이 `scheduler`를 쓰는 것이 핵심이다 — 대시보드의 그 칸은 예전에도
    `scheduler`였고(배치 워커의 하트비트 스레드가 함께 찍었다), 레인을 꺼낸 뒤에도
    같은 이름을 같은 뜻으로 유지한다. 이름이 바뀌면 대시보드가 «스케줄러 없음»을
    보여 주는데 실제로는 멀쩡히 돌고 있는, 가장 헷갈리는 종류의 거짓말이 된다.
    """
    if lane == LANE_CONVERSATIONAL:
        return "worker_conversational"
    if lane == LANE_SCHEDULER:
        return "scheduler"
    if lane == LANE_INDEX:
        return "index"
    return "worker"
