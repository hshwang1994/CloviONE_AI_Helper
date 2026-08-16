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

# 대화형 job_type. chat_message는 사용자가 화면 앞에서 기다리는 요청이고, llm_connection_test도
# 같은 이유로 최근 이 큐로 옮겨졌다(핸들러 자신의 주석 참고 — 웹 요청에서 기다리면 처리 칸이
# 수십 초 잠긴다). 배치 잡(schedule_run·document_generate·notion_mapping_sync·mail_send·
# project_weekly_summary)은 전부 여기 없다 — 기본값(제외 목록 없음)이 배치 레인이 된다.
CONVERSATIONAL_JOB_TYPES: tuple[str, ...] = ("chat_message", JOB_TYPE_TEST)


def lock_filename(lane: str) -> str:
    """레인별 워커 리스 파일 이름. 배치 레인은 기존 `worker.lock`을 그대로 쓴다 —
    in-place 업그레이드 중 기존 리스가 고아가 되거나, 배포 순간 배치 워커가 잠깐
    둘로 보이는 창을 만들지 않기 위해서다."""
    if lane == LANE_CONVERSATIONAL:
        return "worker-conversational.lock"
    return "worker.lock"


def liveness_component(lane: str) -> str:
    """레인별 헬스 대시보드 liveness 컴포넌트 이름."""
    if lane == LANE_CONVERSATIONAL:
        return "worker_conversational"
    return "worker"
