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

/* 상태 조건의 낱말 — 서버의 `app/mail/labels.py::STATUS_FILTER_WORDS` 와 같은 표다(D-555). 행의 낱말은 서버가 그 행의 보내는 방식과
   바깥 전달 결과로 고른다(`status_label` — 「메일 서버가 접수함」 · 「로컬 릴레이가 접수함」 · 「수신측 메일 서버로 전달함」). 어느 낱말도
   「도착」 · 「받았습니다」가 아니다 - 접수는 받은 편지함이 아니다. */
export const MAIL_STATUS_LABEL = {
  queued: "보낼 차례",
  retrying: "다시 보낼 차례",
  sent: "서버가 접수함",
  failed: "보내지 못함",
  unconfigured: "설정이 끝나지 않아 보내지 못함",
  cancelled: "취소됨",
  superseded: "보내지 않음(의미가 없어짐)",
};

const STATUS_KIND = {
  queued: "info", retrying: "warn", sent: "info", failed: "danger",
  unconfigured: "warn", cancelled: "neutral", superseded: "neutral",
};

/* 종류 이름 — 서버의 `MAIL_KIND_LABELS` 와 같은 표다. 알림 메일도 종류다(예전에는 빠져 있어 조건으로 고를 수 없었다). */
export const MAIL_KIND_LABEL = {
  invite: "계정 초대",
  password_reset: "비밀번호 재설정",
  approval_requested: "승인 요청 알림",
  backup_failed: "백업 실패 알림",
  test: "시험 메일",
  notification: "알림 메일",
  notify_email_verification: "주소 확인 코드",
};

const FAILURE_KIND_LABEL = {
  auth: "로그인 거부", tls: "보안 연결", sender: "보내는 사람 거부", recipient: "받는 사람 거부",
  rejected: "메일 서버 거절", connect: "연결 실패", temporary: "일시 거절", disconnected: "연결 끊김",
  render: "내용을 만들지 못함", config: "설정 없음", unknown: "알 수 없음",
};

/* 로컬 릴레이로 넘긴 메일의 바깥 전달(D-551) — 서버가 고른 낱말(`relay.remote_label`)이다. 외부 SMTP 로 보낸 메일은 그 칸이 없다
   (「메일 서버가 접수함」이 제품이 아는 마지막 단계다, D-555). */
const REMOTE_KIND = { delivered: "ok", deferred: "warn", bounced: "danger", expired: "danger", queued: "info", unknown: "neutral" };
const REMOTE_VALUES = ["전달 대기", "전달 재시도 중", "수신측이 거부함", "전달 시간이 지남", "결과를 알 수 없음",
  "수신측 메일 서버로 전달함", "상위 SMTP 서버가 접수함"];

function remoteOf(r) {
  return r.relay && r.relay.remote_label ? r.relay.remote_label : null;
}

/** 행에 고유한 까닭 한 줄 — 실패면 서버가 고른 요약, 보내지 않았으면 그 까닭. */
function reasonOf(r) {
  return r.skip_reason_label || r.error_summary || "-";
}

