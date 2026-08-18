/* 스스로 도는 것들 — 예약 실행·문서 생성·작업 큐.
 *
 * 공통점은 '사람이 누르지 않아도 서버가 하는 일'이다. 셋 다 실행 이력과 실패 사유를 같은
 * 방식으로 보여주고, 진행 중인 행이 있으면 목록을 폴링한다.
 *
 * registry.js 를 쪼갠 조각이다 (E-10). 쪼갠 축은 '줄 수'가 아니라 **관리자가 한 번에
 * 함께 보는 묶음**이다 — 줄 수를 맞추려고 아무 데나 자르면 화면 하나를 고치는 데
 * 파일 셋을 열게 되어 오히려 더 나빠진다.
 *
 * 화면 설정만 있고 그리는 코드는 없다. 그리는 것은 DataScreen.jsx 하나다.
 */
import React from "react";
import Link from "@mui/material/Link";
import { CONCURRENCY_OPTS, DOC_MODE, JOB_TYPE, MISFIRE_OPTS, OPS_ROLES, SCHEDT_OPTS, SCHED_PRESET_OPTS, SCHED_RUN, SCHED_TARGET_OPTS, SCHED_TYPE, WRITE_ROLES, badgeCol, col, dateCol, enabledCol, field, fmtDateTime, jsonField, linkCol, listField, mapCol, opt, personField, previewField, schedSkipReasonText } from "./shared.js";
import { DOC_GENERATE_FIELDS, docConfigInitial, docConfigTransform, docGenerateResult, onoff } from "./actions.js";

