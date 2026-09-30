import React from "react";
import { Badge } from "../../ui/kit.jsx";
import { dateCol } from "../data-screen/columnHelpers.jsx";
import { WRITE_ROLES, field, fmtDateTimeCompact, opt } from "../registry/shared.js";

/* 메일 발송 기록 — 메일 화면의 「발송 기록」 탭이 그리는 목록 (계획 3.3, D-512).
 *
 * 예전에는 최근 실패 10건만 볼 수 있었다. 이제 모든 발송을 상태 · 종류 · 받는 사람과 제목 검색 · 기간으로 거르고,
 * 한 통을 열어 잡의 다음 시도 시각과 보낸 메일의 Message-ID 를 보며, 끝난 메일은 다시 보내고 기다리는 메일은
 * 취소한다. 서버가 대기 · 다시 보내는 중인 행을 계속 바꾸므로 그런 행이 있으면 목록을 따라 읽는다.
 *
 * 이 설정은 REGISTRY 에 들지 않는다 — 메일 화면(`/mail`)의 탭 안에서만 선다(REGISTRY 키는 저마다 자기 주소를
 * 가져야 한다, `registry-surface-parity.test.js`). 정렬 키는 서버의 정렬 표(`sortKeys.json` 의 `mail-deliveries`)와
 * 같은 목록이다. */

export const MAIL_STATUS_LABEL = {
  queued: "발송 대기",
  retrying: "다시 보내는 중",
  sent: "발송됨",
  failed: "발송 실패",
  unconfigured: "발송 불가(설정 없음)",
  cancelled: "보내지 않음(취소)",
  superseded: "의미가 없어져 보내지 않음",
};

const STATUS_KIND = {
  queued: "info", retrying: "warn", sent: "ok", failed: "danger",
  unconfigured: "warn", cancelled: "neutral", superseded: "neutral",
};

export const MAIL_KIND_LABEL = {
  invite: "초대",
  password_reset: "비밀번호 재설정",
  approval_requested: "승인 요청",
  backup_failed: "백업 실패",
  test: "시험 메일",
};

const FAILURE_KIND_LABEL = {
  auth: "로그인 거부", tls: "보안 연결", sender: "보내는 사람 거부", recipient: "받는 사람 거부",
  rejected: "메일 서버 거절", connect: "연결 실패", temporary: "일시 거절", disconnected: "연결 끊김",
  render: "내용을 만들지 못함", config: "설정 없음", unknown: "알 수 없음",
};

/** 행에 고유한 까닭 한 줄 — 실패면 서버가 고른 요약, 보내지 않았으면 그 까닭. */
function reasonOf(r) {
  return r.skip_reason_label || r.error_summary || "-";
}

export const MAIL_DELIVERIES = {
  key: "mail-deliveries", area: "운영", title: "발송 기록", endpoint: "/api/admin/mail/deliveries",
  help: "이 포털이 보낸 메일과 보내지 못한 메일을 모두 봅니다. 실패한 메일은 다시 보낼 수 있고, 기다리는 메일은 취소할 수 있습니다.",
  emptyTitle: "보낸 메일이 없습니다",
  emptyHelp: "초대, 비밀번호 재설정, 승인 요청, 백업 실패 메일이 나가기 시작하면 여기에 쌓입니다.",
  selectKey: "delivery",
  paginated: true, pageSize: 50,
  searchable: true, searchPlaceholder: "받는 사람, 제목 검색",
  filters: [
    { key: "status", type: "select", label: "상태", options: opt(Object.entries(MAIL_STATUS_LABEL)) },
    { key: "kind", type: "select", label: "종류", options: opt(Object.entries(MAIL_KIND_LABEL)) },
    { key: "since", type: "date", label: "시작일", group: "other" },
    { key: "until", type: "date", label: "종료일", group: "other" },
  ],
  serverSort: { keys: ["created_at", "status", "kind", "to_email", "attempt_count"], default: { key: "created_at", dir: "desc" } },
  pollWhile: (r) => r.status === "queued" || r.status === "retrying",
  columns: [
    { ...dateCol("created_at", "발생"), sortable: true, rowName: (r) => (r.kind_label || r.kind) + " / " + (r.to_email || "") },
    { key: "kind", label: "종류", type: "enum", sortable: true, render: (r) => r.kind_label || MAIL_KIND_LABEL[r.kind] || r.kind },
    { key: "to_email", label: "받는 사람", type: "identifier", sortable: true },
    { key: "subject", label: "제목", type: "title" },
    {
      key: "status", label: "상태", type: "status", sortable: true,
      render: (r) => React.createElement(Badge, {
        value: r.status_label || MAIL_STATUS_LABEL[r.status] || r.status, kind: STATUS_KIND[r.status] || "neutral",
      }),
    },
    /* 실패한 횟수다(보낸 한 번은 세지 않는다) — 「시도」라고 부르면 보낸 메일도 0 이라 틀린 말이 된다. */
    { key: "attempt_count", label: "실패", type: "count", sortable: true },
    { key: "reason", label: "원인", type: "text", render: reasonOf },
  ],
  detailFields: [
    field("to_email", "받는 사람"),
    { key: "kind_detail", label: "종류", render: (r) => r.kind_label || MAIL_KIND_LABEL[r.kind] || r.kind },
    { key: "status_detail", label: "상태", render: (r) => r.status_label || MAIL_STATUS_LABEL[r.status] || r.status },
    { key: "reason_detail", label: "원인", render: reasonOf },
    { key: "failure_kind", label: "실패 종류", render: (r) => FAILURE_KIND_LABEL[r.failure_kind] || (r.failure_kind || "-") },
    { key: "attempts_detail", label: "실패 횟수", render: (r) => r.max_attempts != null ? r.attempt_count + " / " + r.max_attempts : String(r.attempt_count) },
    { key: "next_attempt", label: "다음 시도", render: (r) => (r.job && r.job.next_attempt_at ? fmtDateTimeCompact(r.job.next_attempt_at) : "-") },
    { key: "sent_at", label: "보낸 시각", render: (r) => (r.sent_at ? fmtDateTimeCompact(r.sent_at) : "-") },
    field("message_id", "Message-ID"),
    { key: "last_error_full", label: "기술 정보", render: (r) => (r.last_error ? React.createElement("pre", { className: "c-detail-json" }, String(r.last_error)) : "-") },
    field("id", "발송 ID"),
  ],
  actions: [
    { label: "다시 보내기", variant: "primary", roles: WRITE_ROLES, when: (r) => !!r.resendable,
      path: (r) => "/api/admin/mail/deliveries/" + r.id + "/resend", confirm: "이 메일을 다시 보낼까요? 보내기 직전에 아직 의미가 있는지 한 번 더 확인합니다." },
    { label: "취소", variant: "danger", roles: WRITE_ROLES, when: (r) => !!r.cancellable,
      path: (r) => "/api/admin/mail/deliveries/" + r.id + "/cancel", confirm: "보내기를 기다리는 이 메일을 취소할까요?" },
    { label: "감사 로그에서 보기", roles: ["admin", "system_admin"], navigate: (r) => "#/audit?object_type=mail_delivery&object_id=" + r.id },
  ],
};
