/* 플랫폼 운영 — 백업·복원 리허설·공지·AI 쿼터·기능 플래그.
 *
 * 서비스 자체를 돌보는 화면들이다. 업무 데이터가 아니라 '이 설치'의 상태를 다룬다.
 *
 * registry.js 를 쪼갠 조각이다 (E-10). 쪼갠 축은 '줄 수'가 아니라 **관리자가 한 번에
 * 함께 보는 묶음**이다 — 줄 수를 맞추려고 아무 데나 자르면 화면 하나를 고치는 데
 * 파일 셋을 열게 되어 오히려 더 나빠진다.
 *
 * 화면 설정만 있고 그리는 코드는 없다. 그리는 것은 DataScreen.jsx 하나다.
 */
import React from "react";
import { Badge, WRITE_ROLES, activeCol, backupReasonText, badgeCol, col, dateCol, field, fmtBytes, fmtDateTime, mapCol, opt, personField, truncateCol, writerEmptyHelp } from "./shared.js";

export const PLATFORM_SCREENS = {
  backup: {
    key: "backup", area: "운영", title: "백업", endpoint: "/api/admin/backups",
    // 웹 콘솔에서 실행되는 이 백업은 단일 파일 스냅샷(var/exports/web-*.sqlite3)이며, 웹에서
    // 복원할 수 없고 rollback 스크립트의 입력도 아니다(system_admin이 '복원 안내'에서 상세를 볼 수
    // 있지만, 그 경고가 role 게이트된 모달 안에만 있어 다른 역할은 볼 방법이 없었다 — 항상 보이는
    // help로 옮겨 어떤 역할이 봐도 오해하지 않게 한다).
    // 이 목록이 최근 50건까지만 온다는 사실(app/backups/router.py list_backups의 .limit(50))이
    // 화면 어디에도 없었다 — 51번째 백업부터는 조용히 사라진다. 필터를 붙이기 전에 그 경계부터
    // 밝힌다(안 그러면 '필터에 안 걸림'과 '애초에 안 옴'을 구별할 수 없다).
    help: "데이터베이스를 백업합니다. 오래된 백업은 자동 정리됩니다. 이 목록은 웹 콘솔 DB 스냅샷입니다, 웹에서 복원할 수 없으며 서버의 rollback 스크립트 입력도 아닙니다. 복원은 시스템 관리자가 서버에서 별도 스크립트로만 수행합니다. 목록에는 최근 50건까지만 표시됩니다.",
    emptyTitle: "아직 백업이 없습니다",
    // 상태 필터가 하나도 없어 '실패한 백업만' 같은 질문에 답할 방법이 없었다. 이 엔드포인트는
    // 쿼리 파라미터를 받지 않고 페이지네이션도 하지 않는다(위 50건 상한이 전부) — 받아 온 것이
    // 곧 전부이므로 clientFilter로 걸러도 다른 페이지에 숨는 행이 생기지 않는다.
    // 검색도 대상 필드를 못박는다. 기본 검색은 JSON.stringify(row) 전체를 훑어 원시 UUID·체크섬·
    // UTC ISO 시각까지 매칭했다(화면에 보이지 않는 값으로 결과가 걸린다 — 부서/직책 화면과 같은 함정).
    filters: [{ key: "status", type: "select", label: "상태", clientFilter: true, options: opt([["verified", "확인됨"], ["succeeded", "성공"], ["failed", "실패"], ["running", "진행 중"]]) }],
    searchFields: ["path"],
    searchPlaceholder: "백업 파일 이름으로 검색",
    // 백업 프로세스가 도중에 죽으면(OOM-kill·systemd 재시작) 행이 status='running'인 채로 남고,
    // reap_stuck_running()이 다음 GET에서만 정리한다(app/backups/service.py, 60분 임계값) — 이미
    // 열어 둔 탭이 그 GET을 스스로 트리거하지 않으므로, 다른 화면들과 동일하게 진행 중 행이 있으면
    // 자동 새로고침해 그 전이를 화면이 따라가게 한다.
    pollWhile: (r) => r.status === "running",
    // 백업 실행·복원·검증은 모두 system_admin 전용(백엔드 RBAC). 그 외 역할에는 CTA 대신 읽기 전용 안내를 준다.
    emptyHelp: (role) => role === "system_admin"
      ? "‘+ 백업 실행’으로 지금 데이터베이스를 백업하세요. 오래된 백업은 자동 정리됩니다."
      : "아직 백업이 없습니다. 백업은 시스템 관리자가 실행할 수 있습니다.",
    // 첫 실행 시스템 관리자에게 단계별 안내를 준다(canOnboard가 primary 헤더 작업 '+ 백업 실행'을
    // 근거로 system_admin에만 보여준다). 다른 운영 화면(연동/러너)의 온보딩 패턴과 통일.
    emptySituation: "아직 데이터베이스 백업이 하나도 없습니다.",
    emptyPrerequisite: "백업은 웹 콘솔 DB 스냅샷입니다, 웹에서 복원할 수 없고 복원은 서버에서 별도 스크립트로만 수행합니다.",
    emptySteps: ["‘+ 백업 실행’으로 지금 스냅샷을 만듭니다.", "상태가 ‘확인됨(verified)’이 되는지 확인합니다.", "정기적으로 백업하는 습관을 들입니다(오래된 백업은 자동 정리됩니다)."],
    emptyExpected: "실행한 백업이 상태, 크기와 함께 목록에 남고, 최근의 정상 백업이 자동 보관됩니다.",
    headerActions: [
      { label: "복원 안내", method: "GET", roles: ["system_admin"], path: () => "/api/admin/backups/restore-instructions",
        // 웹 콘솔 스냅샷의 실제 복원법(web_snapshot_note)과 rollback 입력 규칙(rollback_input)까지 함께 보여준다.
        info: (res) => {
          const r0 = res || {};   // 빈/비-JSON 2xx면 api()가 null을 준다 — res.x 직접 접근은 throw
          const asText = (v) => v == null ? "" : (typeof v === "string" ? v : JSON.stringify(v, null, 2));
          const parts = [asText(r0.note), asText(r0.web_snapshot_note), asText(r0.rollback_input)].filter((x) => x);
          const steps = (r0.steps || []).map((s, i) => (i + 1) + ". " + s).join("\n");
          if (steps) parts.push(steps);
          return parts.join("\n\n");
        } },
      // primary:true → 백업이 하나도 없는 첫 실행 화면의 CTA가 '복원 안내'가 아니라 이 버튼이 된다(system_admin에게만).
      // 백업 실패 사유는 sqlite3 원시 예외 텍스트가 그대로 올 수 있다(app/backups/sqlite_backup.py) —
      // 알려진 사유 코드만 한국어로 치환해 영어가 그대로 새지 않게 한다(backupReasonText).
      { label: "+ 백업 실행", variant: "primary", primary: true, roles: ["system_admin"], path: () => "/api/admin/backups", confirm: "지금 데이터베이스 백업을 실행할까요?",
        result: (res) => { const s = res.backup && res.backup.status; const ok = s === "verified" || s === "succeeded"; return { ok, msg: ok ? "백업 완료" : ("백업 실패: " + backupReasonText((res.backup && res.backup.error_message) || "확인 실패")) }; } },
    ],
    // 경로는 파일명만 목록에 보이고(내부 배포 경로 노출·너비 낭비 방지), 전체 경로는 상세에서 본다.
    // SEM-01: 첫 열(생성 시각)이 dateCol(render 있음)이라 표식 없이는 전부 "상세 보기"였다 —
    // 파일명(아래 "파일" 열과 동일한 추출 로직)으로 실제로 구별되는 이름을 만든다.
    columns: [{ ...dateCol("created_at", "생성"), rowName: (r) => {
      const p = r.path;
      if (!p) return "백업 / " + fmtDateTime(r.created_at);
      const s = String(p);
      const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
      return i >= 0 ? s.slice(i + 1) : s;
    } }, badgeCol("status", "상태"), { key: "size_bytes", label: "크기", align: "right", render: (r) => fmtBytes(r.size_bytes) },
      { key: "path", label: "파일", render: (r) => { const p = r.path; if (p == null || p === "") return "-"; const s = String(p); const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\")); return i >= 0 ? s.slice(i + 1) : s; } }],
    // 목록 열은 파일명만 보여주고(위 columns "파일") 상세는 전체 경로를 보여준다 — 둘 다 실제로는
    // r.path를 읽지만 표시가 다르므로(파일명 vs 전체 경로), 새 드로어 중복 제거(key 기준, DataScreen.jsx
    // mergeDetailFields)가 이 상세 전용 항목을 columns의 "파일"과 같은 것으로 오인해 지우지 않도록
    // key를 다르게 둔다.
    // id는 감사 로그의 object_id(object_type=backup)와 대조할 때 필요한데, 템플릿·감사 기록 상세와
    // 달리 이 화면만 id를 어디에도 보여주지 않아 대조할 방법이 없었다.
    // backup_type은 현재 항상 "sqlite"뿐이지만(app/backups/models.py 하드코딩), 다른 상태 열(status)처럼
    // mapCol/badgeCol 대신 raw 값을 그대로 보여주고 있었다 — 미래에 두 번째 유형이 생겨도 번역 없는
    // 원문이 새지 않게 지금부터 작은 맵으로 감싼다.
    detailFields: [field("id", "백업 ID"), mapCol("backup_type", "유형", { sqlite: "SQLite" }), { key: "path_full", label: "전체 경로", render: (r) => r.path || "-" }, personField("created_by", "실행한 사람", "created_by_name", "created_by_email"), field("checksum", "체크섬"), dateCol("verified_at", "검증 시각"),
      { key: "error_message", label: "오류", render: (r) => r.error_message ? backupReasonText(r.error_message) : "-" }],
    // 검증 엔드포인트는 상태와 무관하게 어떤 backup id도 받아들인다(app/backups/router.py) — 예전엔
    // status===verified|succeeded일 때만 버튼을 보여줘서, 한 번 failed가 된 행은 재검증할 방법이
    // 영영 사라졌다(백엔드는 지원하는데 UI만 막고 있었다). 상태와 무관하게 항상 노출한다.
    actions: [
      // status==='running'인 동안은 백업 파일이 아직 쓰이는 중이고 체크섬도 null이다(app/backups/service.py
      // run_backup()) — 이 창에 '검증'을 누르면 expected_checksum=None이라 체크섬 비교를 건너뛰고
      // PRAGMA integrity_check만 돈다(app/backups/sqlite_backup.py). 완료된 백업에만 노출한다.
      { label: "검증", roles: ["system_admin"], when: (r) => r.status !== "running", path: (r) => "/api/admin/backups/" + r.id + "/verify",
        result: (res) => ({ ok: !!(res.verify && res.verify.ok), msg: (res.verify && res.verify.ok) ? "검증 완료: 정상" : "검증 실패: " + backupReasonText((res.verify && res.verify.reason) || "손상 가능성") }) },
      // operator는 백업 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=backup&object_id=" + r.id },
    ],
  },
  "restore-drills": {
    key: "restore-drills", area: "운영", title: "복구 리허설",
    endpoint: "/api/admin/backups/rehearsals",
    help: "백업은 복원해 본 적이 없으면 백업이 아닙니다. 리허설은 백업을 실제로 되돌려 무결성, 행 수, 스키마를 대조하고, 복원본으로 앱을 띄워 읽기 경로까지 확인합니다. 앱이 스스로 돌리지 않으므로(메모리를 두 배로 쓰기 때문) 서버에서 명령을 실행하면 결과가 여기에 남습니다. 목록에는 최근 20건까지만 표시됩니다.",
    // RG-06: 이 화면은 create도 primary headerAction도 없다(리허설은 웹 버튼이 아니라 서버
    // CLI로 돈다, 아래 emptySteps 참고) — DataScreen.jsx의 canOnboard 게이트가 그 둘만 보므로
    // 그대로 두면 situation/prerequisite/steps/expected 4종이 어떤 역할에서도 안 그려진다.
    // 화면 접근 자체는 이미 라우트 role 게이트로 걸려 있으니 안전하게 우회한다.
    forceOnboarding: true,
    emptyTitle: "복구 리허설 기록이 없습니다",
    emptyHelp: "아직 한 번도 복원을 시험하지 않았습니다. 아래 순서로 실행하면 결과가 이 목록에 남습니다.",
    emptySituation: "백업 파일은 쌓이는데, 그것으로 실제 복원이 되는지는 아무도 확인한 적이 없습니다.",
    emptyPrerequisite: "서버에 접속할 수 있어야 합니다(웹에서 실행하지 않습니다).",
    emptySteps: [
      "서버에서 scripts/restore_rehearsal.py --record 를 실행합니다.",
      "백업 → 검증 → 복원 → 무결성 → 행 수 대조 → 스키마 → 실제 부팅 순으로 7단계가 돕니다.",
      "끝나면 결과 한 줄이 이 목록에 남습니다(실패하면 실패한 단계도 함께).",
    ],
    emptyExpected: "‘마지막으로 복원을 시험한 게 언제인가’에 이 화면 하나로 답할 수 있게 됩니다.",
    emptyRelatedLink: { href: "#/backup", label: "백업 목록으로 이동" },
    // 이 화면이 답해야 하는 질문은 '언제 마지막으로 실패했나'인데, 필터가 하나도 없어
    // 통과한 기록 사이에서 실패를 눈으로 찾아야 했다. GET /api/admin/backups/rehearsals는
    // 쿼리 파라미터를 받지 않고 페이지네이션도 하지 않는다(app/backups/router.py
    // list_rehearsals) — 받아 온 것이 곧 전부라 clientFilter가 숨기는 행이 없다.
    // 다만 그 응답 자체가 최근 20건까지다(.limit(20)) — 그 경계는 help에 적었다.
    filters: [{ key: "ok", type: "select", label: "결과", clientFilter: true, options: opt([["true", "통과"], ["false", "실패"]]) }],
    // 기본 검색은 JSON.stringify(row) 전체를 훑는다 — 이 행에는 summary 객체와 ok 불리언이 들어
    // 있어서 '실패'를 찾으려고 true를 쳐 넣으면 통과한 기록이 전부 걸린다(화면에 없는 값으로
    // 결과가 걸리는, 부서/직책 화면에서 이미 한 번 고친 함정). 사람이 읽는 원본 라벨만 본다.
    searchFields: ["source_label"],
    searchPlaceholder: "원본 백업 이름으로 검색",
    summary: {
      endpoint: "/api/admin/backups/schedule",
      cards: (data) => {
        const s = (data && data.schedule) || {};
        const last = data && data.last_backup;
        const drill = data && data.last_rehearsal;
        return [
          { value: s.enabled ? s.cron : "꺼짐", label: s.enabled ? "자동 백업 (" + (s.timezone || "Asia/Seoul") + ")" : "자동 백업", kind: s.enabled ? "ok" : "warn" },
          { value: last ? fmtDateTime(last.created_at) : "없음", label: "마지막 백업", kind: last ? "ok" : "danger" },
          { value: drill ? (drill.ok ? "통과" : "실패") : "한 번도 안 함", label: "마지막 리허설", kind: drill ? (drill.ok ? "ok" : "danger") : "warn" },
          { value: s.keep == null ? "-" : String(s.keep), label: "보관 개수" },
        ];
      },
    },
    columns: [
      { key: "ok", label: "결과", render: (r) => React.createElement(Badge, { value: r.ok ? "통과" : "실패", kind: r.ok ? "ok" : "danger" }) },
      dateCol("started_at", "시작"), dateCol("finished_at", "종료"),
      { key: "_rows", label: "행 수", align: "right", render: (r) => (r.summary && r.summary.rows != null) ? String(r.summary.rows) : "-" },
      { key: "_head", label: "스키마", render: (r) => (r.summary && r.summary.alembic_head) || "-" },
      // SEM-01: 첫 열(결과 배지)이 render라 표식 없이는 전부 "상세 보기"였다 — 원본 백업
      // 이름(검색 대상과 동일한 필드) + 시작 시각으로 실제로 구별되는 이름을 만든다.
      { ...truncateCol("source_label", "원본", 50), rowName: (r) => (r.source_label || "리허설") + " / " + fmtDateTime(r.started_at) },
    ],
    detailFields: [
      field("id", "기록 ID"),
      { key: "failures", label: "실패한 단계", render: (r) => (r.failures || []).join(", ") || "없음" },
      { key: "_summary", label: "요약", render: (r) => JSON.stringify(r.summary || {}) },
    ],
    headerActions: [
      { label: "백업 목록", navigate: () => "#/backup" },
      { label: "백업 일정 설정", roles: WRITE_ROLES, navigate: () => "#/settings" },
    ],
  },
  announcements: {
    key: "announcements", area: "운영", title: "공지 배너",
    endpoint: "/api/admin/announcements",
    help: "모든 화면 위쪽에 띠로 뜨는 공지입니다. 사용자가 닫으면 그 사람에게는 다시 뜨지 않습니다(브라우저가 아니라 계정에 기록되므로 다른 PC에서도 닫힌 상태가 유지됩니다).",
    emptyTitle: "등록된 공지가 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 공지 추가’로 점검 예고나 안내를 띄우세요.", "공지는 관리자가 등록합니다."),
    emptySituation: "점검이나 장애를 알릴 곳이 알림 벨밖에 없었습니다(놓치기 쉽습니다).",
    emptySteps: ["‘+ 공지 추가’로 제목과 내용을 적습니다.", "필요하면 노출 기간을 정합니다(비우면 끌 때까지 계속).", "‘사용 안 함’으로 바꾸면 즉시 내려갑니다."],
    emptyExpected: "활성 공지는 모든 화면 위쪽에 띠로 뜨고, 사용자가 닫으면 그 계정에는 다시 뜨지 않습니다.",
    createLabel: "+ 공지 추가",
    paginated: true,
    searchFields: ["title", "body"],
    searchPlaceholder: "제목, 내용으로 검색",
    filters: [
      { key: "active", type: "select", label: "사용", options: opt([["true", "사용"], ["false", "사용 안 함"]]) },
      { key: "level", type: "select", label: "중요도", options: opt([["info", "안내"], ["warning", "주의"], ["critical", "긴급"]]) },
    ],
    columns: [
      col("title", "제목"),
      { key: "level", label: "중요도", render: (r) => React.createElement(Badge, {
        value: ({ info: "안내", warning: "주의", critical: "긴급" })[r.level] || r.level,
        kind: r.level === "critical" ? "danger" : r.level === "warning" ? "warn" : "info",
      }) },
      mapCol("audience", "대상", { all: "모든 사용자", admin: "관리자군에게만" }),
      activeCol("사용"),
      dateCol("starts_at", "시작"), dateCol("ends_at", "종료"),
    ],
    detailFields: [field("id", "공지 ID"), field("body", "내용"),
      { key: "dismissible", label: "닫기 허용", render: (r) => r.dismissible ? "닫을 수 있음" : "닫을 수 없음(기간이 끝나야 사라짐)" },
      field("link_url", "링크 주소"), field("link_label", "링크 문구"), dateCol("created_at", "등록")],
    create: { roles: WRITE_ROLES, fields: [
      { name: "title", label: "제목", type: "text", required: true },
      { name: "body", label: "내용", type: "textarea" },
      { name: "level", label: "중요도", type: "select", value: "info", options: opt([["info", "안내"], ["warning", "주의"], ["critical", "긴급"]]) },
      { name: "audience", label: "대상", type: "select", value: "all", options: opt([["all", "모든 사용자"], ["admin", "관리자군에게만(운영자 이상)"]]) },
      { name: "starts_at", label: "노출 시작(선택)", type: "datetime-local", help: "비우면 즉시 노출됩니다." },
      { name: "ends_at", label: "노출 종료(선택)", type: "datetime-local", help: "비우면 ‘사용 안 함’으로 바꿀 때까지 계속 노출됩니다." },
      { name: "dismissible", label: "닫기 허용", type: "checkbox", value: true, checkLabel: "사용자가 닫을 수 있음", help: "끄면 닫기 버튼이 없습니다. 그런 공지는 반드시 종료 시각을 정하세요." },
      { name: "link_url", label: "링크 주소(선택)", type: "text" },
      { name: "link_label", label: "링크 문구(선택)", type: "text" },
      { name: "active", label: "사용", type: "checkbox", value: true, checkLabel: "지금 사용" },
    ] },
    editMethod: "PATCH",
    edit: { roles: WRITE_ROLES, fields: [
      { name: "title", label: "제목", type: "text", required: true },
      { name: "body", label: "내용", type: "textarea" },
      { name: "level", label: "중요도", type: "select", options: opt([["info", "안내"], ["warning", "주의"], ["critical", "긴급"]]) },
      { name: "audience", label: "대상", type: "select", options: opt([["all", "모든 사용자"], ["admin", "관리자군에게만(운영자 이상)"]]) },
      { name: "starts_at", label: "노출 시작(선택)", type: "datetime-local" },
      { name: "ends_at", label: "노출 종료(선택)", type: "datetime-local" },
      { name: "dismissible", label: "닫기 허용", type: "checkbox", checkLabel: "사용자가 닫을 수 있음" },
      { name: "link_url", label: "링크 주소(선택)", type: "text" },
      { name: "link_label", label: "링크 문구(선택)", type: "text" },
      { name: "active", label: "사용", type: "checkbox", checkLabel: "지금 사용" },
    ] },
    actions: [
      { label: "사용", roles: WRITE_ROLES, when: (r) => !r.active, method: "PATCH", path: (r) => "/api/admin/announcements/" + r.id, body: { active: true } },
      { label: "사용 안 함", roles: WRITE_ROLES, when: (r) => r.active, method: "PATCH", path: (r) => "/api/admin/announcements/" + r.id, body: { active: false }, confirm: "이 공지를 내릴까요? 모든 화면에서 즉시 사라집니다." },
      { label: "삭제", variant: "danger", roles: WRITE_ROLES, method: "DELETE", path: (r) => "/api/admin/announcements/" + r.id, confirm: "이 공지를 지울까요? 되돌릴 수 없습니다(닫음 기록도 함께 의미를 잃습니다)." },
      // announcement은 감사 로그의 유효한 object_type이고(app/announcements/router.py) 이제
      // OBJ_ROUTE에도 있다 — 조직·기능 플래그와 동일한 딥링크를 추가한다(MEGA CYCLE G).
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=announcement&object_id=" + r.id },
    ],
  },
  "ai-quotas": {
    key: "ai-quotas", area: "자동화", title: "AI 사용 상한",
    endpoint: "/api/admin/ai-quotas",
    help: "AI 호출을 사용자, 기간별로 제한합니다. 상한이 걸리는 곳은 아래 표 위의 ‘상한이 걸리는 곳’ 목록에 서버가 직접 알려 줍니다. 사용자별 상한이 전체 상한보다 우선하고, 상한 행이 하나도 없으면 제한이 없습니다. 취소되거나 실패한 호출은 세지 않습니다. 위 요약 카드는 조직 전체 합계이고, 아래 표의 ‘현재 사용’은 그 행(전체 범위면 가장 많이 쓴 사람 1인, 사용자 범위면 그 1인)의 값입니다. 두 숫자는 서로 다른 것을 셉니다.",
    emptyTitle: "설정된 상한이 없습니다",
    emptyHelp: writerEmptyHelp("‘+ 상한 추가’로 하루 또는 한 달 상한을 정하세요. 아무것도 없으면 제한이 없습니다.", "상한은 관리자가 설정합니다."),
    emptySituation: "AI 호출 비용에 상한이 없어, 한 사람이 많이 써도 알아챌 방법이 없습니다.",
    emptySteps: ["‘+ 상한 추가’에서 ‘전체’ 범위로 하루 상한을 정합니다.", "특정 사용자만 늘리거나 줄이려면 ‘사용자’ 범위로 한 줄 더 만듭니다.", "목록의 ‘현재 사용’ 열로 소비 상황을 확인합니다."],
    emptyExpected: "상한에 도달하면 그 사용자의 AI 요청이 거절되고, 언제 풀리는지 안내됩니다.",
    createLabel: "+ 상한 추가",
    // 필터가 하나도 없어 사용자별 상한이 쌓이면 '한 달 상한만' 같은 질문에 답할 방법이 없었다.
    // GET /api/admin/ai-quotas는 쿼리 파라미터를 받지 않고 페이지네이션도 하지 않는다
    // (app/quotas/router.py list_quotas — 전체를 한 번에 돌려준다). 받아 온 것이 곧 전부이므로
    // clientFilter가 숨기는 행은 없다. 대상 사람 이름은 clientFilter로 다룰 수 없어(정확 일치
    // 비교라 이름 일부로는 못 찾는다) 검색창에 맡긴다 — 그 검색도 대상 필드를 못박는다.
    filters: [
      { key: "scope_type", type: "select", label: "범위", clientFilter: true, options: opt([["global", "전체"], ["user", "사용자"]]) },
      { key: "period", type: "select", label: "기간", clientFilter: true, options: opt([["day", "하루"], ["month", "한 달"]]) },
    ],
    searchFields: ["user_name", "user_email", "note"],
    searchPlaceholder: "대상 이름, 이메일, 메모로 검색",
    // FN-05 — GET /ai-quotas/usage(app/quotas/router.py)는 처음부터 있었는데 부르는 화면이
    // 없어 죽어 있었다(UB-25와 같은 결함). 아래 행별 "현재 사용" 열은 최다 사용자 1인 또는
    // 특정 사용자 1인의 값이라 "오늘 전체 몇 번 썼나"에는 답을 못한다 — 그건 이 요약 카드가
    // 준다(같은 화면 안에 서로 다른 두 숫자가 있다는 것을 help 문구에도 적어 둔다).
    summary: {
      endpoint: "/api/admin/ai-quotas/usage",
      cards: (data) => {
        const periods = (data && data.periods) || [];
        const day = periods.find((p) => p.period === "day");
        const month = periods.find((p) => p.period === "month");
        return [
          { value: day ? String(day.used) : "-", label: "오늘 전체 AI 호출" },
          { value: month ? String(month.used) : "-", label: "이번 달 전체 AI 호출" },
        ];
      },
    },
    columns: [
      mapCol("scope_type", "범위", { global: "전체", user: "사용자" }),
      // SEM-01: 첫 열(범위)이 mapCol(render 있음)이라 표식 없이는 같은 범위(대부분 "사용자")끼리
      // 전부 "상세 보기"로 동일했다 — 대상 + 기간을 합쳐 실제로 구별되는 이름을 만든다.
      { key: "user_name", label: "대상", render: (r) => r.scope_type === "global" ? "(전체)" : (r.user_name || r.user_id || "-"), rowName: (r) => (r.scope_type === "global" ? "전체" : (r.user_name || r.user_id || "-")) + " / " + ({ day: "하루", month: "한 달" }[r.period] || r.period) },
      mapCol("period", "기간", { day: "하루", month: "한 달" }),
      { key: "max_calls", label: "상한", align: "right" },
      { key: "used", label: "현재 사용", align: "right", render: (r) => (r.used == null ? "-" : r.used + " / " + r.max_calls + (r.scope_type === "global" ? " (최다 사용자 기준)" : "")) },
      dateCol("resets_at", "초기화"),
    ],
    detailFields: [field("id", "상한 ID"), field("user_email", "대상 이메일"), field("note", "메모"),
      dateCol("created_at", "등록"), dateCol("updated_at", "수정"),
      { key: "_over", label: "상태", render: (r) => (r.used != null && r.used >= r.max_calls) ? "상한에 도달했습니다. 이 대상의 AI 요청이 지금 거절됩니다." : "여유가 있습니다." }],
    create: { roles: WRITE_ROLES, fields: [
      { name: "scope_type", label: "범위", type: "select", value: "global", required: true, options: opt([["global", "전체"], ["user", "사용자"]]) },
      { name: "user_id", label: "사용자 ID", type: "text", showIf: (v) => v.scope_type === "user", help: "‘사용자’ 화면에서 ID를 복사해 붙여 넣으세요." },
      { name: "period", label: "기간", type: "select", value: "day", required: true, options: opt([["day", "하루"], ["month", "한 달"]]) },
      { name: "max_calls", label: "상한(횟수)", type: "number", required: true, help: "0이면 차단입니다(무제한이 아닙니다). 무제한으로 두려면 이 줄을 지우세요. 기간 경계는 한국 시간 기준입니다." },
      { name: "note", label: "메모", type: "text" },
    ] },
    editMethod: "PATCH",
    edit: { roles: WRITE_ROLES, fields: [
      { name: "max_calls", label: "상한(횟수)", type: "number", required: true },
      { name: "note", label: "메모", type: "text" },
    ] },
    actions: [
      { label: "삭제", variant: "danger", roles: WRITE_ROLES, method: "DELETE", path: (r) => "/api/admin/ai-quotas/" + r.id, confirm: "이 상한을 지울까요? 지우면 이 범위, 기간에는 제한이 없어집니다." },
      // ai_quota는 감사 로그의 유효한 object_type이고(app/quotas/router.py) 이제 OBJ_ROUTE에도
      // 있다 — 조직·기능 플래그와 동일한 딥링크를 추가한다(MEGA CYCLE G).
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=ai_quota&object_id=" + r.id },
    ],
  },
  "feature-flags": {
    key: "feature-flags", area: "운영", title: "기능 플래그",
    endpoint: "/api/admin/feature-flags",
    help: "모듈을 켜고 끄는 스위치입니다. ‘파일’ 소유 플래그는 여기서 바꾸면 재시작 없이 즉시 반영됩니다. ‘설정 화면’ 소유 플래그는 여기서 바꿀 수 없습니다. 값의 주인이 한 곳이어야 하기 때문입니다(‘설정’ 화면에서 바꾸세요).",
    emptyTitle: "플래그 정의를 불러오지 못했습니다",
    searchFields: ["name", "description"],
    searchPlaceholder: "플래그 이름으로 검색",
    filters: [{ key: "owner", type: "select", label: "값의 주인", clientFilter: true, options: opt([["file", "파일(여기서 변경)"], ["db", "설정 화면"]]) }],
    columns: [
      col("name", "플래그"),
      { key: "value", label: "현재", render: (r) => React.createElement(Badge, { value: r.value ? "켜짐" : "꺼짐", kind: r.value ? "ok" : "neutral" }) },
      mapCol("owner", "값의 주인", { file: "파일", db: "설정 화면" }),
      { key: "has_consumer", label: "실제 효과", render: (r) => r.has_consumer ? "있음" : "없음(읽는 코드 없음)" },
      truncateCol("description", "설명", 70),
    ],
    // description은 이미 목록 열이지만 그 열은 truncateCol(70자 말줄임, hover title로만 전체 확인)이다
    // — 같은 key로 다시 넣으면 mergeDetailFields가 columns 쪽(자른 버전)만 남기고 이 평문 버전은
    // 조용히 버려져(상세 드로어의 원래 목적인 '전체 설명 확인'이 실제로는 절대 렌더되지 않는다) —
    // audit 화면의 object_id_full/backup 화면의 path_full과 동일한 패턴으로 별도 key를 쓴다.
    detailFields: [
      { key: "description_full", label: "설명", render: (r) => r.description || "-" }, field("edit_hint", "변경 안내"),
      { key: "default", label: "기본값", render: (r) => r.default ? "켜짐" : "꺼짐" },
      { key: "_no_consumer", label: "주의", render: (r) => r.has_consumer ? "-" : "이 플래그를 읽는 코드가 아직 없습니다. 켜거나 꺼도 동작이 달라지지 않습니다." },
    ],
    actions: [
      { label: "켜기", variant: "primary", roles: WRITE_ROLES, when: (r) => r.editable_here && !r.value,
        method: "PUT", path: (r) => "/api/admin/feature-flags/" + encodeURIComponent(r.name), body: { enabled: true },
        confirm: (r) => r.name + " 플래그를 켤까요? 재시작 없이 즉시 반영됩니다." },
      { label: "끄기", variant: "danger", roles: WRITE_ROLES, when: (r) => r.editable_here && r.value,
        method: "PUT", path: (r) => "/api/admin/feature-flags/" + encodeURIComponent(r.name), body: { enabled: false },
        confirm: (r) => r.name + " 플래그를 끌까요? 이 기능을 쓰는 화면이 즉시 사라지거나 요청이 거절됩니다." },
      { label: "설정 화면에서 열기", when: (r) => !r.editable_here, navigate: () => "#/settings" },
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=feature_flag&object_id=" + encodeURIComponent(r.name) },
    ],
  },
};