export const AUTOMATION_SCREENS = {
  schedules: {
    key: "schedules", area: "자동화", title: "실행 일정", endpoint: "/api/admin/schedules",
    help: "정해진 시간에 자동 실행을 예약합니다.",
    emptyTitle: "예약된 일정이 없습니다",
    // 문서 화면의 '정기 실행으로 예약'에서 넘어온 ?workflow_id= 쿼리를 생성 폼 프리필로 소비한다
    // (템플릿 → 문서 생성 프리필과 동일한 onQuery 패턴). 대상 유형은 워크플로로 고정해 시작한다.
    // ?id=는 다른 화면(승인의 '대상 보기' 등)이 특정 스케줄로 딥링크할 때 쓴다 — runners.onQuery와
    // 동일한 패턴으로 그 스케줄의 상세 드로어를 곧바로 연다.
    onQuery: (p) => p.id
      ? { open: "select", id: p.id }
      : (p.workflow_id ? { open: "create", initial: { target_type: "workflow", target_ref: p.workflow_id } } : null),
    selectKey: "schedule",
    // USE-04/SCHD-02: create/edit의 target_ref select가 쓴다(DataScreen.jsx의 refListOptions).
    refLists: [{ key: "workflows", endpoint: "/api/admin/workflows" }],
    // 생성 권한이 없는 역할(operator/auditor)에게는 없는 버튼('+ 스케줄 추가')을 누르라고 안내하지 않는다(백업·문서 화면과 동일 패턴).
    emptyHelp: (role) => (role === "admin" || role === "system_admin")
      ? "‘+ 스케줄 추가’로 Cron 또는 1회 실행 일정을 추가해 워크플로를 자동 실행하세요."
      : "실행 일정은 관리자가 추가합니다. 추가되면 예약과 다음 실행 시각이 여기에 표시됩니다.",
    createLabel: "+ 스케줄 추가",
    // list_schedules(app/schedules/router.py)는 쿼리 파라미터를 전혀 받지 않는다(항상 전체 목록) —
    // clientFilter:true로 이미 받아 온 목록을 화면에서 직접 거른다(workflows.filters와 동일 패턴).
    // 스케줄은 삭제/보관 엔드포인트가 없어 비활성·완료된 once형도 계속 목록에 남으므로, 활성만
    // 보고 싶을 때 걸러낼 방법이 지금까지 없었다.
    filters: [
      { key: "enabled", type: "select", label: "활성", clientFilter: true, options: opt([["true", "활성"], ["false", "비활성"]]) },
      { key: "schedule_type", type: "select", label: "유형", clientFilter: true, options: SCHEDT_OPTS },
      { key: "target_type", type: "select", label: "대상 유형", clientFilter: true, options: SCHED_TARGET_OPTS },
    ],
    // 1회(once) 일정은 Cron 식이 없다 → 빈 칸 대신 유형 라벨을 보여준다(실제 실행 시각은 '다음 실행' 열).
    // target_type/target_ref도 목록 열로 노출 — 이 일정이 실제로 무엇을 실행하는지(어느 워크플로/
    // 시스템)가 예전엔 상세를 하나씩 열어야만 보였다. target_ref는 대상이 워크플로일 때 그 화면으로
    // 바로 이동하는 링크로 보여준다(러너 상세의 integration_id와 동일한 패턴).
    columns: [{ ...col("name", "이름"), identifier: true }, mapCol("schedule_type", "유형", SCHED_TYPE),
      { key: "cron_expression", label: "실행 일정(Cron)", render: (r) => r.schedule_type === "once" ? "1회 실행(‘다음 실행’ 참고)" : (r.cron_expression == null || r.cron_expression === "" ? "-" : String(r.cron_expression)) },
      mapCol("target_type", "대상 유형", { workflow: "워크플로", system: "시스템" }),
      // 워크플로 화면의 ?id= 딥링크(onQuery)로 그 워크플로 상세를 곧바로 연다(무필터 전체 목록 아님).
      // USE-04: 서버가 target_name을 함께 준다(app/schedules/router.py _view) — 원시 UUID 대신
      // 이름을 보여주고, id는 계속 옆에 남긴다(다른 이름-해석 열과 같은 관용, personField 참고).
      { key: "target_ref", label: "대상", render: (r) => (r.target_ref && r.target_type === "workflow")
        ? React.createElement(Link, { underline: "hover", href: "#/workflows?id=" + encodeURIComponent(r.target_ref) }, r.target_name || r.target_ref)
        : (r.target_ref || "-") },
      enabledCol("활성"),
      // 비활성화(disable_schedule)는 next_run_at을 지우지 않는다(백엔드가 enabled만 끈다) — 그대로
      // 보여주면 '이 시각에 다시 실행될 것'처럼 읽힌다. 비활성 행은 활성 배지로 알 수 있으니 이 열은
      // 무의미한 미래 시각 대신 '-'로 지워 이중 확인을 강제하지 않는다.
      { key: "next_run_at", label: "다음 실행", render: (r) => r.enabled ? fmtDateTime(r.next_run_at) : "-" },
      dateCol("last_run_at", "마지막 실행"),
      // 백엔드가 now > end_at이면 cron 일정을 자동 비활성화한다(scheduler.py advance_next_run) —
      // 상세를 하나씩 열지 않고도 곧 만료될 일정을 목록에서 바로 훑을 수 있게 노출한다.
      dateCol("end_at", "유효 기간(종료)")],
    // 관리자(비-system_admin)가 활성 스케줄의 정의를 바꾸면 백엔드가 재승인 위해 자동 비활성화한다 → 저장 후 경고.
    onSaved: (res, { toast, prev }) => {
      const s = res && res.schedule;
      if (prev && prev.enabled && s && s.enabled === false) {
        toast("저장했지만 정의 변경으로 비활성화되었습니다. 다시 활성화(승인)해야 실행됩니다.", "error");
        return true;
      }
      return false;
    },
    create: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "description", label: "설명", type: "text" },
      { name: "schedule_type", label: "유형", type: "select", value: "cron", options: SCHEDT_OPTS },
      { name: "preset", label: "간편 주기(선택)", type: "select", value: "", options: SCHED_PRESET_OPTS, help: "고르면 Cron 식이 자동 생성됩니다. ‘사용 안 함’이면 아래 Cron 식/실행 시각을 직접 입력하세요." },
      // 이 폼은 유형(cron/once)에 따른 조건부 표시가 없다 — 두 필드가 항상 함께 보이므로, 각각 어느
      // 유형에서만 쓰이는지 help로 명시해 반대 유형의 값을 채우고 무시되는 걸 모르는 일을 줄인다.
      { name: "cron_expression", label: "Cron 식", type: "text", help: "예: 0 9 * * 1 (매주 월 09:00). 간편 주기를 골랐으면 비워도 됩니다. (유형이 ‘1회 실행’이면 이 값은 쓰이지 않습니다.)" },
      { name: "run_at", label: "실행 시각(1회형, ISO)", type: "text", help: "예: 2026-08-01T09:00:00+09:00, 시간대 표기가 없으면 UTC로 해석됩니다(KST면 +09:00을 붙이세요). (유형이 ‘Cron 반복’이면 이 값은 쓰이지 않습니다.)" },
      { name: "timezone", label: "시간대", type: "text", value: "Asia/Seoul", help: "Cron 평가에 쓰이는 시간대(run_at에는 적용되지 않음)." },
      { name: "target_type", label: "대상 유형", type: "select", value: "workflow", options: SCHED_TARGET_OPTS },
      // USE-04/SCHD-02: 워크플로 UUID를 손으로 옮겨 적던 것을 이름으로 고르게 한다(refLists,
      // 아래 참고). '대상 유형'을 '시스템'으로 바꿔도 고를 수 있게 유일한 시스템 값(noop)을
      // 같은 목록 끝에 얹는다 — 두 필드를 서로 맞춰 조건부로 보여주는 것보다 단순하다.
      { name: "target_ref", label: "대상", type: "select", required: true, optionsFromRefList: "workflows",
        extraOptions: [{ value: "noop", label: "시스템 (noop)" }],
        help: "‘대상 유형’이 워크플로면 여기서 워크플로를 고르세요(승인 필요 없음으로 설정된 것만 실제 실행됩니다). 시스템이면 목록 끝의 ‘시스템 (noop)’을 고르세요." },
      { name: "payload_template", label: "실행 페이로드(JSON)", type: "json", help: "워크플로에 보낼 기본 페이로드. 비우면 빈 값으로 실행됩니다." },
      { name: "retry_policy", label: "재시도 정책(JSON)", type: "json", help: '예: {"max_attempts": 3}, 일시 오류 시 최대 재시도 횟수(1~10, 기본 3). app/schedules/scheduler.py가 이 값으로 재시도/백오프를 결정합니다.' },
      // 기본값을 명시하지 않으면 FormModal이 null을 보내 백엔드(non-Optional str)가 422로 거절한다
      // → 모든 기본 경로 스케줄 생성이 실패했다. 백엔드 기본값(skip)과 맞춘다.
      { name: "misfire_policy", label: "누락 처리 정책", type: "select", value: "skip", options: MISFIRE_OPTS },
      { name: "concurrency_policy", label: "동시 실행 정책", type: "select", value: "skip", options: CONCURRENCY_OPTS },
      { name: "timeout_seconds", label: "타임아웃(초)", type: "number" },
      { name: "start_at", label: "시작 시각(ISO, 선택)", type: "text", help: "유효 기간의 시작. 예: 2026-08-01T00:00:00+09:00" },
      { name: "end_at", label: "종료 시각(ISO, 선택)", type: "text", help: "유효 기간의 끝. 예: 2026-12-31T23:59:59+09:00" },
    ] },
    // target_type·target_ref는 이제 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    // end_at은 이제 목록 열이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    // 목록의 '다음 실행' 열은 비활성 행에서 '-'로 지워지므로(무의미한 미래 시각 오해 방지), 비활성
    // once형이 언제 실행 예정인지 수정 폼을 열지 않고는 볼 수 없었다 — 상세에서는 활성 여부와
    // 무관하게 예정 시각을 보여준다(비활성이면 라벨로 명시). 목록 열과 key가 겹치지 않게 별도 key.
    // 스케줄 ID 는 남긴다 — 감사 로그 필터(object_type=schedule)에 붙여 넣는 값이다.
    // 소유자는 서버가 이름을 함께 준다(app/schedules/router.py `_view`) — UUID 대신 그 이름을 쓴다.
    detailFields: [field("id", "스케줄 ID"), personField("owner_user_id", "소유자", "owner_name", "owner_email"),
      { key: "_next_run_scheduled", label: "다음 실행(예정)", render: (r) => r.next_run_at ? fmtDateTime(r.next_run_at) + (r.enabled ? "" : " (현재 비활성)") : "-" },
      field("description", "설명"), field("timezone", "시간대"), mapCol("misfire_policy", "누락 처리 정책", { skip: "건너뛰기", run_once: "한 번만 실행" }), mapCol("concurrency_policy", "동시 실행 정책", { skip: "건너뛰기", allow: "동시 실행 허용" }), field("timeout_seconds", "타임아웃(초)"), dateCol("start_at", "시작 시각"), dateCol("created_at", "추가"), jsonField("payload_template", "실행 페이로드"), jsonField("retry_policy", "재시도 정책")],
    actions: [
      // once형은 백엔드 enable이 실행 시각이 이미 지났으면 항상 409('실행 시각이 이미 지났습니다')로
      // 거절한다 — 눌러도 항상 실패하는 '활성화'를 숨긴다. next_run_at이 아예 없거나(이미 실행됨),
      // 있어도 그 시각이 이미 과거면(비활성인 채 run_at이 지나감) 둘 다 숨긴다('수정'으로 새 run_at
      // 지정 후에만 다시 노출). cron형은 그대로 노출한다.
      ...onoff("/api/admin/schedules", undefined, (r) => {
        if (r.schedule_type !== "once") return true;
        if (!r.next_run_at) return false;
        const s = String(r.next_run_at); const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
        const t = new Date(iso).getTime();
        return Number.isNaN(t) ? true : t > Date.now();
      }),
      // run-now는 비동기로 큐잉될 뿐이라 이 토스트 이후 결과를 알 방법이 없었다(목록엔 자동 갱신도
      // 상태 열도 없다) — 최소한 어디서 결과를 확인할지 명확히 안내한다.
      { label: "지금 실행", roles: OPS_ROLES, when: (r) => r.enabled, path: (r) => "/api/admin/schedules/" + r.id + "/run-now", confirm: "이 일정을 지금 한 번 실행할까요?",
        result: (res) => ({ ok: true, msg: (res.deduplicated ? "이미 실행 중이라 중복 실행을 건너뛰었습니다." : "실행을 시작했습니다(비동기).") + " 결과는 ‘실행 이력’에서 확인하세요." }) },
      // 미리보기: 다음 실행 시각뿐 아니라 '실제로 보낼 페이로드'와 대상까지 안내 모달로 보여준다.
      { label: "미리보기", roles: OPS_ROLES, path: (r) => "/api/admin/schedules/" + r.id + "/dry-run",
        info: (res) => {
          const r0 = res || {};   // 빈/비-JSON 2xx면 api()가 null을 준다 — res.x 직접 접근은 throw
          const t = (r0.next_fire_times_utc || []).slice(0, 5).map(fmtDateTime);
          const lines = [];
          lines.push("다음 실행 예정:\n" + (t.length ? t.map((x) => ", " + x).join("\n") : "  (예정된 실행 시각 없음)"));
          if (r0.target_type || r0.target_ref) lines.push("\n대상: " + (r0.target_type || "?") + " / " + (r0.target_ref || "?"));
          const pp = r0.payload_preview;
          lines.push("\n보낼 페이로드:\n" + (pp == null ? "  (없음)" : (typeof pp === "string" ? pp : JSON.stringify(pp, null, 2))));
          return lines.join("\n");
        } },
      { label: "실행 이력", subList: {
        title: "스케줄 실행 이력",
        paginated: true,
        filters: [{ key: "status", type: "select", label: "결과", options: opt([["failed", "실패"], ["succeeded", "성공"], ["running", "실행 중"], ["queued", "대기"], ["skipped", "건너뜀"]]) }],
        endpoint: (r, p) => "/api/admin/schedules/" + r.id + "/runs?page=" + ((p && p.page) || 1) + (p && p.filters && p.filters.status ? "&status=" + encodeURIComponent(p.filters.status) : ""),
        // _run_view가 request_payload(실제로 보낸 값)도 돌려주는데 목록엔 전혀 없었다 — 실패 원인
        // 진단의 핵심 두 값(보낸 것/받은 것) 중 하나가 아예 안 보였다. 둘 다 진단용 요약으로 노출한다.
        columns: [dateCol("scheduled_at", "예정"), mapCol("status", "결과", SCHED_RUN), dateCol("started_at", "시작"), dateCol("finished_at", "종료"), col("retry_count", "재시도"),
          { key: "request_payload", label: "보낸 페이로드", render: (r) => { const v = r.request_payload; if (v == null || v === "" || (typeof v === "object" && !Object.keys(v).length)) return "-"; const s = typeof v === "string" ? v : JSON.stringify(v); return s.length > 60 ? s.slice(0, 60) + "…" : s; } },
          { key: "response_summary", label: "응답 요약", render: (r) => { const v = r.response_summary; if (v == null || v === "") return "-"; const s = typeof v === "string" ? v : JSON.stringify(v); return s.length > 60 ? s.slice(0, 60) + "…" : s; } },
          // 건너뛴 실행(_record_skip, app/schedules/scheduler.py)은 error_message에 원문 영어 사유
          // 코드('misfire_skip'/'concurrent_run_active')를 그대로 담아 온다 — backupReasonText와 동일한
          // 패턴으로 한국어로 치환하고, 그 외(실제 예외 메시지)는 원문 그대로 보여준다.
          { key: "error_message", label: "오류", render: (r) => schedSkipReasonText(r.error_message) },
          // 이 실행 건을 실제로 처리한 작업(큐)으로 가는 링크(FN-13/IA-02 반대 방향) — 예전엔
          // 실패 원인을 더 깊이 보려면(시도 횟수·워커 last_error·소요 시간) 작업 큐에서 이
          // schedule_run_id를 손으로 찾는 것 말고는 길이 없었다. SubListDrawer의 rowActions는
          // navigate를 지원하지 않아(act()가 path()를 호출하는 mutation 전용) 컬럼 링크로 둔다.
          { key: "job_link", label: "작업 큐", render: (r) => React.createElement(Link, { underline: "hover", href: "#/jobs?schedule_run_id=" + encodeURIComponent(r.id) }, "보기") }],
        emptyTitle: "실행 이력이 없습니다", emptyHelp: "아직 이 일정이 실행된 적이 없습니다(또는 이 필터에 해당하는 기록이 없습니다).",
        rowActions: [
          // 목록 열은 진단 핵심 두 값(보낸 페이로드/응답 요약)을 60자로 자른다 — 그 너머는 볼 방법이
          // 없었다. 이미 불러온 행 데이터를 그대로(전체 길이) 안내 모달로 보여준다(네트워크 호출 없음).
          { label: "전체 보기", localInfo: (sub) => {
              const fmt = (v) => (v == null || v === "" || (typeof v === "object" && !Object.keys(v).length)) ? "(없음)" : (typeof v === "string" ? v : JSON.stringify(v, null, 2));
              const lines = ["보낸 페이로드:\n" + fmt(sub.request_payload), "\n응답 요약:\n" + fmt(sub.response_summary)];
              if (sub.error_message) lines.push("\n오류:\n" + fmt(sub.error_message));
              return lines.join("\n");
            } },
          // 재시도는 비활성 스케줄에서 409가 나므로 부모 스케줄이 활성일 때만 노출한다.
          // keepOpen — 방금 재시도한 결과(대기→성공/실패로 바뀌는 것)를 보려고 이 실행 이력을 계속
          // 보고 있는 것인데, 예전엔 성공 즉시 드로어가 닫혀 다시 열어야 했다(같은 목록을 벗어나지
          // 않는 작업이므로 목록만 새로고침하고 드로어는 열어 둔다).
          { label: "재시도", roles: OPS_ROLES, when: (sub, parent) => sub.status === "failed" && !!(parent && parent.enabled),
            path: (sub) => "/api/admin/schedules/runs/" + sub.id + "/retry", keepOpen: true,
            confirm: () => "이 실패한 실행을 다시 시도할까요?" },
        ],
        // 부모 스케줄이 비활성이면 위 '재시도' 버튼이 통째로 숨겨진다(백엔드 _require_execution_gate가
        // 항상 거절하므로) — 그 자리에 이유를 알려준다(DataScreen.jsx SubListDrawer가 소비).
        actionHint: (sub, parent) => (sub.status === "failed" && parent && !parent.enabled)
          ? "이 일정이 비활성 상태라 재시도할 수 없습니다. 먼저 활성화하세요." : null,
      } },
      // operator는 스케줄 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=schedule&object_id=" + r.id },
    ],
    // PUT 전체 교체 → 필수(target_type/target_ref)와 핵심 필드를 모두 함께 보낸다(누락 시 422).
    // 고급 필드(payload_template/retry_policy/misfire/concurrency/timeout/start_at/end_at)도
    // 함께 돌려보내야 한다 — 빠지면 PUT이 이 값들을 기본값으로 되돌린다(라운드트립). _view가 다 준다.
    editMethod: "PUT", edit: { roles: WRITE_ROLES, fields: [
      { name: "name", label: "이름", type: "text", required: true },
      { name: "description", label: "설명", type: "text" },
      { name: "schedule_type", label: "유형", type: "select", options: SCHEDT_OPTS },
      { name: "preset", label: "간편 주기(선택)", type: "select", value: "", options: SCHED_PRESET_OPTS, help: "고르면 Cron 식이 자동 생성됩니다." },
      { name: "cron_expression", label: "Cron 식", type: "text", help: "유형이 ‘1회 실행’이면 이 값은 쓰이지 않습니다." },
      // 이미 실행된 once형은 next_run_at이 비어 있어 이 폼도 run_at을 빈 채로 연다(백엔드 _view가
      // next_run_at이 있을 때만 run_at을 돌려줌) — 그대로 저장하면 백엔드가 422('once 스케줄에는
      // run_at이 필요합니다')로 거절한다. 왜 비어 있는지·무엇을 채워야 하는지 여기서 미리 알린다.
      { name: "run_at", label: "실행 시각(1회형, ISO)", type: "text", help: "시간대 표기가 없으면 UTC로 해석됩니다(KST면 +09:00). 유형이 ‘Cron 반복’이면 이 값은 쓰이지 않습니다. 이미 실행된 1회형 일정은 이 칸이 비어 있습니다. 다시 저장하려면 새 실행 시각을 입력하세요(비워 두면 저장이 거절됩니다)." },
      { name: "timezone", label: "시간대", type: "text" },
      { name: "target_type", label: "대상 유형", type: "select", options: SCHED_TARGET_OPTS },
      { name: "target_ref", label: "대상", type: "select", required: true, optionsFromRefList: "workflows",
        extraOptions: [{ value: "noop", label: "시스템 (noop)" }],
        help: "‘대상 유형’이 워크플로면 여기서 워크플로를 고르세요(승인 필요 없음인 것만). 시스템이면 ‘시스템 (noop)’을 고르세요." },
      { name: "payload_template", label: "실행 페이로드(JSON)", type: "json" },
      { name: "retry_policy", label: "재시도 정책(JSON)", type: "json", help: '예: {"max_attempts": 3}, 일시 오류 시 최대 재시도 횟수(1~10, 기본 3).' },
      { name: "misfire_policy", label: "누락 처리 정책", type: "select", options: MISFIRE_OPTS },
      { name: "concurrency_policy", label: "동시 실행 정책", type: "select", options: CONCURRENCY_OPTS },
      { name: "timeout_seconds", label: "타임아웃(초)", type: "number" },
      { name: "start_at", label: "시작 시각(ISO, 선택)", type: "text" },
      { name: "end_at", label: "종료 시각(ISO, 선택)", type: "text" },
    ] },
  },
  documents: {
    key: "documents", area: "자동화", title: "문서 자동 생성", endpoint: "/api/admin/documents",
    help: "Notion 문서를 자동으로 만듭니다. ‘+ 문서 생성’으로 워크플로와 기간을 지정하면 생성 결과가 아래 기록에 남고, ‘승인 대기’ 문서는 ‘승인’ 화면에서 발행합니다.",
    emptyTitle: "생성된 문서가 없습니다",
    // WF1 R5 — 쓰기 역할(admin/system_admin)에게는 emptyHelp가 위 help 배너 및 아래
    // emptySteps[0]와 거의 같은 문장("'+ 문서 생성'으로 워크플로와 기간을 지정하면...")을
    // 세 번째로 또 반복했다(DataScreen.jsx가 canOnboard일 때만 situation/prerequisite/
    // steps/expected를 함께 보여준다 — 그 구조가 이미 "무엇을 할지"를 충분히 말한다).
    // 읽기 전용 역할(operator/auditor)에는 그 4단 구조 자체가 안 보이므로(canOnboard=false)
    // emptyHelp가 유일한 안내다 — 그쪽만 남긴다.
    emptyHelp: (role) => (role === "admin" || role === "system_admin")
      ? null
      : "문서 생성 권한이 있는 관리자가 생성하면 여기에 기록이 남습니다.",
    // 연동/러너 화면처럼 단계별 온보딩 안내를 준다(canOnboard가 primary 헤더 작업 '+ 문서 생성'을 근거로
    // 쓰기 역할에만 보여준다). 문서 자동화가 설정에서 꺼져 있으면 '+ 문서 생성'이 409로 실패하므로
    // 선행 조건과 설정 화면 확인을 안내하고, 워크플로 등록이 선행이라 relatedLink로 이어 준다.
    emptySituation: "아직 자동 생성된 Notion 문서가 없습니다.",
    // DGEN-02: "워크플로가 등록돼 있어야 한다"는 문구만으로는, 채팅용(AI 업무 도우미)이나
    // Notion 매핑용 워크플로가 이미 있는 설치의 관리자가 "워크플로는 있는데 왜 안 되지"로
    // 헤맬 수 있다 — 문서 생성은 그 워크플로들과 무관한 별도 워크플로가 필요하다는 사실
    // 자체를 이 문구가 말하지 않았다(실측: 설치 하나에 등록 워크플로 2개, 둘 다 문서
    // 생성용이 아니었는데 빈 상태는 그 사실을 말하지 않고 그냥 "등록해라"라고만 했다).
    emptyPrerequisite: "대상 워크플로가 먼저 추가, 활성화돼 있어야 하고, 설정에서 ‘문서 자동화’가 활성화되어 있어야 합니다(비활성화되어 있으면 생성이 409로 거절됩니다, #/settings에서 확인). 이 워크플로는 채팅(AI 업무 도우미)이나 Notion 매핑용 워크플로와는 별개입니다. 이 설치에 문서 생성 전용 워크플로가 추가되어 있는지 아래 링크에서 먼저 확인하세요.",
    emptySteps: ["‘+ 문서 생성’으로 대상 워크플로와 기간을 지정합니다.", "모드에 따라 미리보기/승인 대기/발행으로 진행됩니다.", "‘승인 대기’ 문서는 ‘승인’ 화면에서 발행합니다."],
    emptyExpected: "요청한 문서 생성 건이 상태와 함께 이 목록에 남고, 발행되면 Notion 링크가 표시됩니다.",
    emptyRelatedLink: { href: "#/workflows", label: "먼저: 워크플로 추가로 이동" },
    // DGEN-01: '+ 문서 생성' 폼의 워크플로/템플릿 ID가 손으로 옮겨 적는 자유 텍스트였다 — 이
    // 화면이 이미 아는 목록(워크플로/템플릿 이름)을 select로 보여준다(DataScreen.jsx의
    // refListOptions/withOptionsFrom, DOC_GENERATE_FIELDS의 optionsFromRefList가 소비).
    refLists: [
      { key: "workflows", endpoint: "/api/admin/workflows" },
      { key: "templates", endpoint: "/api/admin/templates" },
    ],
    // 템플릿 화면의 '이 템플릿으로 문서 생성'에서 넘어온 해시 쿼리를 생성 폼에 프리필한다(DataScreen이 소비).
    // template_id는 config JSON 안으로 넣고, 워크플로 템플릿의 대상 ID를 workflow_id로 채운다.
    // ?id=는 다른 화면(승인의 '대상 보기' 등)이 특정 문서 생성 건으로 딥링크할 때 쓴다 — runners.onQuery와
    // 동일한 패턴으로 그 문서의 상세 드로어를 곧바로 연다.
    onQuery: (p) => p.id
      ? { open: "select", id: p.id }
      : (p.template_id ? { open: "header", label: "+ 문서 생성", initial: docConfigInitial({ workflow_id: p.workflow_id, config: { template_id: p.template_id } }) } : null),
    selectKey: "generation",
    paginated: true,
    // 비동기 생성(pending→미리보기/승인대기 등) 상태 전이를 화면이 자동으로 따라간다.
    // '승인 대기'는 다른 화면(승인)에서만 풀리므로 여기서 무한 폴링하지 않는다 — pending만 추적한다.
    pollWhile: (r) => r.status === "pending",
    // status는 백엔드가 지원하는 서버 필터. mode는 백엔드 목록이 받지 않으므로(list_generations는
    // status만 받는다 — app/documents/router.py) clientFilter로 현재 페이지에서만 거른다.
    // ⚠ 이 화면은 paginated라, 모드 필터는 구조적으로 '지금 페이지 안'까지가 한계다. 위
    // paginated+clientFilter 경고 Callout이 그 필터 이름을 지목해 함께 알린다 — 조용히 반만
    // 거르지는 않는다. 제대로 된 해결은 서버가 mode를 받는 것이고(status 바로 옆 3줄), 그건 이
    // 작업의 소유 범위(registry.js와 그 부품) 밖이라 손대지 않고 여기에 적어 둔다.
    filters: [{ key: "status", type: "select", label: "상태", options: opt([["pending", "대기"], ["preview_ready", "미리보기 완료"], ["quality_failed", "품질 미달"], ["awaiting_approval", "승인 대기"], ["published", "발행됨"], ["failed", "실패"]]) },
      { key: "mode", type: "select", label: "모드", clientFilter: true, options: opt([["preview_then_approve", "미리보기 후 승인"], ["preview_only", "미리보기만"], ["auto_publish", "자동 발행"]]) }],
    headerActions: [
      { label: "+ 문서 생성", variant: "primary", primary: true, roles: WRITE_ROLES, path: () => "/api/admin/documents/generate",
        result: docGenerateResult, fields: DOC_GENERATE_FIELDS, transform: docConfigTransform },
    ],
    // 첫 열은 원시 UUID 대신 사람이 읽는 식별자(미리보기 제목 → 없으면 UUID)로 행을 구분한다.
    // 실제 UUID(id)는 감사 로그 대조·API 문의 등에 필요한데 어디에도 안 보였다 — 두 분기 모두 끝에
    // 붙여 항상 보이게 한다(제목이 있어도 UUID를 확인·복사할 방법이 있어야 한다).
    columns: [{ key: "id", label: "문서", identifier: true, render: (r) => {
      const idSuffix = r.id ? ", " + r.id : "";
      if (r.preview && r.preview.title) return String(r.preview.title) + idSuffix;
      // 미리보기 제목이 없는 행(대기·품질 미달·실패 — 정확히 운영자가 가장 자주 찾아보는 상태들)은
      // 원시 UUID 대신 기간·상태로 사람이 알아볼 수 있는 라벨을 만든다(스케줄 실행 이력의 동일한
      // 문제와 같은 이유 — 목록을 훑을 때 UUID만으로는 어느 행인지 구분할 수 없었다).
      const st = { pending: "대기", preview_ready: "미리보기 완료", quality_failed: "품질 미달", awaiting_approval: "승인 대기", published: "발행됨", failed: "실패" }[r.status] || r.status || "?";
      return "기간 " + (r.period || "?") + " 문서 (" + st + ")" + idSuffix;
    },
      // SEM-01: 이 열이 render라 표식 없이는 전부 "상세 보기"였다 — 위 render와 같은 값(단
      // 낭독 시 장황한 UUID는 뺀다)을 rowName으로 노출해 행마다 실제로 다른 이름을 만든다.
      rowName: (r) => {
        if (r.preview && r.preview.title) return String(r.preview.title);
        const st = { pending: "대기", preview_ready: "미리보기 완료", quality_failed: "품질 미달", awaiting_approval: "승인 대기", published: "발행됨", failed: "실패" }[r.status] || r.status || "?";
        return "기간 " + (r.period || "?") + " 문서 (" + st + ")";
      } },
      col("period", "기간"), mapCol("mode", "모드", DOC_MODE), badgeCol("status", "상태"),
      // generation_view가 requested_by를 최상위로 이미 돌려주는데 목록엔 없어 각 행을 요청한 사람을
      // 보려면 상세를 하나씩 열어야 했다(승인 화면은 이미 목록에서 요청자를 바로 보여준다).
      // RG-07: 서버(app/documents/router.py)가 requested_by_name/_email을 이미 매 페이지
      // 계산해 주는데 화면이 raw UUID만 그렸다 — approvals/audit와 같은 personField로 맞춘다.
      personField("requested_by", "요청자", "requested_by_name", "requested_by_email"),
      linkCol("published_ref", "발행 링크"), dateCol("created_at", "생성")],
    // 미리보기 본문·품질 문제·오류를 상세에서 읽는다(미리보기만/품질미달 결과 확인).
    // requested_by는 generation_view가 최상위로 준다 — 누가 요청했는지 상세에서 바로 본다(원시 UUID라 'ID'로 라벨링).
    // template_id는 generation_view가 감사·운영 조회를 위해 일부러 최상위로 승격한 필드다(어느
    // 템플릿이 이 문서를 만들었는지) — config JSON 안에 묻히지 않게 직접 노출한다.
    // id는 이미 목록 첫 열(제목 없으면 원시 UUID로 표시)이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
    // workflow_id·template_id는 다른 화면 엔티티의 ID다 — 러너 상세의 integration_id와 동일한
    // 이유로 원시 텍스트 대신 그 화면으로 바로 이동하는 링크로 보여준다.
    detailFields: [
      // 워크플로 화면의 ?id= 딥링크(onQuery)로 그 워크플로 상세를 곧바로 연다(무필터 전체 목록 아님).
      { key: "workflow_id", label: "워크플로 ID", render: (r) => r.workflow_id ? React.createElement(Link, { underline: "hover", href: "#/workflows?id=" + encodeURIComponent(r.workflow_id) }, r.workflow_id) : "-" },
      // 템플릿 화면이 이제 ?id=로 특정 템플릿 상세를 곧바로 여는 딥링크(onQuery)를 지원한다 — 무필터
      // 전체 목록에만 떨어지던 죽은 앵커가 아니라 실제로 그 템플릿으로 데려간다.
      { key: "template_id", label: "템플릿 ID", render: (r) => r.template_id ? React.createElement(Link, { underline: "hover", href: "#/templates?id=" + encodeURIComponent(r.template_id) }, r.template_id) : "-" },
      // requested_by는 이제 목록 열(요청자)이라 상세에서 중복 제거(드로어는 열+detailFields 합집합을 그린다).
      jsonField("config", "요청 설정"), previewField("preview", "미리보기"), listField("quality_problems", "품질 문제"), field("error_message", "오류"), dateCol("updated_at", "수정")],
    // '승인 대기' 문서는 여기서 발행할 수 없다(백엔드에 문서별 발행 API 없음) — 승인 화면으로 안내한다.
    actions: [
      // '문서 자동 생성' 화면 자체엔 반복/예약 실행 경로가 없다(수동 '+ 문서 생성' 버튼뿐) — 새 인프라를
      // 만드는 대신 이미 있는 스케줄 화면으로 보내 같은 워크플로를 대상으로 한 Schedule을 만들게 한다
      // (템플릿의 '이 템플릿으로 문서 생성'과 동일한 화면 간 프리필 패턴, schedules.onQuery가 소비).
      { label: "정기 실행으로 예약", roles: WRITE_ROLES, when: (r) => !!r.workflow_id,
        navigate: (r) => "#/schedules?workflow_id=" + encodeURIComponent(r.workflow_id) },
      // 특정 문서의 승인 요청으로 딥링크할 수단은 없지만(document.publish 승인은 이 생성 건의 id를
      // approval.object_id로 직접 담지 않는다), 최소한 '대기' 상태로는 걸러 보여준다 — approvals.onQuery가
      // 이제 ?status=를 소비해 실제로 '대기' 큐만 남기고 승인/거절/만료/취소 이력에 묻히지 않게 한다.
      { label: "승인 대기 목록으로", when: (r) => r.status === "awaiting_approval", navigate: () => "#/approvals?status=pending" },
      // FN-07: '+ 문서 생성' 폼을 재오픈해 같은 기간·대상으로 다시 제출하면 idempotency
      // 충돌로 409 막다른 길이었다(round30 감사 E High) — 그래서 백엔드에 같은 레코드를
      // 그대로 재큐잉하는 전용 POST /{id}/retry 가 이미 있는데, 이 버튼은 계속 옛 재오픈
      // 경로(/generate)를 불렀다. jobs·schedule-runs 재시도와 같은 confirm+path 패턴으로
      // 바꾼다 — 새 생성이 아니라 진짜 재시도가 되게.
      { label: "재시도", roles: WRITE_ROLES, when: (r) => r.status === "failed" || r.status === "quality_failed",
        path: (r) => "/api/admin/documents/" + r.id + "/retry", confirm: "이 문서 생성을 같은 설정으로 다시 시도할까요?" },
      // document_generation은 감사 로그의 유효한 object_type이고(app/documents/router.py가 이 이름으로
      // 기록한다) OBJTYPE_OPTS에도 이미 있다 — 부서·직책과 동일한 딥링크를 추가한다.
      // operator는 이 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES) —
      // 다른 화면들의 동일한 '감사 로그에서 보기'와 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=document_generation&object_id=" + r.id },
      // 이 생성 건을 실제로 처리한 작업(큐)으로 가는 링크(FN-13/IA-02 반대 방향) — jobs.onQuery의
      // generation_id 필터가 소비한다. 진행 상황(대기·재시도 횟수)이나 워커의 원시 오류를 보려면
      // 예전엔 작업 큐에서 이 문서의 generation_id를 손으로 찾는 것 말고는 길이 없었다.
      { label: "작업 큐에서 보기", navigate: (r) => "#/jobs?generation_id=" + encodeURIComponent(r.id) },
    ],
  },
  jobs: {
    key: "jobs", area: "운영", title: "작업 큐", endpoint: "/api/admin/jobs",
    // 이 화면이 순수 관찰용(모니터링)으로 읽히지 않게, 실제로 조작 가능한 액션(재시도/취소)이
    // 있다는 것도 헤더에서 바로 안내한다(러너 화면의 help가 이미 자신의 버튼을 언급하는 것과 동일한 패턴).
    help: "채팅, 문서 생성, Notion 동기화, 예약 실행 같은 백그라운드 작업의 처리 현황과 실패를 봅니다. 실패한 작업은 '재시도', 대기 중인 작업은 '취소'할 수 있습니다.",
    // job_type은 chat_message/document_generate뿐 아니라 notion_mapping_sync·schedule_run도
    // 이 화면에 똑같이 나타난다(아래 filters의 job_type 옵션과 JOB_TYPE 맵 참고) — 두 유형만
    // 예시로 들면 처음 보는 사람은 이 화면이 Notion 동기화·예약 실행 작업도 보여준다는 걸 모른다.
    emptyTitle: "처리된 작업이 없습니다", emptyHelp: "채팅, 문서 생성, Notion 동기화, 예약 실행 같은 백그라운드 작업이 실행되면 처리 현황과 실패 내역이 여기에 표시됩니다.",
    // 감사 로그·알림에서 특정 작업으로 딥링크할 때(?job_id=) 무필터 전체 목록 대신 그 작업의 상세
    // 드로어를 곧바로 연다 — GET /api/admin/jobs/{id}는 이미 pollJobUntilDone이 쓰는 엔드포인트다.
    // schedule_id/schedule_run_id/generation_id는 그 반대 방향(FN-13/IA-02) — 스케줄 실행
    // 이력·문서 생성 상세가 "이 실행을 담당한 작업"으로 오는 딥링크다. 특정 행 하나가 아니라
    // 목록을 그 값으로 미리 걸러서 연다(schedule_id/generation_id는 여러 작업과 매칭될 수 있다 —
    // schedule_run_id만 사실상 1건이지만 같은 방식으로 다뤄 일관성을 지킨다).
    onQuery: (p) => p.job_id ? { open: "select", id: p.job_id }
      : (p.schedule_id || p.schedule_run_id || p.generation_id)
        ? { open: "filter", values: { schedule_id: p.schedule_id, schedule_run_id: p.schedule_run_id, generation_id: p.generation_id } }
        : null,
    selectKey: "job",
    paginated: true,
    // 큐가 정체된 실제 장애 상황에선 실패/대기 행을 빠르게 훑어야 한다 — 감사 화면과 동일한
    // 이유(registry.js audit pageSize:100 주석 참고)로 기본값 20보다 넉넉하게 둔다.
    pageSize: 100,
    // 큐 정체를 이 화면에서 바로 감지 — 대기/실행/실패 카운트와 '실행 가능(ready)'·가장 오래된 대기 age.
    // VIS-120: 그 지표들은 전부 "지금 이 순간"뿐이라 최근 24시간 실패 수·평균 처리 시간도 더했다.
    summary: {
      endpoint: "/api/admin/jobs/stats",
      poll: true,   // 대기/실행/실패 카운트도 목록과 함께 주기적으로 갱신(정체를 실시간 감지).
      // (s, {setFilter}) — Dashboard.jsx/Ops.jsx는 이미 이 화면 바깥에서 동일한 카운트 데이터로
      // onClick 드릴다운을 건다(Ops.jsx 주석: '문제를 보여주기만 하고 조치할 방법이 없는 죽은
      // 타일'을 피하려는 목적) — 정작 이 화면 자신의 요약 판독은 그 드릴다운이 없어 같은 데이터를
      // 보여주면서도 클릭해도 아무 일이 없었다. 목록의 status 필터로 직접 좁혀 준다.
      cards: (s, ctx) => {
        const cards = [
          { value: s.queued != null ? s.queued : 0, label: "대기", kind: s.queued > 0 ? "warn" : undefined, onClick: () => ctx.setFilter("status", "queued") },
          { value: s.running != null ? s.running : 0, label: "실행 중", onClick: () => ctx.setFilter("status", "running") },
          // '실행 가능(ready)'은 status 값이 아니라 대기 중 행 중 available_at이 이미 지난 부분집합의
          // 계산값이다(백엔드에 그 자체의 status 필터가 없다) — '대기'와 동일하게 좁혀 준 뒤 목록의
          // '대기' 열(지연 표시)에서 직접 훑게 한다(전혀 드릴다운이 없는 것보다는 낫다).
          { value: s.ready != null ? s.ready : 0, label: "실행 가능(ready)", kind: s.ready > 0 ? "warn" : undefined, onClick: () => ctx.setFilter("status", "queued") },
          { value: s.failed != null ? s.failed : 0, label: "실패", kind: s.failed > 0 ? "danger" : undefined, onClick: () => ctx.setFilter("status", "failed") },
          { value: s.succeeded != null ? s.succeeded : 0, label: "완료", onClick: () => ctx.setFilter("status", "succeeded") },
          { value: s.cancelled != null ? s.cancelled : 0, label: "취소됨", onClick: () => ctx.setFilter("status", "cancelled") },
          // VIS-120: 위 6장은 전부 "지금 이 순간의 큐 깊이"뿐이라 셋 다 0이면 큐가 건강해
          // 보이지만, 최근에 계속 실패해 왔거나(재시도로 큐를 이미 빠져나갔다) 처리가
          // 느려지고 있다는 신호는 어디에도 없었다 — 같은 24시간 창으로 그 둘을 더한다.
          // '실패'(현재 status=failed 행 수, 오래된 것도 포함)와는 다른 신호다: 이건
          // "최근에 새로 실패가 났는가"라는 속도 신호다.
          {
            value: s.recent_failed_24h != null ? s.recent_failed_24h : 0, label: "최근 24시간 실패",
            kind: s.recent_failed_24h > 0 ? "danger" : undefined, onClick: () => ctx.setFilter("status", "failed"),
          },
          {
            value: s.avg_processing_seconds_24h == null ? null : (
              s.avg_processing_seconds_24h < 60
                ? s.avg_processing_seconds_24h.toFixed(1) + "초"
                : Math.floor(s.avg_processing_seconds_24h / 60) + "분 " + Math.round(s.avg_processing_seconds_24h % 60) + "초"
            ),
            label: "평균 처리 시간(24h)",
          },
        ];
        if (s.oldest_queued_at) {
          const str = String(s.oldest_queued_at);
          const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(str) ? str : str + "Z";
          const t = new Date(iso).getTime();
          if (!Number.isNaN(t)) {
            const m = Math.floor(Math.max(0, Date.now() - t) / 60000);
            const age = m < 1 ? "<1분" : (m < 60 ? m + "분" : Math.floor(m / 60) + "시간 " + (m % 60) + "분");
            // 다른 타일과 달리 이 '가장 오래된 대기' 카드만 드릴다운이 없어(백로그로 빨갛게 물들어도
            // 눌러도 아무 일이 없었다) — 인접한 '실행 가능(ready)' 타일과 같은 대기 큐로 좁혀 준다.
            cards.push({ value: age, label: "가장 오래된 대기", kind: m >= 10 ? "danger" : (m >= 1 ? "warn" : undefined), onClick: () => ctx.setFilter("status", "queued") });
          }
        }
        return cards;
      },
    },
    // 대기·실행 중인 작업이 있으면 상태 전이(대기→실행→완료/실패)를 자동으로 따라간다.
    pollWhile: (r) => r.status === "queued" || r.status === "running",
    filters: [
      { key: "status", type: "select", label: "상태", options: opt([["queued", "대기"], ["running", "실행 중"], ["succeeded", "완료"], ["failed", "실패"], ["cancelled", "취소됨"]]) },
      { key: "job_type", type: "select", label: "유형", options: opt([["chat_message", "채팅 메시지"], ["document_generate", "문서 생성"], ["notion_mapping_sync", "Notion 동기화"], ["schedule_run", "예약 실행"]]) },
      // governance.js audit 화면의 actor_user_id/target_user_id와 같은 패턴(자유 텍스트 ID
      // 필터). 스케줄/문서 생성 화면의 크로스링크(onQuery)가 채우지만, 운영자가 직접 ID를
      // 붙여넣어 찾는 용도로도 그대로 쓴다 — 숨긴 필터가 아니라 진짜 검색 기능이다.
      { key: "schedule_id", type: "text", label: "연결된 스케줄 ID" },
      { key: "schedule_run_id", type: "text", label: "실행 건 ID" },
      { key: "generation_id", type: "text", label: "연결된 문서 생성 ID" },
    ],
    // SEM-01: 첫 열(생성 시각)이 dateCol(render 있음)이라 표식 없이는 100건이 전부 "상세
    // 보기"였다. job_type 필터로 좁혀 보는 게 흔한 사용 패턴이라 유형만으로는 부족해
    // (필터링하면 보이는 행 전부가 같은 유형이 된다) 생성 시각까지 합친다 — 요청자 이름/
    // 이메일은 이 화면이 일부러 감추는 값이라(아래 detailFields 주석) 후보에서 제외한다.
    columns: [{ ...dateCol("created_at", "생성"), rowName: (r) => (JOB_TYPE[r.job_type] || r.job_type) + " / " + fmtDateTime(r.created_at) }, mapCol("job_type", "유형", JOB_TYPE), badgeCol("status", "상태"),
      // 대기 중인데 실행 예정 시각이 이미 지났으면 지연(백로그) 신호 — 워커 정체를 이 화면에서 바로 감지.
      { key: "available_at", label: "대기", render: (r) => {
        if (r.status !== "queued" || !r.available_at) return "-";
        const s = String(r.available_at); const iso = /[zZ]$|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z";
        const t = new Date(iso).getTime(); if (Number.isNaN(t)) return "-";
        const diff = Date.now() - t; if (diff <= 0) return "대기 중";
        const m = Math.floor(diff / 60000);
        if (m < 1) return "지연 <1분"; if (m < 60) return "지연 " + m + "분";
        return "지연 " + Math.floor(m / 60) + "시간 " + (m % 60) + "분";
      } },
      { key: "attempt_count", label: "시도", render: (r) => r.max_attempts != null ? r.attempt_count + " / " + r.max_attempts : String(r.attempt_count) },
      // 실패 사유를 목록에서 바로 훑을 수 있게(예전엔 상세 드로어를 하나씩 열어야만 보였다) — 스케줄
      // 실행 이력의 truncate-at-60 패턴과 동일. title 속성으로 truncateCol과 동일하게 마우스 오버 시
      // 전체 텍스트를 미리 볼 수 있게 한다.
      { key: "last_error", label: "오류", render: (r) => { const v = r.last_error; if (!v) return "-"; const s = String(v); return s.length > 60 ? React.createElement("span", { title: s }, s.slice(0, 60) + "…") : s; } }],
    // available_at·last_error는 목록 열에도 있지만 그 열은 각각 '지연 여부만'(대기 상태 한정)과
    // '60자로 자른 요약'만 보여준다 — 상세에서는 같은 값을 실제 시각/전체 텍스트로 보여줘야 하므로
    // (드로어 중복 제거는 key 기준이라) 목록 열과 겹치지 않는 별도 key를 쓴다.
    // 요청자를 이름으로 바꾸지 **않는다**. 서버가 이 응답에서 요청자 이메일/이름을 일부러
    // 빼기 때문이다(app/jobs/router.py `_job_view`: 큐 화면이 대화 내용 열람의 우회로가
    // 되지 않게). 여기에 이름을 그리려면 그 원칙부터 다시 정해야 한다 — 그래서 id 로
    // 남기되, 라벨에 "계정 ID" 라고 적어 이게 사람 이름이 아니라는 것을 분명히 한다.
    detailFields: [field("id", "작업 ID"), field("idempotency_key", "멱등키"), field("user_id", "요청자 계정 ID"), field("conversation_id", "대화 ID"), field("message_id", "메시지 ID"),
      // schedule_run/document_generate 작업이 자신을 구동한 스케줄/문서로 돌아갈 길이 없었다
      // (IA-02) — 백엔드는 이미 참조 ID를 내려주고 있었다(app/jobs/router.py::_link_ids,
      // round30 감사 E에서 이 문제를 위해 추가됨) 프런트가 안 그렸을 뿐이다. schedule_run_id는
      // 개별 실행 건을 여는 화면이 따로 없어(스케줄 상세의 '실행 이력' 하위 목록만 있다)
      // 링크 대신 참조값으로만 보여준다 — 없는 화면으로 가짜 링크를 걸지 않는다.
      { key: "schedule_id", label: "연결된 스케줄", render: (r) => r.schedule_id
        ? React.createElement(Link, { underline: "hover", href: "#/schedules?id=" + encodeURIComponent(r.schedule_id) }, r.schedule_id) : "-" },
      { key: "schedule_run_id", label: "실행 건 ID", render: (r) => r.schedule_run_id || "-" },
      { key: "generation_id", label: "연결된 문서 생성", render: (r) => r.generation_id
        ? React.createElement(Link, { underline: "hover", href: "#/documents?id=" + encodeURIComponent(r.generation_id) }, r.generation_id) : "-" },
      { key: "available_at_full", label: "실행 예정", render: (r) => fmtDateTime(r.available_at) },
      dateCol("started_at", "시작"), dateCol("finished_at", "종료"),
      { key: "duration_ms", label: "소요 시간", render: (r) => r.duration_ms != null ? (Math.round(r.duration_ms / 100) / 10) + "초" : "-" }, // 백엔드 오류 문자열(f"{type(exc).__name__}: {exc}", worker.py)은 pydantic ValidationError 등에서
      // 흔히 여러 줄이다, jsonField와 동일한 <pre>로 렌더해 줄바꿈이 살아 있게 한다(plain span은
      // word-break만 있고 white-space 보존이 없어 여러 줄이 한 줄로 뭉개졌다).
      { key: "last_error_full", label: "마지막 오류", render: (r) => (r.last_error == null || r.last_error === "" ? "-" : React.createElement("pre", { className: "c-detail-json" }, String(r.last_error))) }],
    actions: [
      { label: "재시도", variant: "primary", roles: OPS_ROLES, when: (r) => r.status === "failed", path: (r) => "/api/admin/jobs/" + r.id + "/retry", confirm: "이 작업을 다시 시도할까요?" },
      { label: "취소", variant: "danger", roles: OPS_ROLES, when: (r) => r.status === "queued", path: (r) => "/api/admin/jobs/" + r.id + "/cancel", confirm: "대기 중인 이 작업을 취소할까요? 연결된 티켓, 문서, 스케줄도 정리됩니다." },
      // 재시도/취소는 모두 object_type='job'으로 감사 로그에 기록된다(app/jobs/router.py) — 다른
      // 화면과 동일한 딥링크. operator는 이 화면(OPS_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다
      // (App.jsx SCREEN_ROLES.audit=admin/system_admin/auditor) — admin/system_admin에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin"], navigate: (r) => "#/audit?object_type=job&object_id=" + r.id },
    ],
  },
};
