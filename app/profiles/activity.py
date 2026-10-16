"""내 활동 피드 — '내가 한 일'과 '나에게 일어난 일'을 한 줄기로 합친다.

## 왜 새 표를 만들지 않는가

두 사건은 이미 각각 기록되고 있다: 내가 한 일은 `audit_log`(actor = 나), 나에게 일어난
일은 `notifications`(user_id = 나). 세 번째 표를 만들면 같은 사건이 두 곳에 적히고,
한쪽만 기록하는 코드 경로가 생기는 순간 피드가 조용히 진실을 잃는다. 여기서는 **읽어서
합치기만** 한다 — 쓰기가 0이라 어긋날 여지가 없다.

## 감사 로그를 사용자에게 보여도 되는가

여기서 읽는 것은 `actor_id == 나` 인 행뿐이다. 즉 **내가 한 일**만 나온다. before/after
JSON 은 싣지 않는다 — 감사 화면(관리자용)이 다루는 값이고, 개인 피드에는 '무엇을 했는가'
한 줄이면 충분하다. 마스킹된 값이라도 굳이 개인 화면에 다시 펼칠 이유가 없다.

## 두 어휘를 한 표로 합치지 않는 이유

알림의 `related_object_type`(`chat_room`, `chat_mention`)과 감사의 `object_type`
(`notion_task`, `notion_document`, `board_post`…)은 **서로 다른 두 작성자가 만든 다른
어휘**다. 딥링크는 알림 쪽 표(`app/notifications/destinations.py`)를 **먼저** 물어보고,
거기 없는 감사 전용 유형만 아래 표가 답한다. 그래서 알림 목적지를 바꿀 곳은 여전히 한
곳이고, 이 파일은 감사 어휘에 대해서만 책임진다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.core.text import object_particle as _object_particle
from app.notifications.destinations import destination_for
from app.notifications.models import Notification

KIND_DID = "did"          # 내가 한 일 (audit_log)
KIND_HAPPENED = "happened"  # 나에게 일어난 일 (notifications)

# 감사 `object_type` → 화면 경로. 알림 표에 없는 것만 여기 둔다(모듈 docstring 참조).
# 목적지에 `{id}` 가 있는데 object_id 가 비면 링크를 만들지 않는다 — 목록만 열리는
# 링크는 사용자를 원점으로 돌려보낼 뿐이다.
AUDIT_DESTINATIONS: dict[str, str] = {
    "notion_task": "/tickets/{id}",
    "notion_document": "/team-docs/{id}",
    "board_post": "/board/{id}",
    "chat_room": "/chat-rooms/{id}",
}

# 감사 object_type → 한국어 명사. 화면에 'notion_task' 를 그대로 보이면 사용자는 자기가
# 무엇을 했는지 알 수 없다.
#
# **여기 빠진 유형이 있으면 문장이 "만듦" 처럼 목적어 없이 나온다** — 실제로 캡처에서 그렇게
# 보였다(`department.create` 가 표에 없어서). 그래서 tests/unit/test_activity_labels.py 가
# 코드가 실제로 쓰는 object_type 을 훑어 이 표에 다 있는지 확인한다.
OBJECT_LABELS: dict[str, str] = {
    "notion_task": "티켓",
    "notion_document": "문서",
    # 문서 소속 지정(0060 진단 화면). 감사 대상이 외부 미러 행이 아니라 **Portal 이 정한
    # 소속**이라 `notion_document` 와 다른 이름을 쓴다.
    "document": "문서",
    "document_comment": "문서 댓글",
    # 0027. 새 문서가 시작할 틀. 「문서」와 다른 이름인 이유는 감사 화면의 「관련 항목」
    # 링크가 가리키는 표가 다르기 때문이다 — 한 이름으로 뭉치면 그 링크가 안 열린다.
    "document_template": "문서 틀",
    "document_sync": "문서 동기화",
    # 강제 재동기화/재색인 트리거(C7). 운영자가 지금 당장 다시 동기화/색인하라고 누른 경로다.
    "ticket_sync": "티켓 동기화",
    "search_index": "검색 색인",
    "document_generation": "문서 생성",
    "board_post": "게시글",
    "board_comment": "댓글",
    "board_attachment": "첨부",
    "chat_room": "채팅방",
    "ticket_comment": "티켓 댓글",
    "ticket_attachment": "티켓 첨부",
    # S6. `notion_task` 와 **다른 이름인 이유**: 저쪽은 외부 미러 행을 가리키는 옛 이름
    # (page id 를 object_id 로 쓴다)이고, 이쪽은 자체 표의 티켓(uuid)이다. 한 이름으로
    # 뭉치면 감사 화면의 「관련 항목」 링크가 어느 축인지 몰라 절반이 안 열린다.
    "ticket": "티켓",
    "sprint": "회차",
    # S7. 공간은 **권한 경계**라 감사 화면에서 프로젝트·부서와 같은 급으로 읽혀야 한다.
    "knowledge_space": "지식 공간",
    # S8. 첨부를 붙이고 떼는 기록은 **문서**에 달린다 — 파일이 아니다. 감사 화면에서
    # 「무엇이 바뀌었나」의 답은 언제나 그 문서이고, 파일 id 는 사람이 못 알아본다.
    "knowledge_document": "지식 문서",
    # S8. 저장소를 켜고 끄는 것은 **업로드가 어디로 가는지**를 바꾸는 일이라, 감사
    # 화면에서 백업·연동과 같은 급으로 읽혀야 한다.
    "storage_provider": "파일 저장소",
    # 회의에서 정한 것과 그래서 할 일(D 회차의 `sprint_decisions`). 「스프린트」와 다른
    # 이름인 이유는 감사 줄이 가리키는 것이 회차가 아니라 **그 안의 한 줄**이기 때문이다.
    "sprint_decision": "회의 기록",
    # 문서 태그 어휘(G 회차). 이름을 고치고 지우는 것이 감사 대상이 됐다 — 그 동작 하나가
    # 그 태그를 쓰는 **모든 문서**의 분류 표기를 바꾼다.
    "tag": "문서 태그",
    # 문서 카테고리(D-404 · 0026) — 태그와 대칭인 어휘 CRUD 가 감사 대상이다.
    "document_category": "문서 분류",
    "organization": "조직",
    "project": "프로젝트",
    "project_milestone": "마일스톤",
    "user": "계정",
    "user_notion_mapping": "Notion 연결",
    "approval": "승인",
    "backup": "백업",
    "integration": "외부 연동",
    "job": "작업",
    # 메일 발송(9-9 P4). 관리 콘솔의 시험 발송이 이 이름으로 감사에 남는다.
    "mail_delivery": "메일 발송",
    # 메일 서버 연결 확인(D-512)과 조직 정합성의 일괄 정리(D-508).
    "mail_settings": "메일 설정",
    "integrity_check": "조직 정합성 검사",
    "runner": "러너",
    "schedule": "실행 일정",
    "schedule_run": "실행 이력",
    "template": "템플릿",
    "offboarding_run": "오프보딩",
    "session": "세션",
    # 아래는 라우터가 변수로 넘기는 값들이다(문자열 리터럴 grep 만으로는 안 보인다):
    #   app/org/router.py    audit_type="department" / "job_title"
    #   app/prompts/router.py object_type=kind → "prompts" | "policies" (라우터를 만드는 이름이 복수형이다)
    #   app/settings/service.py OBJECT_TYPE = "app_setting"
    #   app/workflows/service.py OBJECT_TYPE = "workflow"
    "department": "부서",
    "job_title": "직책",
    "prompts": "프롬프트",
    "policies": "정책",
    "app_setting": "설정",
    "workflow": "워크플로",
    #   app/sysops/router.py OBJECT_TYPE = "system_setting" (타임존·DNS·인증서 등 서버 설정)
    "system_setting": "시스템 설정",
    #   app/admin/secrets_router.py OBJECT_TYPE = "secret" (메일 비밀번호, AI 키. 값은 남기지 않는다)
    "secret": "비밀 값",
    # 관리자 백로그 잔여(0033, PLAN Phase 6).
    "announcement": "공지",
    "ai_quota": "AI 사용 한도",
    "approval_delegation": "승인 위임",
    "feature_flag": "기능 플래그",
    "restore_rehearsal": "복구 리허설",
    # Notion 관리(9-4)와 LLM 관리(9-5). 토큰 교체, 연결 테스트, 데이터베이스 생성이
    # 이 이름으로 감사에 남는다.
    "notion_token": "Notion 토큰",
    "notion_database": "Notion 데이터베이스",
    "llm_config": "AI 설정",
    # AI 설정 화면(D-515). 설정 저장과 연결 확인이 이 이름으로 감사에 남는다.
    "ai_config": "AI 설정",
    # 승인을 기다리는 AI 문서 초안(D-519). 승인 요청과 실행이 이 이름으로 감사에 남는다.
    "ai_action_request": "AI 초안",
    # 첫 관리자 설정 코드(D-522). 틀린 코드로 코드가 폐기된 일이 이 이름으로 남는다.
    "setup": "초기 설정",
}

# 액션 문자열의 **마지막 조각** → 한국어 동사. 'ticket.body.update' 처럼 조각이 셋이어도
# 마지막이 동사라는 규약을 지켜 온 덕에 표 하나로 전부 읽을 수 있다.
# 🔴 **한 목록이 두 말투를 쓰지 않는다** (S19).
#
# 예전에는 이 표가 명사형("만듦"·"고침")이었고 `ACTION_SENTENCES` 는 완결형("로그인했습니다")
# 이었다. 그래서 같은 피드에 「로그인했습니다」 바로 아래 「게시글을 만듦」이 왔다 — 한 화면이
# 두 문체로 말하면 사용자는 둘이 다른 종류의 기록이라고 읽는다. CLAUDE.md 의 한국어 규칙도
# 조각 문장을 금지한다. 완결형으로 통일한다.
VERB_LABELS: dict[str, str] = {
    # 동사는 표준 동사표를 따른다(만들기 → 추가, 고치기 → 수정, 지우기 → 삭제, 켜기 · 끄기 → 활성화 · 비활성화 — r23).
    # 화면 단추가 「추가」인데 기록이 「만들었습니다」면 같은 일을 두 이름으로 부른다.
    "create": "추가했습니다",
    "update": "수정했습니다",
    "delete": "삭제했습니다",
    "trash": "휴지통으로 보냈습니다",
    "claim": "가져갔습니다",
    "pin": "고정했습니다",
    "upload": "올렸습니다",
    "sync": "동기화했습니다",
    "publish": "발행했습니다",
    "enable": "활성화했습니다",
    "disable": "비활성화했습니다",
    "login": "로그인했습니다",
    "logout": "로그아웃했습니다",
    "approve": "승인했습니다",
    "cancel": "취소했습니다",
    "retry": "다시 시도했습니다",
    "rollback": "되돌렸습니다",
    "clone": "복제했습니다",
    "verify": "확인했습니다",
    "run": "실행했습니다",
    "undo": "되돌렸습니다",
    # Notion / AI 연결 확인(9-4, 9-5). 'notion.connection.test' 처럼 마지막이 동사다.
    "test": "확인했습니다",
    # r23 — 서버가 기록하는 나머지 동사. 「대상을 동사」로 바로 이어지는 것만 여기 둔다(목적어를 품은 동사는 아래 통문장 표).
    "add": "추가했습니다",
    "edit": "수정했습니다",
    "remove": "삭제했습니다",
    "archive": "보관했습니다",
    "restore": "복원했습니다",
    "purge": "영구 삭제했습니다",
    "download": "내려받았습니다",
    "close": "닫았습니다",
    "start": "시작했습니다",
    "stop": "끝냈습니다",
    "revoke": "거뒀습니다",
    "write": "저장했습니다",
    "apply": "적용했습니다",
    "check": "점검했습니다",
    "connect": "연결했습니다",
}

# 위 규칙(명사 + 동사)으로 자연스럽게 읽히지 않는 액션은 통째로 문장을 준다.
ACTION_SENTENCES: dict[str, str] = {
    "user.login": "로그인했습니다",
    "user.logout": "로그아웃했습니다",
    "user.login_failed": "로그인에 실패했습니다",
    "user.password_change_self": "비밀번호를 변경했습니다",
    "user.password_change_failed": "비밀번호 변경에 실패했습니다",
    # 첫 관리자(D-522). 설치 코드로 만든 계정의 첫 줄이다.
    "setup.first_admin_created": "설치 코드로 첫 시스템 관리자 계정을 추가했습니다",
    "setup.first_admin_locked": "첫 관리자 추가 경로를 잠갔습니다",
    "profile.avatar.update": "프로필 사진을 바꿨습니다",
    "profile.avatar.delete": "프로필 사진을 삭제했습니다",
    "profile.preferences.update": "알림과 방해금지 설정을 바꿨습니다",
    "profile.sessions.revoke_others": "내 다른 기기의 로그인을 모두 해제했습니다",
    "profile.sessions.revoke": "다른 기기의 로그인을 해제했습니다",
    "profile.notify_email.requested": "알림 받을 메일 주소 확인을 요청했습니다",
    "profile.notify_email.verified": "알림 받을 메일 주소를 확인했습니다",
    "profile.notify_email.cleared": "알림 받을 메일 주소를 계정 이메일로 되돌렸습니다",
    # 채팅방을 파하는 동작은 방을 지운다(`team_chat.service.disband_room`, soft delete) — 화면 낱말도 「삭제」다.
    # 참여자를 더하는 동작은 화면 이름이 「초대」다(관리 창 단추 · 「N명을 초대했습니다.」 알림). 수락 절차 없이 바로 들어오는
    # 메신저의 관용과 같은 말이라 기록도 같은 낱말을 쓴다.
    "team_chat.create_group": "채팅방을 추가했습니다",
    "team_chat.disband": "채팅방을 삭제했습니다",
    "team_chat.rename": "채팅방 이름을 바꿨습니다",
    "team_chat.add_members": "채팅방에 참여자를 초대했습니다",
    "team_chat.remove_member": "채팅방에서 참여자를 내보냈습니다",
    "team_chat.transfer_owner": "채팅방 방장을 넘겼습니다",
    # r23 — 아래는 「대상 + 동사」로 이으면 목적어가 겹치거나 동사가 표에 없는 동작이다. 빠지면 내 활동에 원문
    # (`메일 발송: mail.test_send`)이 섰다. `tests/unit/test_activity_labels.py` 가 서버의 감사 호출을 훑어 대조한다.
    "ai.config.update": "AI 설정을 수정했습니다",
    "ai.connection.test": "AI 연결을 확인했습니다",
    "ai.oauth.start": "ChatGPT 계정 연결을 시작했습니다",
    "ai.oauth.connect": "ChatGPT 계정을 연결했습니다",
    "ai.oauth.logout": "ChatGPT 계정 연결을 해제했습니다",
    "ai.document.drafted": "AI 문서 초안을 작성했습니다",
    "ai.document.approval_requested": "AI 문서 저장 승인을 요청했습니다",
    "ai.document.created_on_approval": "승인을 받아 AI 문서를 추가했습니다",
    "approval_delegation.revoke": "승인 위임을 거뒀습니다",
    "approval_delegation.restore": "승인 위임을 다시 적용했습니다",
    "backup.download": "백업 파일을 내려받았습니다",
    "backup.discard_file": "서버에서 백업 파일을 삭제했습니다",
    "board.idea.status": "기능 개선 제안의 상태를 바꿨습니다",
    "cli.user.archive": "명령줄에서 계정을 보관했습니다",
    "cli.user.unarchive": "명령줄에서 계정 보관을 해제했습니다",
    "cli.user.reset_password": "명령줄에서 비밀번호를 재설정했습니다",
    "cli.user.revoke_sessions": "명령줄에서 로그인 세션을 모두 해제했습니다",
    "cli.user.set_role": "명령줄에서 역할을 바꿨습니다",
    "cli.user.unlock": "명령줄에서 계정 잠금을 해제했습니다",
    "impersonation.start": "대리 보기를 시작했습니다",
    "impersonation.stop": "대리 보기를 끝냈습니다",
    "integration.change_config": "외부 연동 설정을 바꿨습니다",
    "integration.change_requested": "외부 연동 설정 변경을 요청했습니다",
    "integration.rollback_requested": "외부 연동 설정 되돌리기를 요청했습니다",
    "integrity.assign_membership": "사용자의 소속을 지정했습니다",
    "integrity.fix": "조직 정합성 문제를 정리했습니다",
    "knowledge.attachment.add": "문서에 첨부 파일을 추가했습니다",
    "knowledge.attachment.remove": "문서의 첨부 파일을 삭제했습니다",
    "knowledge.category_delete": "문서 분류를 삭제했습니다",
    "knowledge.category_rename": "문서 분류 이름을 바꿨습니다",
    "knowledge.document_archive": "문서를 보관했습니다",
    "knowledge.document_move_project": "문서를 다른 프로젝트로 옮겼습니다",
    "knowledge.document_purge": "문서를 영구 삭제했습니다",
    "knowledge.document_restore": "문서를 복원했습니다",
    "knowledge.space_create": "지식 공간을 추가했습니다",
    "knowledge.space_update": "지식 공간을 수정했습니다",
    "knowledge.tag_delete": "문서 태그를 삭제했습니다",
    "knowledge.tag_rename": "문서 태그 이름을 바꿨습니다",
    "knowledge.template_create": "문서 서식을 추가했습니다",
    "knowledge.template_update": "문서 서식을 수정했습니다",
    "knowledge.template_delete": "문서 서식을 삭제했습니다",
    "knowledge.version_restore": "문서를 이전 판으로 되돌렸습니다",
    "mail.test_send": "시험 메일을 보냈습니다",
    "mail.resend": "메일을 다시 보냈습니다",
    "mail.cancel": "메일 발송을 취소했습니다",
    "mail.verify": "메일 서버 연결을 확인했습니다",
    "mail.inbox_confirm": "받은 편지함 확인 결과를 기록했습니다",
    "mail.requeue_on_recovery": "메일 서버가 복구되어 대기 메일을 다시 보냈습니다",
    "mail.requeue_unconfigured": "메일 설정을 마쳐 대기 메일을 다시 보냈습니다",
    "mail.relay.apply": "로컬 릴레이 설정을 적용했습니다",
    "mail.relay.check": "로컬 릴레이를 점검했습니다",
    "mail.relay.dkim": "DKIM 키를 설정했습니다",
    "mail.relay.flush": "대기 메일을 다시 보냈습니다",
    "project.export_xlsx": "프로젝트를 엑셀로 내보냈습니다",
    "project.health.snapshot": "프로젝트 건강도를 기록했습니다",
    "project.progress.recompute": "프로젝트 진행률을 다시 계산했습니다",
    "project.weekly_report.generate": "주간 리포트를 저장했습니다",
    "project.weekly_report.llm_summary_requested": "주간 리포트 AI 요약을 요청했습니다",
    "prompts.transition": "프롬프트 상태를 바꿨습니다",
    "prompts.update_content": "프롬프트 내용을 수정했습니다",
    "schedule.cancel_run": "예약 실행을 취소했습니다",
    "schedule.retry_run": "예약 실행을 다시 시도했습니다",
    "schedule.run_now": "실행 일정을 지금 실행했습니다",
    "schedule.enable_requested": "실행 일정 활성화를 요청했습니다",
    "search.reindex": "검색 색인을 다시 만들었습니다",
    "secret.write": "비밀 값을 저장했습니다",
    "secret.delete": "비밀 값을 삭제했습니다",
    "setting.rollback": "설정을 이전 값으로 되돌렸습니다",
    "sprint.close": "회차를 닫았습니다",
    "sprint.state": "회차 상태를 바꿨습니다",
    "sprint.decision.add": "회의 기록을 추가했습니다",
    "sprint.decision.edit": "회의 기록을 수정했습니다",
    "system_action": "시스템 작업을 실행했습니다",
    "team_docs.allowed_users": "문서 열람자를 지정했습니다",
    "team_docs.restrict": "문서 열람을 제한했습니다",
    "ticket.board_move": "작업 보드에서 티켓을 옮겼습니다",
    "ticket.exception_assign": "티켓을 예외로 배정했습니다",
    "ticket.relation_add": "티켓 관계를 추가했습니다",
    "ticket.relation_remove": "티켓 관계를 삭제했습니다",
    "trash.purge": "휴지통에서 영구 삭제했습니다",
    "trash.restore": "휴지통에서 복원했습니다",
    "integration.rollback": "외부 연동 설정을 되돌렸습니다",
    "user.export_csv": "계정 목록을 CSV로 내보냈습니다",
    "user.import_create": "CSV로 계정을 추가했습니다",
    "user.password_reset": "메일 링크로 비밀번호를 재설정했습니다",
    "user.password_reset_requested": "비밀번호 재설정 메일을 요청했습니다",
    "user.reset_password": "계정의 비밀번호를 재설정했습니다",
    "user.revoke_sessions": "계정의 로그인을 모두 해제했습니다",
    "user.role_change": "계정 역할을 바꿨습니다",
    "user.role_change_requested": "계정 역할 변경을 요청했습니다",
    "user.unarchive": "계정 보관을 해제했습니다",
    "user.unlock": "계정 잠금을 해제했습니다",
}


# 조사 계산은 `app/core/text.py` 에 하나만 둔다 — 이 파일이 처음 판정했고 폼 검증·조직
# 오류 문구가 뒤따라 같은 규칙이 필요해졌다. 세 번째로 베끼면 「job를」과 「job을」이
# 같은 제품 안에서 동시에 나온다. 이 이름으로 가져다 쓰던 호출자를 위해 다시 내보낸다.
object_particle = _object_particle


def describe_action(action: str, object_type: str | None) -> str:
    """감사 한 줄을 사람 문장으로. 모르는 액션이어도 **원문을 그대로 보여 준다**.

    빈 문자열이나 '알 수 없는 활동' 으로 뭉개지 않는다 — 내가 한 일인데 무엇인지 알 수
    없게 만드는 것이 이 화면에서 할 수 있는 가장 나쁜 일이다. 원문이라도 보이면
    사용자는 최소한 검색해서 물어볼 수 있다.
    """
    sentence = ACTION_SENTENCES.get(action)
    if sentence:
        return sentence
    parts = (action or "").split(".")
    verb = VERB_LABELS.get(parts[-1]) if parts else None
    noun = OBJECT_LABELS.get(object_type or "")
    if verb and noun:
        return f"{noun}{object_particle(noun)} {verb}"
    if verb and action:
        # 동사만 알고 대상을 모르면 동사만 내지 않는다 — "만들었습니다" 한 마디는 무엇을
        # 만들었는지 알려 주지 않아 원문보다도 정보가 적다. 원문을 함께 남긴다.
        return f"{verb} ({action})"
    if noun:
        return f"{noun}: {action}"
    return action or "활동"


def route_for(object_type: str | None, object_id: str | None) -> str | None:
    """딥링크 경로. 알림 표를 먼저 묻고, 없으면 감사 전용 표를 본다."""
    route = destination_for(object_type, object_id)
    if route:
        return route
    template = AUDIT_DESTINATIONS.get(object_type or "")
    if not template:
        return None
    if "{id}" in template:
        if not object_id:
            return None
        # id 는 서버가 만든 값이지만 경로를 깨뜨릴 문자는 통과시키지 않는다.
        if any(ch in object_id for ch in "/?#\\ "):
            return None
        return template.replace("{id}", object_id)
    return template


def _audit_item(row: AuditLog) -> dict:
    return {
        "id": "audit:" + row.id,
        "kind": KIND_DID,
        "at": row.created_at.isoformat(),
        "action": row.action,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "title": describe_action(row.action, row.object_type),
        "body": None,
        # 실패한 시도도 내 활동이다(로그인 실패·비밀번호 오답). 숨기면 "내가 안 했는데
        # 누가 시도했나"를 본인이 알아챌 유일한 창이 닫힌다.
        "result": row.result,
        "route": route_for(row.object_type, row.object_id),
        "read_at": None,
    }


def _notification_item(row: Notification) -> dict:
    return {
        "id": "noti:" + row.id,
        "kind": KIND_HAPPENED,
        "at": row.created_at.isoformat(),
        "action": row.type,
        "object_type": row.related_object_type,
        "object_id": row.related_object_id,
        "title": row.title,
        "body": row.body,
        "result": "success",
        "route": route_for(row.related_object_type, row.related_object_id),
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


def build_feed(
    db: Session, user_id: str, *, kind: str | None = None, offset: int = 0, limit: int = 20,
    order: str | None = None,
) -> dict:
    """두 원천을 합쳐 시간순으로 자른다.

    각 원천에서 `offset + limit` 건만 읽는다 — 합친 뒤 자를 것이므로 그보다 더 읽어도
    결과가 달라지지 않고, 무제한으로 읽으면 오래 쓴 계정에서 응답이 통째로 커진다.
    `total` 은 정확한 합계다(개수는 따로 센다) — 목록은 잘려도 "몇 건인지"는 진실이어야
    한다(app/home/aggregate.py 의 bucket 과 같은 규칙).

    🔴 **정렬 축이 시간 하나뿐인 이유.** 이 목록은 SQL 이 아니라 두 원천의 파이썬 병합이다.
    다른 키로 정렬하려면 각 원천의 읽기 창(`offset + limit`)이 그 키를 기준으로 잘려야 하는데,
    두 표에 그런 공통 키가 없다 — 억지로 만들면 「읽어 온 범위 안에서만 맞는 정렬」이 되고
    그것은 정렬이 아니라 착시다. 그래서 `sort` 키는 안 만들고 **방향만** 받는다. 방향을 뒤집을
    때는 **두 원천의 `order_by` 를 함께** 뒤집는다 — 한쪽만 뒤집으면 읽기 창이 서로 다른
    구간을 집어 합친 결과가 어느 쪽도 아니게 된다.
    """
    asc = (order or "desc") == "asc"
    take = max(offset + limit, 1)
    items: list[dict] = []
    total = 0

    if kind in (None, "", KIND_DID):
        rows = (
            db.execute(
                select(AuditLog)
                .where(AuditLog.user_id == user_id)
                .order_by(
                    AuditLog.created_at.asc() if asc else AuditLog.created_at.desc(),
                    AuditLog.id.asc() if asc else AuditLog.id.desc(),
                )
                .limit(take)
            ).scalars().all()
        )
        items.extend(_audit_item(r) for r in rows)
        total += _count(db, AuditLog, AuditLog.user_id == user_id)

    if kind in (None, "", KIND_HAPPENED):
        rows = (
            db.execute(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(
                    Notification.created_at.asc() if asc else Notification.created_at.desc(),
                    Notification.id.asc() if asc else Notification.id.desc(),
                )
                .limit(take)
            ).scalars().all()
        )
        items.extend(_notification_item(r) for r in rows)
        total += _count(db, Notification, Notification.user_id == user_id)

    # 같은 시각이면 id 로 안정 정렬한다 — 묶음을 이어 받을 때 항목이 왔다 갔다 하지 않게.
    # 이것이 이 목록의 전순서다(audit id 와 notification id 는 서로 겹치지 않는 UUID 공간이다).
    items.sort(key=lambda it: (it["at"], it["id"]), reverse=not asc)
    return {
        "items": items[offset:offset + limit],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def _count(db: Session, model, condition) -> int:
    from sqlalchemy import func

    return int(
        db.execute(select(func.count()).select_from(model).where(condition)).scalar_one()
    )
