"""UB-09: `quotas.service.pending()`이 세는 job_type 집합이 실제로 `record_call`을
부르는 잡 핸들러 전부를 덮는지 상시 확인한다.

`pending()`은 "아직 `usage_events`에 안 남았지만 이미 쓰기로 확정된" AI 호출을 큐에
쌓인 잡 행으로 센다(`app/quotas/service.py` 모듈 docstring 참조) — 그래야 확인(라우터)과
기록(워커)이 다른 프로세스에 있어도 그 사이에 동시 요청이 상한을 통과하지 못한다. 이
계산이 맞으려면 "나중에 `record_call`을 부르는 잡 유형 전부"를 알아야 하는데, 그 지식이
`PENDING_JOB_TYPES`라는 한 집합에만 있다 — 새 AI 잡 핸들러가 이 패턴(예약→워커가 나중에
기록)을 쓰기 시작했는데 그 집합에 추가를 깜빡하면, `pending()`이 그 잡의 예약을 조용히
놓쳐 상한이 샌다. 증상은 "청구서가 예상보다 크다"로 몇 달 뒤에야 드러난다(모듈이 스스로
적어 둔 경고, UB-09).

`test_job_handler_registration_complete.py`(USE-02, 잡 유형이 핸들러 등록과 맞는지)와
같은 결함 부류를 다른 축(잡 유형이 쿼터 예약 집합과 맞는지)에서 잡는다 — 실제 핸들러
소스 파일을 훑어 `record_call(` 호출이 있는 파일을 찾고, 그 job_type이
`PENDING_JOB_TYPES`에 있는지 대조한다. 매핑에 없는 새 핸들러 파일이 `record_call`을
부르기 시작해도 이 시험이 잡는다(고정된 목록이 아니라 실제 디렉터리를 훑는다).
"""

from __future__ import annotations

from pathlib import Path

from app.quotas.service import PENDING_JOB_TYPES

HANDLERS_DIR = Path(__file__).resolve().parents[2] / "app" / "jobs" / "handlers"

# 핸들러 파일 → 그 파일이 처리하는 job_type. `test_job_handler_registration_complete.py`
# 와 같은 이유로 전용 상수가 없는 핸들러는 실제 enqueue 호출부와 대조한 문자 그대로를 쓴다.
_HANDLER_JOB_TYPES = {
    "chat_message.py": "chat_message",
    "document_generate.py": "document_generate",
    "llm_connection_test.py": "llm_connection_test",
    "mail_send.py": "mail_send",
    "notion_mapping_sync.py": "notion_mapping_sync",
    "project_weekly_summary.py": "project_weekly_summary",
    "schedule_run.py": "schedule_run",
}


def test_pending_job_types_cover_every_record_call_handler():
    handler_files = sorted(
        p for p in HANDLERS_DIR.glob("*.py") if p.name != "__init__.py"
    )
    assert handler_files, f"핸들러 디렉터리가 비어 있다: {HANDLERS_DIR}"

    unmapped: list[str] = []
    uncovered: list[tuple[str, str]] = []
    for path in handler_files:
        if "record_call(" not in path.read_text(encoding="utf-8"):
            continue
        job_type = _HANDLER_JOB_TYPES.get(path.name)
        if job_type is None:
            unmapped.append(path.name)
            continue
        if job_type not in PENDING_JOB_TYPES:
            uncovered.append((path.name, job_type))

    assert not unmapped, (
        f"이 핸들러 파일들은 record_call을 부르는데 이 시험의 _HANDLER_JOB_TYPES에 매핑이 "
        f"없다: {unmapped} — 이 파일 상단에 job_type 매핑을 추가하라."
    )
    assert not uncovered, (
        f"이 잡 핸들러들은 record_call을 부르는데 PENDING_JOB_TYPES에 없다: {uncovered} — "
        "app/quotas/service.py::PENDING_JOB_TYPES에 추가하라. 안 하면 quotas.service.pending()"
        "이 이 잡의 예약을 놓쳐 동시 요청이 AI 사용 상한을 통과할 수 있다(UB-09)."
    )
