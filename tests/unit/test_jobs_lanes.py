"""D-118 Phase 1 — 레인 정의(app/jobs/lanes.py)가 claim 필터·sweep 필터·리스 경로·
liveness 컴포넌트 네 곳이 공유하는 단일 정본이라는 계약을 고정한다.

qa-contract-change: 대화형 레인에 로컬 릴레이 준비 점검(`mail_relay_check`, D-551)이 더해졌다 - 메일 연결 확인과 같이 관리자가
화면 앞에서 결과를 기다리는 잡이다. 대화형 집합을 정확히 같다고 재는 단언은 그대로이고 집합에 하나가 늘었다.
"""

import pytest

from app.jobs import lanes

pytestmark = pytest.mark.unit


def test_conversational_job_types_are_the_latency_sensitive_two():
    assert set(lanes.CONVERSATIONAL_JOB_TYPES) == {"chat_message", "llm_connection_test", "mail_verify", "mail_relay_check"}


def test_batch_job_types_are_not_in_the_conversational_set():
    for batch_type in ("schedule_run", "document_generate", "notion_mapping_sync",
                        "mail_send", "project_weekly_summary"):
        assert batch_type not in lanes.CONVERSATIONAL_JOB_TYPES


def test_lock_filename_batch_matches_pre_lane_filename():
    assert lanes.lock_filename(lanes.LANE_BATCH) == "worker.lock"


def test_lock_filename_conversational_is_distinct():
    conv = lanes.lock_filename(lanes.LANE_CONVERSATIONAL)
    assert conv != lanes.lock_filename(lanes.LANE_BATCH)


def test_liveness_component_names_are_distinct_per_lane():
    batch = lanes.liveness_component(lanes.LANE_BATCH)
    conv = lanes.liveness_component(lanes.LANE_CONVERSATIONAL)
    assert batch == "worker"
    assert conv == "worker_conversational"
    assert batch != conv
