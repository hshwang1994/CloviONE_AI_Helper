import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { fmtDateTime, fmtListStamp } from "../../lib/format.js";
import {
  Button, Callout, Card, DotLabel, FACTS_ROW_SX, FormSection, HeadRow, MetaBar, TechDetail, TechRows,
} from "../../ui/kit.jsx";
import { SettingRow } from "../../ui/adminKit.jsx";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";

/* AI 연결의 ① 현재 상태 면과 ⑥ 「확인과 오류」 구획 (계획 A3 · M4, D-539 · D-558 · D-574).
 *
 * 화면은 여섯 구획이다 — ① 현재 상태(이 면, 화면에서 카드는 이것과 그 아래 설정 판 둘) ② 제공자와 인증 ③ 모델 ④ 실행 옵션
 * ⑤ AI 기능 ⑥ 확인과 오류. 상태를 읽는 자리(①)와 확인을 하는 자리(⑥)를 가른다: 예전에는 [지금 확인] 이 상태 면 머리에 있고
 * 최근 확인 · 최근 성공 시각은 띠와 기술 정보에 흩어져 있어, 「언제 확인했고 왜 막혔는가」를 한 곳에서 읽을 수 없었다.
 *
 * ① 은 대시보드가 아니다: 상태 점과 낱말, 한 문장, 「다음 할 일」 한 문장과 그 자리로 가는 단추(`next`), **서버가 준 사실 띠**
 * (`facts[]` — 자격이 없으면 제공자 · 인증 방식뿐이고 모델 · 능력 줄은 없다), 연결에 딸린 기술 정보. 낱말과 문장은 서버가 정한다
 * (`state.display` — 초기 설정의 AI 항목과 같은 함수). 이 화면은 어떤 사실도 지어내지 않는다 — 「문서 검색 사용 가능」 같은
 * 고정 문구를 그리지 않는다.
 *
 * ⑥ 은 확인의 자리다: 최근 확인 시각과 이 화면의 **하나뿐인** [지금 확인], 최근 성공 시각, 막힌 까닭(메시지 상자 하나), 이 화면의
 * 저장 실패, 상태 · 까닭 코드 같은 원시 값. 막힌 까닭은 ⑥ 에만 선다 — ① 은 낱말과 다음 할 일로 말하고 같은 문장을 두 번 쓰지
 * 않는다(D-501, 한 사실은 한 곳).
 */

export const KIND_TONE = { ok: "ok", info: "info", warn: "warn", error: "danger", muted: "neutral" };
/* 「다음 할 일」 단추의 글. 자리는 서버의 `next.action` 이고 모양은 화면이 정한다. 확인(`verify`)은 ⑥ 의 [지금 확인] 이 하나뿐인
   자리라 여기서 단추를 만들지 않는다. */
export const NEXT_BUTTON = {
  configure: "제공자 정하기",
  api_key: "API 키 넣기",
  login: "ChatGPT 로그인",
  paste: "주소 붙여 넣기",
  model: "모델 고르기",
  enable: "AI 사용 활성화",
};
/* 최근 성공 · 최근 확인 시각은 ⑥ 의 줄이다 — ① 의 띠에 한 번 더 세우지 않는다(D-501). 서버 사실의 **자리**만 고르고 글은 바꾸지
   않는다. */
const CHECK_FACTS = new Set(["last_success", "checked"]);

/* 띠에는 짧은 꼴(「3분 전」 · 「8월 24일」)을 쓴다 — 「2026. 10. 2. 오전 11:00」 둘이 띠를 1366 에서 두 줄로 접어 첫 폼 칸을 밀었다(P17V).
   정확한 시각은 ⑥ 의 줄에 있다. */
function when(iso) {
  return iso ? fmtListStamp(iso) : "아직 없음";
}

function displayOf(state) {
  return state.display || { label: state.label || "알 수 없음", kind: "muted", message: state.message || "" };
}

function blockedKind(display) {
  return display.kind === "error" || display.kind === "warn";
}

/* 값이 있는 기술 줄이 하나라도 있을 때만 「기술 정보」 접기를 세운다 — 빈 접기는 눌러도 아무것도 없는 글이다. */
function TechFold({ rows, trailing = false }) {
  const present = rows.filter(([, value]) => value != null && value !== "" && value !== false);
  if (!present.length) return null;
  return (
    <TechDetail trailing={trailing}>
      <TechRows rows={present} />
    </TechDetail>
  );
}

/* 의미 검색 한 줄 — 서버가 지은 낱말(`index.embed_status_label`)이 있으면 그 글이고, 없으면 예전 낱말(있음 · 없음)이다. 화면이
   상태를 짓지 않는다. */