export const MAIL_DELIVERIES = {
  key: "mail-deliveries", area: "운영", title: "발송 기록", endpoint: "/api/admin/mail/deliveries",
  help: "이 포털이 보낸 메일과 보내지 못한 메일을 모두 봅니다. 「서버가 접수함」은 다음 메일 서버가 받았다는 뜻이고 받은 편지함 도착은 아닙니다. 접수 뒤에 오는 반송 메일은 보내는 주소의 메일함으로 갑니다.",
  emptyTitle: "아직 보낸 메일이 없습니다.",
  emptyHelp: "초대, 비밀번호 재설정, 승인 요청, 백업 실패, 알림 메일이 나가기 시작하면 여기에 쌓입니다.",
  selectKey: "delivery",
  paginated: true, pageSize: 50,
  searchable: true, searchPlaceholder: "받는 사람, 제목 검색",
  filters: [
    { key: "status", type: "select", label: "상태", options: opt(Object.entries(MAIL_STATUS_LABEL)) },
    { key: "kind", type: "select", label: "종류", options: opt(Object.entries(MAIL_KIND_LABEL)) },
    /* 기간 칸 하나(D-530). 서버는 날짜를 KST 달력일로 읽고(`app/core/dates.py::parse_kst_boundary`) 빈 값은 전체다. */
    { key: "since", endKey: "until", type: "period", label: "기간" },
  ],
  serverSort: { keys: ["created_at", "status", "kind", "to_email", "attempt_count"], default: { key: "created_at", dir: "desc" } },
  pollWhile: (r) => r.status === "queued" || r.status === "retrying",
  columns: [
    { ...dateCol("created_at", "발생"), sortable: true, rowName: (r) => (r.kind_label || r.kind) + " / " + (r.to_email || "") },
    { key: "kind", label: "종류", type: "enum", sortable: true, values: Object.values(MAIL_KIND_LABEL), render: (r) => r.kind_label || MAIL_KIND_LABEL[r.kind] || r.kind },
    { key: "to_email", label: "받는 사람", type: "identifier", sortable: true },
    { key: "subject", label: "제목", type: "title" },
    {
      key: "status", label: "상태", type: "status", sortable: true,
      values: [...Object.values(MAIL_STATUS_LABEL), "메일 서버가 접수함", "로컬 릴레이가 접수함", "수신측 메일 서버로 전달함"],
      render: (r) => React.createElement(Badge, {
        value: r.status_label || MAIL_STATUS_LABEL[r.status] || r.status,
        kind: r.status_kind || STATUS_KIND[r.status] || "neutral",
      }),
    },
    {
      key: "remote", label: "바깥 전달", type: "status", tier: "secondary", values: REMOTE_VALUES,
      value: (r) => remoteOf(r) || "-",
      render: (r) => (remoteOf(r)
        ? React.createElement(Badge, { value: remoteOf(r), kind: REMOTE_KIND[r.relay.remote_status] || "neutral" })
        : "-"),
    },
    /* 실패한 횟수다(보낸 한 번은 세지 않는다) — 「시도」라고 부르면 보낸 메일도 0 이라 틀린 말이 된다. */
    /* 받는 사람 · 종류 · 상태 · 시각(과 제목)이 필수다. 실패 횟수 · 원인은 보조라 좁으면 숨고, 행을 열면 상세가 보인다(D-529). */
    { key: "attempt_count", label: "실패", type: "count", sortable: true, tier: "secondary", render: (r) => String(r.failures ?? r.attempt_count ?? 0) },
    { key: "reason", label: "원인", type: "text", tier: "secondary", render: reasonOf },
  ],
  detailFields: [
    field("to_email", "받는 사람"),
    { key: "kind_detail", label: "종류", render: (r) => r.kind_label || MAIL_KIND_LABEL[r.kind] || r.kind },
    { key: "status_detail", label: "상태", render: (r) => r.status_label || MAIL_STATUS_LABEL[r.status] || r.status },
    { key: "reason_detail", label: "원인", render: reasonOf },
    {
      key: "remote_detail", label: "바깥 전달",
      render: (r) => (r.relay
        ? [remoteOf(r) || "-", r.relay.remote_sentence, r.relay.remote_checked_at ? "최근 확인 " + fmtDateTimeCompact(r.relay.remote_checked_at) : null]
          .filter(Boolean).join(" ")
        : "외부 SMTP로 보냈습니다. 메일 서버가 접수한 뒤의 일은 추적하지 않습니다."),
    },
    { key: "failure_kind", label: "실패 종류", render: (r) => FAILURE_KIND_LABEL[r.failure_kind] || (r.failure_kind || "-") },
    { key: "failure_stage", label: "실패 단계", render: (r) => r.failure_stage_label || "-" },
    /* 이번 회차의 시도 수와 상한은 잡이 말하고, 누적 실패는 행이 말한다 - 재발송해도 「10 / 8」이 되지 않는다. */
    {
      key: "attempts_detail", label: "시도",
      render: (r) => [
        r.job && r.job.max_attempts ? "이번 회차 시도 " + r.job.attempt_count + "/" + r.job.max_attempts : null,
        "누적 실패 " + (r.failures ?? r.attempt_count ?? 0) + "회",
      ].filter(Boolean).join(", "),
    },
    { key: "next_attempt", label: "다음 시도", render: (r) => (r.job && r.job.next_attempt_at ? fmtDateTimeCompact(r.job.next_attempt_at) : "-") },
    { key: "sent_at", label: "보낸 시각", render: (r) => (r.sent_at ? fmtDateTimeCompact(r.sent_at) : "-") },
    field("message_id", "Message-ID"),
    /* 다음 서버의 응답 한 줄(접수면 「250 … queued as …」, 거절이면 그 코드)과 예외 원문은 기술 정보다. */
    {
      key: "last_error_full", label: "기술 정보",
      render: (r) => (r.last_error || r.relay_response || (r.relay && r.relay.remote_detail)
        ? React.createElement("pre", { className: "c-detail-json" }, [
          r.relay_response ? "서버 응답: " + r.relay_response : null,
          r.relay && r.relay.queue_id ? "릴레이 큐 id: " + r.relay.queue_id : null,
          r.relay && r.relay.remote_detail ? "받는 쪽 응답: " + r.relay.remote_detail : null,
          r.last_error,
        ].filter(Boolean).join("\n"))
        : "-"),
    },
    field("id", "발송 ID"),
  ],
  actions: [
    { label: "다시 보내기", variant: "primary", roles: WRITE_ROLES, when: (r) => !!r.resendable,
      path: (r) => "/api/admin/mail/deliveries/" + r.id + "/resend", confirm: "이 메일을 다시 보낼까요? 보내기 직전에 아직 의미가 있는지 한 번 더 확인합니다." },
    { label: "취소", variant: "danger", roles: WRITE_ROLES, when: (r) => !!r.cancellable,
      path: (r) => "/api/admin/mail/deliveries/" + r.id + "/cancel", confirm: "보내기를 기다리는 이 메일을 취소할까요?" },
    /* 큐에 남은 메일을 지금 다시 보내게 한다(로컬 릴레이, 메일 설정 권한). 이 메일만이 아니라 큐 전체다 - 확인 문장이 그것을 말한다. */
    { label: "지금 다시 보내기", roles: ["system_admin"], when: (r) => !!(r.relay && r.relay.flushable),
      path: () => "/api/admin/mail/relay/flush",
      confirm: "로컬 릴레이의 큐에 남은 메일을 지금 다시 보낼까요? 이 메일만이 아니라 큐에 남은 메일을 모두 다시 시도합니다." },
    { label: "감사 로그에서 보기", roles: ["admin", "system_admin"], navigate: (r) => "#/audit?object_type=mail_delivery&object_id=" + r.id },
  ],
};
