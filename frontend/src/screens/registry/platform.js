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
import { Badge, PEOPLE_ACTIVE_REF_LIST, WRITE_ROLES, activeCol, backupReasonText, badgeCol, col, dateCol, field, fmtBytes, fmtDateTimeCompact, mapCol, opt, personField, truncateCol, writerEmptyHelp } from "./shared.js";

/* AI 상한이 걸린 계정의 상태 꼬리표. 서버는 코드만 주고(`app/quotas/router.py::_target_states`)
   낱말은 화면이 정한다. `active` 는 정상이라 아무것도 안 붙인다 — 모든 행에 「정상」이 붙으면
   그 열은 아무것도 구별하지 않는다. */
const QUOTA_TARGET_STATE = {
  inactive: " (비활성 계정)",
  archived: " (보관된 계정)",
  missing: " (없는 계정)",
};

export const PLATFORM_SCREENS = {
  backup: {
    smallSet: true, // 저장된 뷰 기준(서버 페이지 + 조건 셋 이상)에 못 미친다(D-506)
    key: "backup", area: "운영", title: "백업", endpoint: "/api/admin/backups",
    // 백업 하나는 파일 하나가 아니라 **세트 디렉터리**다(S12) — 덤프 + 매니페스트 +
    // 체크섬. 매니페스트에는 스키마 판과 «무엇이 안 담겼는가» 가 적혀 있고, 그 파일이
    // 백업과 함께 이동하므로 낯선 서버에서도 범위를 읽을 수 있다.
    // 웹에서 복원하지 않는다는 사실은 항상 보이는 help 에 둔다(system_admin 만 여는 모달
    // 안에 두면 다른 역할은 볼 방법이 없다).
    // 이 목록이 최근 50건까지만 온다는 사실(app/backups/router.py list_backups의 .limit(50))이
    // 화면 어디에도 없었다 — 51번째 백업부터는 조용히 사라진다. 필터를 붙이기 전에 그 경계부터
    // 밝힌다(안 그러면 '필터에 안 걸림'과 '애초에 안 옴'을 구별할 수 없다).
    help: "데이터베이스를 백업합니다. 백업 하나는 덤프와 매니페스트가 함께 든 세트입니다. 오래된 백업은 정한 개수와 기간에 따라 정리됩니다. 복원은 시스템 관리자가 서버에서 별도 스크립트로 수행합니다. 목록에는 최근 50건까지만 표시됩니다.",
    emptyTitle: "아직 백업이 없습니다",
    // 🔴 **거르는 자리는 서버다** (2026-09-01). 처음엔 두 필터가 `clientFilter` 였고, 그
    // 근거는 「받아 온 것이 곧 전부라 다른 쪽에 숨는 행이 없다」였다. 그 전제가 틀렸다 —
    // 이 목록은 최신 50건에서 **잘린다**(BACKUP_LIST_LIMIT). 그래서 「실패한 백업만」이
    // 실제로는 「최근 50건 안의 실패만」이었고, 51번째 이후의 실패는 구조적으로 답이
    // 안 나오는데 화면은 「없다」처럼 그렸다. 이제 조건을 서버가 받아, 상한이 **그 조건
    // 안에서** 최신 50건이 된다.
    // 상한 자체는 `cap` 으로 선언한다 — 화면이 그 경계를 말한다(`capWarning`).
    // 검색도 대상 필드를 못박는다. 기본 검색은 JSON.stringify(row) 전체를 훑어 원시 UUID·체크섬·
    // UTC ISO 시각까지 매칭했다(화면에 보이지 않는 값으로 결과가 걸린다 — 부서/직책 화면과 같은 함정).
    // 「파일이 서버에 남아 있는가」는 상태와 다른 축이다 — 내려받고 지운 백업은 성공한
    // 백업이지만 **복원 지점이 아니다.** 한 열에 섞으면 그 둘을 구별할 방법이 없다.
    cap: 50, capWarning: 50,
    filters: [
      { key: "status", type: "select", label: "상태", options: opt([["verified", "확인됨"], ["succeeded", "성공"], ["failed", "실패"], ["running", "진행 중"]]) },
      { key: "file_state", type: "select", label: "서버 파일", options: opt([["present", "있음"], ["removed", "삭제함"]]) },
    ],
    searchFields: ["path"],
    searchPlaceholder: "백업 파일 이름으로 검색",
    // 백업 프로세스가 도중에 죽으면(OOM-kill·systemd 재시작) 행이 status='running'인 채로 남고,
    // reap_stuck_running()이 다음 GET에서만 정리한다(app/backups/service.py, 60분 임계값) — 이미
    // 열어 둔 탭이 그 GET을 스스로 트리거하지 않으므로, 다른 화면들과 동일하게 진행 중 행이 있으면
    // 자동 새로고침해 그 전이를 화면이 따라가게 한다.
    pollWhile: (r) => r.status === "running",
    // 백업 실행·복원·검증은 모두 system_admin 전용(백엔드 RBAC). 그 외 역할에는 CTA 대신 읽기 전용 안내를 준다.
    emptyHelp: (role) => role === "system_admin"
      ? "‘백업 실행’으로 지금 데이터베이스를 백업하세요. 오래된 백업은 정한 개수와 기간에 따라 정리됩니다."
      : "아직 백업이 없습니다. 백업은 시스템 관리자가 실행할 수 있습니다.",
    // 첫 실행 시스템 관리자에게 단계별 안내를 준다(canOnboard가 primary 헤더 작업 '백업 실행'을
    // 근거로 system_admin에만 보여준다). 다른 운영 화면(연동/러너)의 온보딩 패턴과 통일.
    emptySituation: "아직 데이터베이스 백업이 하나도 없습니다.",
    emptyPrerequisite: "백업 세트는 서버에 만들어집니다. 복원은 서버에서 별도 스크립트로 수행합니다.",
    emptySteps: ["‘백업 실행’으로 지금 세트를 만듭니다.", "상태가 ‘확인됨(verified)’이 되는지 확인합니다. 임시 데이터베이스에 실제로 복원해 본 상태입니다.", "필요하면 ‘내려받기’로 받아 두고, 받은 뒤에 ‘서버에서 삭제’를 고를 수 있습니다."],
    emptyExpected: "실행한 백업이 상태, 크기와 함께 목록에 남고, 정한 개수와 기간만큼 보관됩니다.",
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
      // 백업 실패 사유는 외부 도구(pg_dump/pg_restore)의 stderr 가 섞여 올 수 있다 —
      // 알려진 사유 코드만 한국어로 치환해 영어가 그대로 새지 않게 한다(backupReasonText).
      { label: "백업 실행", variant: "primary", primary: true, roles: ["system_admin"], path: () => "/api/admin/backups", confirm: "지금 데이터베이스 백업을 실행할까요?",
        result: (res) => { const s = res.backup && res.backup.status; const ok = s === "verified" || s === "succeeded"; return { ok, msg: ok ? "백업 완료" : ("백업 실패: " + backupReasonText((res.backup && res.backup.error_message) || "확인 실패")) }; } },
      /* 🔴 이 화면에서 **예약을 만질 길이 없었다** (2026-09-01). 이 화면은 「지금 한 번」만
         할 수 있었고 「매일 새벽 3시」는 관리 콘솔 설정 표 어딘가에 있었다 — 그래서
         `check_backup_health` 가 「백업 화면에서 예약을 켜세요」라고 알려도 그 화면에는
         켤 것이 없었다. 항목 딥링크로 그 자리를 바로 연다(`SettingsMain` 의 `?setting=`). */
      { label: "백업 일정 설정", roles: WRITE_ROLES, navigate: () => "#/settings?setting=backup_schedule" },
    ],
    /* 이 화면은 「백업이 있는가」만 말하고 「백업이 **돌고 있는가**」는 한 번도 말하지 않았다.
       그 답은 이미 서버에 있었는데(`GET /api/admin/backups/schedule`) 옆 탭 하나만 읽고
       있었다 — 예약이 꺼진 채로 이 목록을 열면 마지막 백업이 20일 전이어도 화면은
       평온했다(RSTR-03 이 겪은 그 상태다). */
    summary: {
      endpoint: "/api/admin/backups/schedule",
      /* 백업 일정은 세는 값이 아니라 **속성**이다(cron · 마지막 시각 · 보관 규칙) — 속성 줄로 선다(계획 표 7). */
      kind: "meta",
      cards: (data) => {
        const s = (data && data.schedule) || {};
        const last = data && data.last_backup;
        return [
          { value: s.enabled ? s.cron : "비활성", label: s.enabled ? "자동 백업 (" + (s.timezone || "Asia/Seoul") + ")" : "자동 백업", kind: s.enabled ? "ok" : "warn" },
          { value: last ? fmtDateTimeCompact(last.created_at) : "없음", label: "마지막 백업", kind: last ? "ok" : "danger" },
          { value: s.keep == null ? "-" : String(s.keep), label: "보관 개수" },
          { value: s.keep_days == null ? "-" : (String(s.keep_days) + "일"), label: "보관 기간" },
        ];
      },
      /* 「백업이 있다」와 「그 백업을 믿을 수 있다」는 다른 질문이고, 후자의 답이 여기 있다.
         세는 대신 **문장 그대로** 낸다 — 「1건」으로는 무엇을 해야 할지 알 수 없다. */
      notes: (data) => (data && data.warnings) || [],
    },
    // 경로는 파일명만 목록에 보이고(내부 배포 경로 노출·너비 낭비 방지), 전체 경로는 상세에서 본다.
    // SEM-01: 첫 열(생성 시각)이 dateCol(render 있음)이라 표식 없이는 전부 "상세 보기"였다 —
    // 파일명(아래 "파일" 열과 동일한 추출 로직)으로 실제로 구별되는 이름을 만든다.
    columns: [{ ...dateCol("created_at", "생성"), rowName: (r) => {
      const p = r.path;
      if (!p) return "백업 / " + fmtDateTimeCompact(r.created_at);
      const s = String(p);
      const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
      return i >= 0 ? s.slice(i + 1) : s;
    } }, badgeCol("status", "상태"), { key: "size_bytes", label: "크기", type: "number", render: (r) => fmtBytes(r.size_bytes) },
      // 파일 이름은 산문이 아니라 토큰이다 — `identifier` 다. 산문(`text`)으로 두면 제목이 없는 이 표에서
      // 남는 폭을 가져가(D-501) 「db.dump」 하나가 1,000px 칸 가운데에 떠 있게 된다.
      { key: "path", label: "파일", type: "path", render: (r) => { const p = r.path; if (p == null || p === "") return "-"; const s = String(p); const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\")); return i >= 0 ? s.slice(i + 1) : s; } },
      // 「성공한 백업」과 「지금 되돌릴 수 있는 백업」은 다르다. 내려받고 서버에서 지운
      // 백업은 전자이지 후자가 아니고, 그 차이가 목록에서 보여야 한다.
      // 🔴 `type:"text"` 였다. 이 칸에 들어가는 것은 산문이 아니라 **배지**인데, `text` 는
      // 왼쪽 정렬 + 12rem 바닥 + 수축 후보라 머리글(언제나 가운데)과 값이 서로 다른 자리에
      // 섰다 — 1920 실측에서 「서버 파일」머리는 1677, 그 아래 배지는 1527 이었다.
      // 🔴 이 칸이 「있음」이라고 말하는 근거는 `file_state` 하나였는데, 그 값은 **사람이
      // 서버 파일을 지웠는가**만 기록한다(D-204) — 운영이 밖에서 덤프를 치워도 `present` 다.
      // 그래서 서버에 없는 파일을 「있음」이라고 적었다. 서버가 실제로 디스크를 보고 내는
      // 판정(`download_blocked_reason === "missing"`)이 있으면 그것을 말한다. 그 필드를
      // 안 싣는 옛 응답에서는 예전과 똑같이 두 값만 그린다.
      { key: "file_state", label: "서버 파일", type: "status", render: (r) => {
        if (r.file_state === "removed") return React.createElement(Badge, { value: "삭제함", kind: "warn" });
        if (r.download_blocked_reason === "missing") return React.createElement(Badge, { value: "서버에 없음", kind: "danger" });
        return React.createElement(Badge, { value: "있음", kind: "ok" });
      } }],
    // 목록 열은 파일명만 보여주고(위 columns "파일") 상세는 전체 경로를 보여준다 — 둘 다 실제로는
    // r.path를 읽지만 표시가 다르므로(파일명 vs 전체 경로), 새 드로어 중복 제거(key 기준, DataScreen.jsx
    // mergeDetailFields)가 이 상세 전용 항목을 columns의 "파일"과 같은 것으로 오인해 지우지 않도록
    // key를 다르게 둔다.
    // id는 감사 로그의 object_id(object_type=backup)와 대조할 때 필요한데, 템플릿·감사 기록 상세와
    // 달리 이 화면만 id를 어디에도 보여주지 않아 대조할 방법이 없었다.
    // backup_type 은 **덤프 형식**이다 — 되돌릴 때 어떤 도구로 여는지가 이 값에 달렸다.
    // 옛 설치에는 `sqlite` 행이 남아 있을 수 있어 둘 다 이름을 붙인다(원문이 새지 않게).
    detailFields: [field("id", "백업 ID"), mapCol("backup_type", "유형", { pg_dump: "PostgreSQL 덤프", sqlite: "SQLite(옛 형식)" }), { key: "path_full", label: "세트 경로", render: (r) => r.path || "-" }, personField("created_by", "실행한 사람", "created_by_name", "created_by_email"), field("checksum", "체크섬"), field("alembic_head", "스키마 판"), dateCol("verified_at", "검증 시각"), dateCol("downloaded_at", "내려받은 시각"),
      // 「무엇이 안 담겼는가」를 상세에서 읽을 수 있어야 한다 — 복원한 뒤 검색이 비어 있는
      // 것을 보고 사고로 오해하는 일이 이 한 줄로 없어진다.
      { key: "excluded_table_data", label: "담지 않은 것", render: (r) => (r.excluded_table_data || []).join(", ") || "-" },
      { key: "destination_name", label: "백업 저장소 사본", render: (r) => {
        if (!r.destination_name) return "보내지 않았습니다";
        return r.destination_name + (r.destination_ok ? " (확인됨)" : " (실패)");
      } },
      { key: "warnings", label: "경고", render: (r) => (r.warnings || []).join(" ") || "-" },
      { key: "error_message", label: "오류", render: (r) => r.error_message ? backupReasonText(r.error_message) : "-" }],
    // 검증 엔드포인트는 상태와 무관하게 어떤 backup id도 받아들인다(app/backups/router.py) — 예전엔
    // status===verified|succeeded일 때만 버튼을 보여줘서, 한 번 failed가 된 행은 재검증할 방법이
    // 영영 사라졌다(백엔드는 지원하는데 UI만 막고 있었다). 상태와 무관하게 항상 노출한다.
    actions: [
      // status==='running'인 동안은 덤프가 아직 쓰이는 중이고 체크섬도 null이다(app/backups/service.py
      // run_backup()) — 그 창에 '검증'을 누르면 체크섬 비교를 건너뛰고 그 순간의 불완전한 파일만
      // 보게 되어, 정상적으로 진행 중인 백업을 failed로 격하시킬 수 있다. 서버도 독립적으로 막지만
      // (409) 화면에서도 안 보여준다. 완료된 백업에만 노출한다.
      // 🔴 서버에서 지운 백업에는 검증할 파일이 없다 — 눌러도 언제나 「이 백업 파일은
      // 서버에서 이미 삭제했습니다」로 끝난다(`verify_existing` 의 `file_removed` 조기 반환).
      // 그 사실은 「서버 파일」열이 이미 말하고 있으므로, 실패밖에 못 내는 단추를 남기지
      // 않는다. 실패한 백업은 그대로 재검증할 수 있다(파일이 남아 있으면).
      // 여기는 아래 「내려받기」와 달리 `downloadable` 을 보지 **않는다**. 그 판정은 실패한
      // 백업(`status === "failed"`)도 막는데, 검증은 실패한 세트를 다시 확인하는 것이 바로
      // 그 목적이다. 디스크에서 사라진 파일도 검증은 `file_missing` 이라는 답을 돌려주므로
      // (`verify_existing`) 누른 사람이 사실을 얻는다 — 받을 것이 없는 것과는 다르다.
      { label: "검증", roles: ["system_admin"], when: (r) => r.status !== "running" && r.file_state !== "removed", path: (r) => "/api/admin/backups/" + r.id + "/verify",
        result: (res) => ({ ok: !!(res.verify && res.verify.ok), msg: (res.verify && res.verify.ok) ? "검증 완료: 정상" : "검증 실패: " + backupReasonText((res.verify && res.verify.reason) || "손상 가능성") }) },
      /* 내려받기 — `DataScreen.runDownload` 가 처리한다. 작은 산출물은 화면을 떠나지 않고
         fetch 로 받아 상태를 확인하고 Blob 으로 저장하며, 실패는 토스트로 말한다(파일 이름은
         응답의 `Content-Disposition` 을 직접 읽어서 붙인다). 큰 덤프는 `size_bytes` 를 보고
         브라우저의 내려받기 관리자에게 넘긴다 — 몇 GB 를 탭 메모리에 담지 않는다.
         옛 주석은 「브라우저가 직접 그 주소로 가야 Content-Disposition 이 먹는다」였는데,
         그 규칙은 이제 성립하지 않는다(그리고 그 갈래에서는 403·504 가 관리자 콘솔을
         통째로 날 JSON 오류 페이지로 바꿨다).

         🔴 **받을 수 있는가는 서버가 판정한다**(`app/backups/router.py::_downloadable`).
         예전 조건 `file_state === "present"` 는 아무것도 거르지 못했다 — 그 칸에 들어가는
         값은 `present`/`removed` 둘뿐이라(`app/backups/models.py`) 「지운 것이 아니다」를
         길게 적은 것과 같았다. 실패한 백업에도, 디스크에서 사라진 덤프에도 `present` 가
         그대로 남아 단추가 섰고, 누르면 「백업 파일이 서버에 없습니다」로 끝났다.
         `!== false` 로 보는 이유: 그 필드를 안 싣는 옛 응답에서는 예전 조건 그대로 동작해야
         한다(그때는 아래 두 조건이 판정을 맡는다). */
      { label: "내려받기", roles: ["system_admin"],
        when: (r) => r.downloadable !== false && r.status !== "running" && r.file_state !== "removed",
        download: (_qs, r) => "/api/admin/backups/" + r.id + "/download" },
      // 🔴 **자동으로 지우지 않는다**(D-204). 브라우저가 받다 만 것과 다 받은 것을 서버는
      // 구별하지 못하므로, 지우는 것은 받은 사람이 답한 뒤여야 한다. 그래서 이 작업은
      // 내려받은 적이 있는 행에만 뜨고, 누르면 확인을 한 번 더 묻는다.
      { label: "서버에서 삭제", variant: "danger", roles: ["system_admin"],
        when: (r) => r.file_state === "present" && !!r.downloaded_at,
        confirm: "서버에 저장된 백업 파일을 삭제하시겠습니까? 내려받은 파일과 백업 저장소 사본은 그대로 남고, 이 서버에서는 이 백업으로 되돌릴 수 없게 됩니다.",
        path: (r) => "/api/admin/backups/" + r.id + "/discard-file",
        result: () => ({ ok: true, msg: "서버에서 삭제했습니다" }) },
      // operator는 백업 화면(READ_ROLES)엔 들어오지만 /audit 화면엔 못 들어간다(App.jsx SCREEN_ROLES)
      // — approvals.registry.js:990과 동일한 이유로 admin/system_admin/auditor에만 노출한다.
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=backup&object_id=" + r.id },
    ],
  },
  "restore-drills": {
    smallSet: true, // 저장된 뷰 기준(서버 페이지 + 조건 셋 이상)에 못 미친다(D-506)
    key: "restore-drills", area: "운영", title: "복구 리허설",
    endpoint: "/api/admin/backups/rehearsals",
    help: "백업은 복원해 본 적이 없으면 백업이 아닙니다. 리허설은 백업을 임시 데이터베이스로 실제로 되돌려 무결성, 행 수, 스키마를 대조하고, 복원본으로 앱을 띄워 읽기 경로까지 확인합니다. 앱이 스스로 돌리지 않으므로(메모리를 두 배로 쓰기 때문) 서버에서 명령을 실행하면 결과가 여기에 남습니다. 목록에는 최근 20건까지만 표시됩니다.",
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
      "서버에서 python scripts/restore_rehearsal.py --record 를 실행합니다.",
      "백업 → 검증 → 새 데이터베이스로 복원 → 무결성 → 행 수 대조 → 스키마 → 실제 부팅 → 첨부 순으로 여덟 단계가 돕니다.",
      "복원은 임시 데이터베이스에만 하므로 운영 데이터를 건드리지 않습니다.",
      "끝나면 결과 한 줄이 이 목록에 남습니다(실패하면 실패한 단계도 함께).",
    ],
    emptyExpected: "‘마지막으로 복원을 시험한 게 언제인가’에 이 화면 하나로 답할 수 있게 됩니다.",
    emptyRelatedLink: { href: "#/backup", label: "백업 목록으로 이동" },
    // 이 화면이 답해야 하는 질문은 '언제 마지막으로 실패했나'인데, 필터가 하나도 없어
    // 통과한 기록 사이에서 실패를 눈으로 찾아야 했다. 그 필터를 붙였고, **거르는 자리는
    // 서버다** — 응답이 최근 20건에서 잘리므로(REHEARSAL_LIST_LIMIT) 화면 안에서 거르면
    // 「마지막 실패」가 「최근 20건 안의 실패」로 조용히 좁아진다(백업 목록과 같은 이유).
    cap: 20, capWarning: 20,
    filters: [{ key: "ok", type: "select", label: "결과", options: opt([["true", "통과"], ["false", "실패"]]) }],
    // 기본 검색은 JSON.stringify(row) 전체를 훑는다 — 이 행에는 summary 객체와 ok 불리언이 들어
    // 있어서 '실패'를 찾으려고 true를 쳐 넣으면 통과한 기록이 전부 걸린다(화면에 없는 값으로
    // 결과가 걸리는, 부서/직책 화면에서 이미 한 번 고친 함정). 사람이 읽는 원본 라벨만 본다.
    searchFields: ["source_label"],
    searchPlaceholder: "원본 백업 이름으로 검색",
    summary: {
      endpoint: "/api/admin/backups/schedule",
      /* 백업 일정은 세는 값이 아니라 **속성**이다(cron · 마지막 시각 · 보관 규칙) — 속성 줄로 선다(계획 표 7). */
      kind: "meta",
      cards: (data) => {
        const s = (data && data.schedule) || {};
        const last = data && data.last_backup;
        const drill = data && data.last_rehearsal;
        return [
          { value: s.enabled ? s.cron : "비활성", label: s.enabled ? "자동 백업 (" + (s.timezone || "Asia/Seoul") + ")" : "자동 백업", kind: s.enabled ? "ok" : "warn" },
          // 🔴 `fmtDateTime` 이었다 — 그 형식기는 「2026. 8. 23. 오후 12:00」을 내는데, 바로
          // 아래 표의 같은 값은 「2026-08-23 12:00」이다(`dateCol` → `DateCell`). 한 화면이
          // 같은 시각을 두 가지 말로 적으면 눈이 그 둘을 대조하지 못한다. 표와 같은 형식기로.
          { value: last ? fmtDateTimeCompact(last.created_at) : "없음", label: "마지막 백업", kind: last ? "ok" : "danger" },
          { value: drill ? (drill.ok ? "통과" : "실패") : "한 번도 안 함", label: "마지막 리허설", kind: drill ? (drill.ok ? "ok" : "danger") : "warn" },
          { value: s.keep == null ? "-" : String(s.keep), label: "보관 개수" },
          { value: s.keep_days == null ? "-" : (String(s.keep_days) + "일"), label: "보관 기간" },
        ];
      },
      // 경고는 **문장 그대로** 낸다. 예전에는 「1건」이라는 카드 하나였는데, 그 숫자를 본
      // 사람이 할 수 있는 일이 없었다 — 무엇이 경고인지는 어디에도 안 적혀 있었다.
      notes: (data) => (data && data.warnings) || [],
    },
    columns: [
      { key: "ok", label: "결과", type: "status", render: (r) => React.createElement(Badge, { value: r.ok ? "통과" : "실패", kind: r.ok ? "ok" : "danger" }) },
      dateCol("started_at", "시작"), dateCol("finished_at", "종료"),
      { key: "_rows", label: "행 수", type: "count", render: (r) => (r.summary && r.summary.rows != null) ? String(r.summary.rows) : "-" },
      { key: "_head", label: "스키마", type: "enum", render: (r) => (r.summary && r.summary.alembic_head) || "-" },
      // SEM-01: 첫 열(결과 배지)이 render라 표식 없이는 전부 "상세 보기"였다 — 원본 백업
      // 이름(검색 대상과 동일한 필드) + 시작 시각으로 실제로 구별되는 이름을 만든다.
      // 원본은 백업 세트 이름(「20260823-020000」)이라 토큰이다 — `identifier` 로 둔다. 산문으로 두면 남는
      // 폭을 가져간다(D-501, 백업 「파일」과 같은 이유).
      { ...truncateCol("source_label", "원본", 50), type: "identifier", rowName: (r) => (r.source_label || "리허설") + " / " + fmtDateTimeCompact(r.started_at) },
    ],
    detailFields: [
      field("id", "기록 ID"),
      { key: "failures", label: "실패한 단계", render: (r) => (r.failures || []).join(", ") || "없음" },
      { key: "_summary", label: "요약", render: (r) => JSON.stringify(r.summary || {}) },
    ],
    /* 「백업 목록」 머리 단추를 걷었다(D-501) — 이 화면은 언제나 「백업」 그릇의 탭이라 바로 옆 「백업」 탭이 같은
       곳으로 간다. 같은 이동이 두 자리에 있으면 둘 중 무엇을 눌러야 하는지를 사람이 따져야 한다. */
    headerActions: [
      // 설정 표 스무 줄 앞에 내려놓지 않는다 — 보내는 쪽이 어느 줄인지 이미 알고 있다.
      { label: "백업 일정 설정", roles: WRITE_ROLES, navigate: () => "#/settings?setting=backup_schedule" },
    ],
  },
  announcements: {
    key: "announcements", area: "설정", title: "공지 배너",
    endpoint: "/api/admin/announcements",
    help: "모든 화면 위쪽에 띠로 뜨는 공지입니다. 사용자가 닫으면 그 사람에게는 다시 뜨지 않습니다(브라우저가 아니라 계정에 기록되므로 다른 PC에서도 닫힌 상태가 유지됩니다).",
    emptyTitle: "추가된 공지가 없습니다",
    emptyHelp: writerEmptyHelp("‘공지 추가’로 점검 예고나 안내를 띄우세요.", "공지는 관리자가 추가합니다."),
    emptySituation: "점검이나 장애를 알릴 곳이 알림 벨밖에 없었습니다(놓치기 쉽습니다).",
    emptySteps: ["‘공지 추가’로 제목과 내용을 적습니다.", "필요하면 노출 기간을 정합니다(비우면 ‘사용 안 함’으로 바꿀 때까지 계속).", "‘사용 안 함’으로 바꾸면 즉시 내려갑니다."],
    emptyExpected: "활성 공지는 모든 화면 위쪽에 띠로 뜨고, 사용자가 닫으면 그 계정에는 다시 뜨지 않습니다.",
    createLabel: "공지 추가",
    paginated: true, searchable: true,
    searchFields: ["title", "body"],
    searchPlaceholder: "제목, 내용으로 검색",
    filters: [
      { key: "active", type: "select", label: "사용", options: opt([["true", "사용"], ["false", "사용 안 함"]]) },
      { key: "level", type: "select", label: "중요도", options: opt([["info", "안내"], ["warning", "주의"], ["critical", "긴급"]]) },
    ],
    /* 「중요도」로 정렬하면 서버가 **심각도 순**으로 센다(가나다순이면 긴급이 안내보다
       앞에 서서 뜻이 뒤집힌다 — `app/announcements/router.py::_level_rank`). */
    serverSort: { keys: ["created_at", "updated_at", "title", "starts_at", "ends_at", "active", "level"], default: { key: "created_at", dir: "desc" } },
    /* 「제목」은 그 행의 제목 열이다(D-501) — 홀로 왼쪽에 서고 남는 폭을 갖는다. 「대상」의 「관리자군에게만」은
       일곱 글자라 닫힌 집합 바닥(6.5rem)에서 잘린다 — 그 값이 한 줄로 서는 바닥을 준다. */
    columns: [
      { ...col("title", "제목", "title"), sortable: true },
      { key: "level", label: "중요도", type: "status", sortable: true, render: (r) => React.createElement(Badge, {
        value: ({ info: "안내", warning: "주의", critical: "긴급" })[r.level] || r.level,
        kind: r.level === "critical" ? "danger" : r.level === "warning" ? "warn" : "info",
      }) },
      mapCol("audience", "대상", { all: "모든 사용자", admin: "관리자군에게만" }),
      activeCol("사용"),
      dateCol("starts_at", "시작"), dateCol("ends_at", "종료"),
    ],
    detailFields: [field("id", "공지 ID"), field("body", "내용"),
      { key: "dismissible", label: "닫기 허용", render: (r) => r.dismissible ? "닫을 수 있음" : "닫을 수 없음(기간이 끝나야 사라짐)" },
      field("link_url", "링크 주소"), field("link_label", "링크 문구"), dateCol("created_at", "생성 일자")],
    /* 공지는 **포탈 전체**에 뜬다 — 부서로 나눠 보여 줄 방법 자체가 없어서 서버가 쓰기 전부를
       전역 범위 관리자로 한정한다(`app/announcements/router.py::_ensure_may_touch_announcements`
       → 403 「공지는 전체 범위 관리자만 만들고 바꿀 수 있습니다」). 역할 게이트만으로는 부서
       범위 `admin` 이 그대로 지나므로, 그 사람에게 「추가」·「수정」·「사용」·「삭제」가 그려지고
       눌러 403 을 받고 나서야 못 한다는 것을 알았다. `requiresGlobalScope` 가 그 축을 말한다. */
    create: { roles: WRITE_ROLES, requiresGlobalScope: true, fields: [
      { name: "title", label: "제목", type: "text", required: true },
      { name: "body", label: "내용", type: "textarea" },
      { name: "level", label: "중요도", type: "select", value: "info", options: opt([["info", "안내"], ["warning", "주의"], ["critical", "긴급"]]) },
      { name: "audience", label: "대상", type: "select", value: "all", options: opt([["all", "모든 사용자"], ["admin", "관리자군에게만(운영자 이상)"]]) },
      { name: "starts_at", label: "노출 시작(선택)", type: "datetime-local", help: "비우면 즉시 노출됩니다." },
      { name: "ends_at", label: "노출 종료(선택)", type: "datetime-local", help: "비우면 ‘사용 안 함’으로 바꿀 때까지 계속 노출됩니다." },
      { name: "dismissible", label: "닫기 허용", type: "checkbox", value: true, checkLabel: "사용자가 닫을 수 있음", help: "비활성화하면 닫기 버튼이 없습니다. 그런 공지는 반드시 종료 시각을 정하세요." },
      { name: "link_url", label: "링크 주소(선택)", type: "text" },
      { name: "link_label", label: "링크 문구(선택)", type: "text" },
      { name: "active", label: "사용", type: "checkbox", value: true, checkLabel: "지금 사용" },
    ] },
    editMethod: "PATCH",
    edit: { roles: WRITE_ROLES, requiresGlobalScope: true, fields: [
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
      // 셋 다 위 create/edit 와 같은 서버 게이트를 지난다(`_ensure_may_touch_announcements`).
      { label: "사용", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => !r.active, method: "PATCH", path: (r) => "/api/admin/announcements/" + r.id, body: { active: true } },
      { label: "사용 안 함", roles: WRITE_ROLES, requiresGlobalScope: true, when: (r) => r.active, method: "PATCH", path: (r) => "/api/admin/announcements/" + r.id, body: { active: false }, confirm: "이 공지를 내릴까요? 모든 화면에서 즉시 사라집니다." },
      { label: "삭제", variant: "danger", roles: WRITE_ROLES, requiresGlobalScope: true, method: "DELETE", path: (r) => "/api/admin/announcements/" + r.id, confirm: "이 공지를 지울까요? 되돌릴 수 없습니다(닫음 기록도 함께 의미를 잃습니다)." },
      // announcement은 감사 로그의 유효한 object_type이고(app/announcements/router.py) 이제
      // OBJ_ROUTE에도 있다 — 조직·기능 플래그와 동일한 딥링크를 추가한다(MEGA CYCLE G).
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=announcement&object_id=" + r.id },
    ],
  },
  "ai-quotas": {
    smallSet: true, // 저장된 뷰 기준(서버 페이지 + 조건 셋 이상)에 못 미친다(D-506)
    key: "ai-quotas", area: "AI", title: "AI 사용 한도",
    endpoint: "/api/admin/ai-quotas",
    /* 범위가 «사용자» 일 때 그 사람을 고르기 위한 후보(W5) — 예전에는 ID 를 복사해 왔다.
       **보관된 계정은 후보가 아니다**(xb-10). 퇴사해서 보관한 사람에게 AI 사용 상한을 거는
       일에는 뜻이 없는데, 목록에 이름만 있고 상태 표시가 없어 실제로 그 행이 만들어졌다. */
    refLists: [PEOPLE_ACTIVE_REF_LIST],
    // WF1 R4 — "상한이 걸리는 곳은 아래 표 위의 '상한이 걸리는 곳' 목록에 서버가 직접
    // 알려 줍니다"라는 문장이 있었다. 그런 이름의 목록을 그리는 코드는 저장소에 없다 — 위
    // 요약 카드(FN-05, summary 참고)는 "오늘/이번 달 전체 AI 호출" 합계일 뿐 어느 대상이
    // 상한에 걸렸는지는 안 말한다(그건 아래 표의 각 행 '현재 사용' 대 '상한' 비교, 또는
    // 상세의 '상태' 필드로 본다). 존재하지 않는 기능을 광고하던 문장을 지운다 — 나머지
    // 문장이 이미 카드/표의 실제 의미를 정확히 설명한다.
    /* 지원 기준을 화면에 그대로 적는다(계획 3.10). 기본값은 사람마다 같은 수를 주는 것이지 전사 공용 풀이 아니고,
       조직이나 부서 단위의 공용 풀은 없다 - 없는 기능을 있는 것처럼 읽히지 않게 한 문장으로 밝힌다. */
    help: "AI 사용을 사람마다 하루 또는 한 달 단위로 제한합니다. 하루는 한국 시간 0시에, 한 달은 매월 1일 0시에 초기화됩니다. 기본값은 모든 사용자에게 같은 한도를 주고, 사용자별 한도가 기본값보다 우선합니다. 성공한 호출만 세고, 한도가 없으면 제한이 없으며, 0은 차단입니다. 위 요약 줄은 조직 전체 합계이고, 표의 ‘현재 사용’은 그 행의 한 사람이 쓴 수입니다. 조직이나 부서가 함께 나눠 쓰는 한도는 지원하지 않습니다.",
    emptyTitle: "한도가 없으면 제한 없이 사용합니다",
    emptyHelp: writerEmptyHelp("‘한도 추가’로 하루 또는 한 달 한도를 정하세요. 아무것도 없으면 제한이 없습니다.", "한도는 관리자가 정합니다."),
    emptySituation: "AI 사용에 한도가 없어 한 사람이 많이 써도 막히지 않습니다.",
    emptySteps: ["‘한도 추가’에서 ‘기본값(사용자별)’ 범위로 하루 한도를 정합니다.", "특정 사람만 늘리거나 줄이려면 ‘사용자’ 범위로 한 줄 더 만듭니다.", "목록의 ‘현재 사용’과 ‘남음’ 열로 소비 상황을 확인합니다."],
    emptyExpected: "한도에 닿으면 그 사람의 AI 요청이 거절되고, 언제 초기화되는지 안내됩니다.",
    createLabel: "한도 추가",
    // 필터가 하나도 없어 사용자별 상한이 쌓이면 '한 달 상한만' 같은 질문에 답할 방법이 없었다.
    // GET /api/admin/ai-quotas는 쿼리 파라미터를 받지 않고 페이지네이션도 하지 않는다
    // (app/quotas/router.py list_quotas — 전체를 한 번에 돌려준다). 받아 온 것이 곧 전부이므로
    // clientFilter가 숨기는 행은 없다. 대상 사람 이름은 clientFilter로 다룰 수 없어(정확 일치
    // 비교라 이름 일부로는 못 찾는다) 검색창에 맡긴다 — 그 검색도 대상 필드를 못박는다.
    filters: [
      { key: "scope_type", type: "select", label: "범위", clientFilter: true, options: opt([["global", "기본값(사용자별)"], ["user", "사용자"]]) },
      { key: "period", type: "select", label: "기간", clientFilter: true, options: opt([["day", "하루"], ["month", "한 달"]]) },
    ],
    searchFields: ["user_name", "user_email", "note"],
    searchPlaceholder: "대상 이름, 이메일, 메모로 검색",
    // FN-05 — GET /ai-quotas/usage(app/quotas/router.py)는 처음부터 있었는데 부르는 화면이
    // 없어 죽어 있었다(UB-25와 같은 결함). 아래 행별 "현재 사용" 열은 최다 사용자 1인 또는
    // 특정 사용자 1인의 값이라 "오늘 전체 몇 번 썼나"에는 답을 못한다 — 그건 이 요약이
    // 준다(같은 화면 안에 서로 다른 두 숫자가 있다는 것을 help 문구에도 적어 둔다).
    // 값 둘은 판이 아니라 속성 줄 한 줄이다(D-501) — 「0」 하나씩을 든 800px 판 둘이었다. 누를 수도 없고
    // 경보도 아닌 값이라 판을 세울 이유가 없다(`SummaryView` 의 둘 이하 규칙).
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
      mapCol("scope_type", "범위", { global: "기본값(사용자별)", user: "사용자" }),
      // SEM-01: 첫 열(범위)이 mapCol(render 있음)이라 표식 없이는 같은 범위(대부분 "사용자")끼리
      // 전부 "상세 보기"로 동일했다 — 대상 + 기간을 합쳐 실제로 구별되는 이름을 만든다.
      /* 대상 이름 옆에 **그 계정의 상태**를 적는다(R5-01). 서버가 `user_state` 를 함께 주는데
         (`app/quotas/router.py::_target_states` — active·inactive·archived·missing) 화면이
         읽지 않아, 이미 나간 사람에게 걸린 상한이 살아 있는 사람의 상한과 똑같이 보였다.
         그 행은 아무도 소비하지 않으므로 「현재 사용 0」이 정상처럼 읽힌다. 상태 낱말은
         화면이 정한다 — 서버는 코드만 준다(`file_state` 와 같은 규약). */
      { key: "user_name", label: "대상", identifier: true,
        render: (r) => r.scope_type === "global"
          ? "(모든 사람)"
          : (r.user_name || r.user_id || "-") + (QUOTA_TARGET_STATE[r.user_state] || ""),
        rowName: (r) => (r.scope_type === "global" ? "기본값" : (r.user_name || r.user_id || "-")) + " / " + ({ day: "하루", month: "한 달" }[r.period] || r.period) },
      mapCol("period", "기간", { day: "하루", month: "한 달" }),
      { key: "max_calls", label: "한도", type: "count" },
      // 칸에는 수만 둔다(계획 2.1). 기본값 행의 수가 누구의 것인지는 풀이로 붙인다 - 칸 안에 괄호 설명을 이으면 수 열의
      // 폭에서 「0 / 500 (가…」로 잘렸다(최종 캡처 실측).
      { key: "used", label: "현재 사용", type: "count", render: (r) => {
        if (r.used == null) return "-";
        const text = r.used + " / " + r.max_calls;
        return r.scope_type === "global"
          ? React.createElement("span", { title: "기본값 행은 가장 많이 쓴 사람의 사용 수입니다." }, text)
          : text;
      } },
      { key: "remaining", label: "남음", type: "count", render: (r) => (r.remaining == null ? "-" : String(r.remaining)) },
      dateCol("resets_at", "초기화"),
    ],
    detailFields: [field("id", "한도 ID"), field("user_email", "대상 이메일"), field("note", "메모"),
      dateCol("created_at", "생성 일자"), dateCol("updated_at", "수정"),
      { key: "_over", label: "상태", render: (r) => (r.used != null && r.used >= r.max_calls) ? "한도에 닿았습니다. 이 대상의 AI 요청이 지금 거절됩니다." : "여유가 있습니다." }],
    create: { roles: WRITE_ROLES, fields: [
      { name: "scope_type", label: "범위", type: "select", value: "global", required: true, options: opt([["global", "기본값(사용자별)"], ["user", "사용자"]]) },
      /* W5: 범위가 «사용자» 면 그 사용자를 **고른다** — ID 를 복사해 오는 자리가 아니다. */
      { name: "user_id", label: "사용자", type: "select", kind: "entity", optionsFromRefList: "people", showIf: (v) => v.scope_type === "user" },
      { name: "period", label: "기간", type: "select", value: "day", required: true, options: opt([["day", "하루"], ["month", "한 달"]]) },
      { name: "max_calls", label: "한도(횟수)", type: "number", required: true, help: "0이면 차단입니다. 제한을 없애려면 이 줄을 지우세요. 기간 경계는 한국 시간입니다." },
      { name: "note", label: "메모", type: "text" },
    ] },
    editMethod: "PATCH",
    edit: { roles: WRITE_ROLES, fields: [
      { name: "max_calls", label: "한도(횟수)", type: "number", required: true },
      { name: "note", label: "메모", type: "text" },
    ] },
    actions: [
      /* 🔴 **행마다 다르다.** 서버는 사용자 범위 행이면 「그 사람이 내 범위 안인가」를 보고,
         전역 행이면 관리 범위가 전역인지를 본다(`app/quotas/router.py::_get_or_404` →
         `_ensure_may_touch_global`) — 전역 상한 하나가 0 이 되면 전 사용자의 AI 가 멈추기
         때문이다. 그래서 선언 한 줄(`requiresGlobalScope`)로는 못 말한다: 그것을 걸면 부서
         범위 관리자가 자기 사람들의 상한까지 못 지운다. 행의 범위와 내 범위를 함께 본다. */
      { label: "삭제", variant: "danger", roles: WRITE_ROLES,
        when: (r, ctx) => r.scope_type !== "global" || !ctx || ctx.isGlobalAdmin !== false,
        method: "DELETE", path: (r) => "/api/admin/ai-quotas/" + r.id, confirm: "이 한도를 지울까요? 지우면 이 범위와 기간에는 제한이 없어집니다." },
      // ai_quota는 감사 로그의 유효한 object_type이고(app/quotas/router.py) 이제 OBJ_ROUTE에도
      // 있다 — 조직·기능 플래그와 동일한 딥링크를 추가한다(MEGA CYCLE G).
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=ai_quota&object_id=" + r.id },
    ],
  },
  "feature-flags": {
    /* C2 «Filter Surface 가 정당한가» — 이 화면은 **행 수가 유한하고 작다**(정책 2 ·
       기능 플래그 11 · 통합 4 · RBAC 13 실측). R-88 이 "25행" 을 기계 규칙으로 쓰지 말라고
       못박으므로 숫자가 아니라 **판단**을 남긴다: 조건 조합을 이름 붙여 재사용할 만큼
       탐색이 반복되지 않는다. 그래서 저장된 뷰를 그리지 않는다 — 기능이 아니라 소음이다. */
    smallSet: true,
    key: "feature-flags", area: "설정", title: "기능 플래그",
    endpoint: "/api/admin/feature-flags",
    help: "모듈을 활성화하고 비활성화하는 스위치입니다. ‘파일’ 소유 플래그는 여기서 바꾸면 재시작 없이 즉시 적용됩니다. ‘설정 화면’ 소유 플래그는 여기서 바꿀 수 없습니다. 값의 주인이 한 곳이어야 하기 때문입니다(‘설정’ 화면에서 바꾸세요).",
    emptyTitle: "플래그 정의를 불러오지 못했습니다", emptyHelp: "잠시 후 다시 시도해 주세요.",
    searchFields: ["name", "description"],
    searchPlaceholder: "플래그 이름으로 검색",
    filters: [{ key: "owner", type: "select", label: "값의 주인", clientFilter: true, options: opt([["file", "파일(여기서 수정)"], ["db", "설정 화면"]]) }],
    // WF1 R4(단독 결함) — API가 이미 default를 매 행에 내려주는데(app/admin/feature_flags.py
    // _items) 화면은 상세 드로어에서만 썼다 — 목록만 훑어서는 "지금 값이 안전한 기본값과
    // 같은가"를 알 수 없었다(실사례: game_ai_enabled가 설명상 "기본 OFF(fail-closed)"인데
    // 켜져 있어도 목록에서는 다른 플래그와 똑같이 중립으로 보였다). '기본값' 열을 목록에도
    // 추가하고, '현재' 열이 기본값과 어긋나면(위험 신호) warn 톤으로 눈에 띄게 한다 —
    // 어긋남 자체가 잘못은 아니다(의도적으로 바꿨을 수 있다), 그래도 훑어보다 놓치면 안 되는
    // 상태라는 점은 다른 warn 톤 사용처(activeCol 등)와 같은 이유다.
    /* 남는 폭은 「설명」이 갖는다(D-501 — 제목이 없는 표에서는 마지막 산문 열). 예전에는 여섯 열이 비례로 나눠
       「설명」이 70자 말줄임보다 먼저 칸에서 잘렸고, 「현재」 · 「기본값」은 짧은 표지 하나에 250px 을 썼다. 대신 나머지
       열이 자기 바닥 폭으로 서므로, 값이 긴 둘은 그 값이 한 줄로 서는 바닥을 든다 — 가장 긴 플래그 이름
       (`limited_service_actions_enabled`)과 「없음(읽는 코드 없음)」이다. */
    columns: [
      { ...col("name", "플래그"), identifier: true },
      { key: "value", label: "현재", type: "enum", render: (r) => React.createElement(Badge, { value: r.value ? "활성" : "비활성", kind: r.value === r.default ? (r.value ? "ok" : "neutral") : "warn" }) },
      { key: "default", label: "기본값", type: "enum", render: (r) => React.createElement(Badge, { value: r.default ? "활성" : "비활성", kind: "neutral" }) },
      mapCol("owner", "값의 주인", { file: "파일", db: "설정 화면" }),
      { key: "has_consumer", label: "실제 효과", type: "enum", values: ["있음", "없음(읽는 코드 없음)"], render: (r) => r.has_consumer ? "있음" : "없음(읽는 코드 없음)" },
      truncateCol("description", "설명", 70),
    ],
    // description은 이미 목록 열이지만 그 열은 truncateCol(70자 말줄임, hover title로만 전체 확인)이다
    // — 같은 key로 다시 넣으면 mergeDetailFields가 columns 쪽(자른 버전)만 남기고 이 평문 버전은
    // 조용히 버려져(상세 드로어의 원래 목적인 '전체 설명 확인'이 실제로는 절대 렌더되지 않는다) —
    // audit 화면의 object_id_full/backup 화면의 path_full과 동일한 패턴으로 별도 key를 쓴다.
    detailFields: [
      { key: "description_full", label: "설명", render: (r) => r.description || "-" }, field("edit_hint", "수정 안내"),
      { key: "default", label: "기본값", type: "enum", render: (r) => r.default ? "활성" : "비활성" },
      { key: "_no_consumer", label: "주의", render: (r) => r.has_consumer ? "-" : "이 플래그를 읽는 코드가 아직 없습니다. 활성화하거나 비활성화해도 동작이 달라지지 않습니다." },
    ],
    actions: [
      { label: "활성화", variant: "primary", roles: WRITE_ROLES, when: (r) => r.editable_here && !r.value,
        method: "PUT", path: (r) => "/api/admin/feature-flags/" + encodeURIComponent(r.name), body: { enabled: true },
        confirm: (r) => r.name + " 플래그를 활성화할까요? 재시작 없이 즉시 적용됩니다." },
      { label: "비활성화", variant: "danger", roles: WRITE_ROLES, when: (r) => r.editable_here && r.value,
        method: "PUT", path: (r) => "/api/admin/feature-flags/" + encodeURIComponent(r.name), body: { enabled: false },
        confirm: (r) => r.name + " 플래그를 비활성화할까요? 이 기능을 쓰는 화면이 즉시 사라지거나 요청이 거절됩니다." },
      { label: "설정 화면에서 열기", when: (r) => !r.editable_here, navigate: () => "#/settings" },
      { label: "감사 로그에서 보기", roles: ["admin", "system_admin", "auditor"], navigate: (r) => "#/audit?object_type=feature_flag&object_id=" + encodeURIComponent(r.name) },
    ],
  },
};