/* 색인 한 줄 — 문서 수는 `documents_total`(새 응답) 또는 숫자 `documents`(옛 응답)다. 새 응답의 `documents` 는 상태별 수
   `{pending, ok, failed}` 라 그대로 글자에 넣으면 「[object Object]건」이 섰다. 의미 검색이 켜져 있으면 벡터가 붙은 조각 수를 함께 쓴다. */
export function indexText(index) {
  if (!index) return null;
  const total = typeof index.documents_total === "number" ? index.documents_total
    : (typeof index.documents === "number" ? index.documents : null);
  if (total == null) return null;
  const chunks = typeof index.chunks === "number" ? index.chunks : 0;
  const parts = [`${total}건`, `조각 ${chunks}개`];
  if (index.semantic && typeof index.embedded === "number") parts.push(`의미 검색에 쓰는 조각 ${index.embedded}/${chunks}개`);
  return parts.join(", ");
}

/* 문서별 색인 상태 — 새 응답의 `documents{pending, ok, failed}`. 옛 응답(숫자)에는 없다. */
export function indexStateText(index) {
  const d = index && index.documents;
  if (!d || typeof d !== "object") return null;
  return `처리됨 ${d.ok ?? 0}건, 기다림 ${d.pending ?? 0}건, 실패 ${d.failed ?? 0}건`;
}

export function semanticText(index) {
  if (!index) return null;
  if (index.embed_status_label) return index.embed_status_label;
  if (index.semantic == null) return null;
  return index.semantic ? "있음" : "없음(낱말로 찾습니다)";
}

export function AiStatusCard({ data, onNext, timedOut = false }) {
  const state = data.state || {};
  const display = displayOf(state);
  const config = data.config || {};
  const next = data.next || null;
  const technical = data.technical || {};
  const index = data.index;
  const facts = (data.facts || []).filter((f) => !CHECK_FACTS.has(f.key)).map((f) => ({
    key: f.key, label: f.label, value: f.kind === "time" ? when(f.value) : f.value,
  }));
  /* 막힌 까닭은 ⑥ 의 메시지 상자가 말한다. 다음 할 일이 상태 문장과 같은 말이면 머리에는 낱말만 둔다 - 같은 문장을 두 번 쓰지
     않는다. */
  const headMessage = !blockedKind(display) && display.message && !(next && next.label === display.message)
    ? display.message : null;
  const nextButton = next && onNext && NEXT_BUTTON[next.action] ? NEXT_BUTTON[next.action] : null;
  const hint = index && index.embed_hint && index.embed_status !== "ok" ? (
    <Typography variant="body2" color="text.secondary" data-testid="ai-embed-hint" sx={KO_WORD_BREAK}>{index.embed_hint}</Typography>
  ) : null;
  return (
    <Card stack data-testid="ai-state" aria-label="AI 연결 상태">
      {/* 구획 제목과 상태 낱말이 한 줄이다 — 상태 면은 짧아야 한다(F7, 높이 상한 약 120px). 제목을 따로 한 줄 세우면 첫 폼 칸이
          1366 첫 화면 기준(420px) 아래로 밀린다. */}
      <HeadRow>
        <Box sx={{ display: "flex", alignItems: "baseline", columnGap: 1.25, rowGap: 0.5, flexWrap: "wrap", minWidth: 0 }}>
          <Typography component="h2" variant="sectionTitle">현재 상태</Typography>
          <DotLabel label={display.label} tone={KIND_TONE[display.kind] || "neutral"} strong data-testid="ai-state-label" />
          {headMessage ? (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{headMessage}</Typography>
          ) : null}
        </Box>
      </HeadRow>
      {/* 「다음 할 일」은 제목 줄 없이 한 줄(굵은 꼬리표 + 문장)이다 — 동작이 든 상자의 계약(D-528: 아이콘 · 첫 줄 · 동작이 한
          가운데선)은 제목 줄을 세지 않는다. 제목을 따로 세우면 단추가 두 줄 상자의 가운데에 떠서 kit_measure 의 callout 검사가
          걸렸다(캡처 m4-2, 메일 설정의 「지금 할 일」과 같은 모양). */}
      {next ? (
        <Callout
          tone="info" compact className="k-ai-next"
          action={nextButton ? (
            <Button size="sm" variant="primary" onClick={() => onNext(next.action)}>
              {nextButton}
            </Button>
          ) : null}
        >
          <Typography component="span" variant="body2" sx={KO_WORD_BREAK}>
            <Box component="strong" sx={{ fontWeight: FONT_WEIGHT.semibold, mr: 0.75 }}>다음 할 일</Box>
            {next.label}
          </Typography>
        </Callout>
      ) : null}
      {timedOut ? (
        <Callout tone="info" compact>확인이 시간 안에 끝나지 않았습니다. 잠시 뒤 다시 확인하세요.</Callout>
      ) : null}
      {/* 의미 검색을 켜는 길은 서버에서 하는 일이다 — 서버가 지은 한 문장(`embed_hint`)을 단추 없이 글로만 둔다. 화면이 명령을 짓지
          않는다. 의미 검색이 이미 켜져 있으면 서지 않는다. 사실 띠가 비면 그 줄의 빈 왼쪽에 서서 줄을 하나 아낀다(첫 폼 칸이 1920
          첫 화면 440 아래로 밀렸다, 캡처 m4-5 first_data_visible). */}
      {hint && facts.length ? hint : null}
      {/* 칸마다 이름과 값이 한 줄에 붙는 띠다. 「기술 정보」는 그 띠 끝에 접혀 붙고, 연결에 딸린 값(프록시 · 계정 · 토큰 · 색인)만
          든다 — 확인의 원시 값은 ⑥ 의 기술 정보에 있다. */}
      <Box sx={FACTS_ROW_SX}>
        {facts.length ? (
          <MetaBar strip items={facts} ariaLabel="지금 쓰는 연결" sx={{ flex: "1 1 auto", minWidth: 0 }} />
        ) : (
          <Box sx={{ flex: "1 1 auto", minWidth: 0 }}>{hint}</Box>
        )}
        <TechFold
          trailing
          rows={[
            ["프록시", technical.proxy],
            ["연결한 계정", technical.account_label],
            ["토큰 만료", technical.access_expires_at ? fmtDateTime(technical.access_expires_at) : null],
            ["갱신 토큰 만료", technical.refresh_expires_at ? fmtDateTime(technical.refresh_expires_at) : null],
            ["색인 문서", indexText(index)],
            ["색인 상태", indexStateText(index)],
            ["의미 검색", semanticText(index)],
            ["의미 검색 상태 코드", index ? index.embed_status : null],
            ["요금제 사용량", data.chatgpt && data.chatgpt.manage_usage_url && config.auth_method === "chatgpt" ? data.chatgpt.manage_usage_url : null],
          ]}
        />
      </Box>
    </Card>
  );
}

