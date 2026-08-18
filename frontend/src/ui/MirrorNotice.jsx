import React from "react";
import Box from "@mui/material/Box";
import { Button, Callout } from "./kit.jsx";
import { fmtDateTime } from "../lib/format.js";

/* Notion 미러 상태 안내 — **조치가 필요할 때만** 나온다 (지시 1 · 29).
 *
 * ## 무엇이 문제였나
 *
 * 문서 목록과 팀 티켓 목록은 화면 맨 위에 "마지막 동기화: 2026. 8. 3. 오후 11:22, 문서
 * 104개" 를 상시로 띄웠다. 정상 동작을 매번 알리는 줄이라 사용자가 할 일이 없고, 그 옆의
 * '지금 동기화' 는 운영 동작인데 화면의 첫 번째 버튼 자리를 차지했다. 게다가 같은 컴포넌트가
 * `TeamDocs.SyncBanner` 와 `MyTickets.TicketSyncBanner` 로 두 벌 복제돼 있었다(필드 이름만
 * 달랐다) — 한쪽만 고쳐지는 날이 오는 구조다.
 *
 * ## 규칙
 *
 * - **실패** — 무엇이 보이고 있는지(마지막 정상 데이터) 알려야 하므로 경고로 낸다.
 * - **한 번도 성공 못 함** — "정말 0건" 과 "아직 못 재 봤다" 는 완전히 다른 사실이다(UB-26).
 *   목록이 비었을 때 이 구분이 없으면 화면이 조용히 거짓말을 한다.
 * - **정상** — 아무것도 그리지 않는다. 운영 상태는 관리자 화면이 맡는다(지시 67).
 * - **일부만 가져옴(`truncated`)** — 상태값은 ok 인데 숫자가 전체가 아니다. 조치가 필요하다.
 *
 * '지금 동기화' 는 실패했을 때의 **복구 동작**으로만 여기 남는다. 평상시 수동 동기화는
 * 화면 머리의 넘침 메뉴에 있다 — 기능은 그대로고 자리만 바뀐다(지시 50).
 */
export function MirrorNotice({ sync, canSync, onSync, syncing, unit = "항목" }) {
  if (!sync) return null;
  const failed = sync.status === "error";
  const never = !sync.last_success_at;
  /* `truncated` — 성공했지만 **일부만** 가져왔다. 상태값이 ok 라 위 두 갈래에 안 걸리는데,
     그 화면의 숫자는 전체가 아니다. 조치가 필요한 상태라 조용히 넘기지 않는다(예전에는
     Home.jsx 가 자기 문구로 이것만 따로 말했다). */
  const partial = !failed && !!sync.truncated;
  if (!failed && !never && !partial) return null;

  const count = sync.doc_count != null ? sync.doc_count : sync.ticket_count;
  const asOf = sync.last_success_at
    ? " (" + fmtDateTime(sync.last_success_at) + " 기준" + (count != null ? ", " + unit + " " + count + "개" : "") + ")."
    : ".";
  const text = failed
    ? "최근 동기화에 실패했습니다. 마지막 정상 데이터를 보고 있습니다" + asOf
    : partial
      ? "일부만 동기화됐습니다. 여기 숫자는 전체가 아닙니다" + asOf + " 관리자 확인이 필요합니다."
      : "아직 한 번도 동기화되지 않았습니다. 목록이 비어 있는 것은 " + unit + "이 없어서가 아니라 아직 가져오지 않았기 때문일 수 있습니다.";

  return (
    <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", flexWrap: "wrap", mb: 2.5 }}>
      <Box sx={{ flex: 1, minWidth: "16rem" }}>
        <Callout tone={(failed || partial) ? "warn" : "info"}>{text}</Callout>
      </Box>
      {canSync && onSync ? (
        <Button size="sm" onClick={onSync} disabled={syncing}>
          {syncing ? "동기화 중" : "지금 동기화"}
        </Button>
      ) : null}
    </Box>
  );
}
