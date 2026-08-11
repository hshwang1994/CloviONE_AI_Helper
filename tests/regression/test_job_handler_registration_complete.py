"""USE-02: every job_type that gets enqueued must have a handler registered.

`/diagnostics`가 실제로 "등록되지 않은 job_type: notion_mapping_sync" 오류 이력을 보여준 적이
있었다 — 그 잡을 큐에 넣는 코드는 있는데 `app/worker_main.py::build_handlers()`가 그 시점엔
그 핸들러를 등록하지 않았던 배포 창이 있었던 것으로 보인다(지금은 등록돼 있다, 아래 확인).

이 결함 부류(잡을 넣는 코드와 핸들러를 등록하는 코드가 서로 다른 파일에 있어 한쪽만 고쳐도
둘 다 컴파일·기동에는 성공한다 — 실제로 그 잡이 큐에 들어가야만 "등록되지 않음" 실패가
드러난다, 조용한 실패)가 다시 생기지 않게, 실제로 잡을 큐에 넣는 모든 지점의 job_type을
그 **원본 상수**에서 직접 가져와 build_handlers()의 키 집합과 대조한다. 새 job_type을
추가하면서 핸들러 등록을 깜빡하면 이 시험이 즉시 잡는다.
"""

from app.jobs.models import JOB_TYPE_CHAT_MESSAGE
from app.llm_console.service import JOB_TYPE_TEST
from app.mail.service import MAIL_JOB_TYPE
from app.worker_main import build_handlers

# 아래 리터럴 넷(schedule_run/document_generate/notion_mapping_sync/project_weekly_summary)은
# 전용 상수가 없어 app/schedules/scheduler.py, app/documents/service.py,
# app/notion_mapping/service.py, app/projects/service.py의 실제 enqueue(job_type=...) 호출부와
# 문자 그대로 대조해 뽑았다(2026-08-11 grep 확인) — 새 호출부가 다른 문자열을 쓰면 여기도
# 갱신해야 한다.
_ALL_ENQUEUED_JOB_TYPES = {
    JOB_TYPE_CHAT_MESSAGE,
    MAIL_JOB_TYPE,
    JOB_TYPE_TEST,
    "schedule_run",
    "document_generate",
    "notion_mapping_sync",
    "project_weekly_summary",
}


def test_every_enqueued_job_type_has_a_registered_handler():
    handlers = build_handlers()
    missing = _ALL_ENQUEUED_JOB_TYPES - set(handlers)
    assert not missing, (
        f"이 job_type들은 큐에 들어가는데 워커 핸들러가 없다: {missing} — "
        "worker_main.py::build_handlers()에 등록을 추가하라. 등록이 없으면 그 잡은 "
        "'등록되지 않은 job_type' 영구 실패로 조용히 죽는다(app/jobs/worker.py)."
    )
