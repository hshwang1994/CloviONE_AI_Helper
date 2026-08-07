"""project_weekly_summary 잡 핸들러 — 주간 리포트에 AI 요약을 실제로 만든다 (§L 소비처).

## 왜 여태 아무도 안 불렀나

`app/llm/service.py::LlmService` 와 `app/projects/models.py::REPORT_SOURCE_LLM` 는
9-5 라운드에 이미 만들어졌지만, 부를 자리가 없었다 — `app/projects/service.py` 의
GET 경로(`project_weekly_report`)는 의도적으로 LLM 을 안 부른다(CLI 왕복이 수십 초라
웹 요청 스레드를 그만큼 묶는다, `app/llm/service.py` docstring 참조). 잡 큐를 지나는
경로가 없어서 `llm_summary` 는 항상 `None` 이었다. 이 파일이 그 경로다.

## 무엇을 프롬프트로 주는가

`app/projects/service.py::project_weekly_report` 가 이미 만든 규칙 기반
`summary_md`(완료/진행/지연/이슈/다음 주/마일스톤을 다 반영한 문장)를 그대로 입력으로
준다 - 새로 사실을 모으지 않는다. LLM 은 **이미 맞는 사실을 사람이 읽기 좋은 문단으로
다듬는 역할**이지, 사실 자체를 만드는 역할이 아니다(그러면 숫자가 둘이 되고 어느 쪽이
맞는지 아무도 모른다).

## 실패하면 무엇을 남기는가

`app/llm/service.py::LlmService.summarize` 는 예외를 던지지 않고 `LlmResult` 를 돌려준다.
실패(`.ok == False`)면 **기존 저장본을 건드리지 않는다** - 지난주에 저장된 규칙/AI 요약이
있다면 그대로 둔다. 새로 생성 시도가 실패했다고 예전 것까지 지우면 사용자에게는 "있던
것도 없어졌다"로 보인다. 대신 `PermanentJobError` 로 잡을 실패 처리해 큐 화면에 이유가
남게 하고, 재시도는 하지 않는다(로그인 안 됨/설정 꺼짐/타임아웃은 몇 초 뒤에 다시 해도
같은 답이다 - `llm_connection_test` 핸들러와 같은 판단).
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload
from app.llm.service import build_service
from app.projects.models import Project

logger = logging.getLogger("app.handlers.project_weekly_summary")


def handle_project_weekly_summary(db: Session, job: Job, ctx: WorkerContext) -> None:
    payload = parse_payload(job)
    project_id = payload.get("project_id")
    week_of = payload.get("week_of")
    if not project_id or not week_of:
        raise PermanentJobError("payload에 project_id/week_of가 없습니다.")

    project = db.get(Project, project_id)
    if project is None:
        # 잡을 큐에 넣은 뒤 프로젝트가 지워졌을 수 있다 - 드물지만 재시도해도 안 생긴다.
        raise PermanentJobError("프로젝트를 찾을 수 없습니다.")

    from app.projects import service as project_service
    from app.projects import weekly

    week = weekly.week_for(date.fromisoformat(week_of))
    report = project_service.project_weekly_report(
        db, project, week=week, settings=ctx.settings
    )
    body = report["summary_md"]

    llm = build_service(
        ctx.settings, backend=ctx.extras.get("llm_backend"), outbound=ctx.outbound_client
    )
    result = llm.summarize(body=body)
    if not result.ok:
        logger.warning(
            "프로젝트 %s %s주 AI 요약 실패: %s", project_id, week_of, result.status
        )
        raise PermanentJobError(result.status)

    now = ctx.clock.now()
    project_service.save_llm_weekly_summary(
        db, project, week=week, text=result.text, now=now
    )
    db.commit()
    logger.info("프로젝트 %s %s주 AI 요약 저장 완료", project_id, week_of)


__all__ = ["handle_project_weekly_summary"]