/* ⑥ 확인과 오류 — 설정 판의 마지막 구획이다(머리와 1px 선으로 나뉘고 카드를 두르지 않는다, F7).
 *
 * [지금 확인] 은 이 화면에 하나뿐이다. 다음 할 일이 확인이면 그 단추가 화면의 주 동작(채움)이 된다 — ① 의 다음 할 일 상자는 그때
 * 단추를 세우지 않으므로 채움이 둘이 되지 않는다. 확인할 수 없으면(자격 · 모델이 없다) 꺼진 채로 서고 까닭은 줄 설명이 말한다. */
export function AiChecks({ data, onVerify, verifying = false, problem = null, titleId }) {
  const state = data.state || {};
  const display = displayOf(state);
  const config = data.config || {};
  const credentials = data.credentials || { ready: false };
  const next = data.next || null;
  const technical = data.technical || {};
  const canVerify = Boolean(credentials.ready && config.model);
  const primary = Boolean(canVerify && next && next.action === "verify");
  return (
    <FormSection titleAs="h2" title={<span id={titleId}>확인과 오류</span>}>
      <Box data-testid="ai-checks" sx={{ minWidth: 0 }}>
        <SettingRow
          label="최근 확인"
          value={state.checked_at ? fmtDateTime(state.checked_at) : "아직 없음"}
          tone={state.checked_at ? undefined : "muted"}
          description={canVerify
            ? "고른 모델로 짧은 답을 실제로 받아 연결을 확인합니다."
            : "제공자를 연결하고 모델을 고르면 확인할 수 있습니다."}
          action={(
            <Button
              variant={primary ? "primary" : undefined} onClick={onVerify} loading={verifying}
              disabled={!canVerify || verifying}
            >
              연결 확인
            </Button>
          )}
        />
        <SettingRow
          last label="최근 성공"
          value={state.last_success_at ? fmtDateTime(state.last_success_at) : "아직 없음"}
          tone={state.last_success_at ? undefined : "muted"}
        />
      </Box>
      {blockedKind(display) && display.message ? (
        <Callout tone={display.kind === "error" ? "danger" : "warn"} compact className="k-ai-reason">{display.message}</Callout>
      ) : null}
      {problem ? <Callout tone="danger" compact>{problem}</Callout> : null}
      <TechFold
        rows={[
          ["연결 상태 코드", state.state],
          ["까닭 코드", technical.reason_code],
          ["연속 실패", technical.consecutive_failures ? `${technical.consecutive_failures}회` : null],
          ["도구 시험 모델", technical.tools_checked_model],
          ["도구 시험 시각", (data.capabilities || {}).checked_at ? fmtDateTime(data.capabilities.checked_at) : null],
        ]}
      />
    </FormSection>
  );
}

export default AiStatusCard;
