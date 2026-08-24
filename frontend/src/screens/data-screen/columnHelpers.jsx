import React from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import { Badge } from "../../ui/kit.jsx";
import { DateCell } from "../../ui/cells.jsx";
import { JsonBlock, KeyValueRow } from "./JsonBlock.jsx";

// 열/필드 렌더 헬퍼 — registry에서 사용.
export const badgeCol = (key, label) => ({ key, label, render: (r) => <Badge value={r[key]} /> });
export const mapCol = (key, label, map) => ({ key, label, render: (r) => map[r[key]] || (r[key] == null ? "-" : String(r[key])) });
/* 표의 날짜는 한 줄로 고정한다 — 접히면 행 높이가 들쭉날쭉해 세로로 훑을 수 없다(지시 16).
 *
 * 날짜 열은 **정렬 대상이다**(지시 10). "언제 추가됐나 / 무엇이 가장 오래됐나"는 목록에서
 * 가장 자주 묻는 질문이고, 화면에 보이는 압축 표기(`2026-08-18 15:33`)가 아니라 **원본 ISO**
 * 로 비교한다 — 표기 문자열로 비교하면 오전/오후 같은 지역 표기에 순서가 끌려간다.
 * 정렬 UI 를 실제로 그릴지는 `DataScreen` 이 정한다(서버가 페이지를 자르는 목록에는 안 붙인다). */
export const dateCol = (key, label) => ({
  key, label, nowrap: true, sortable: true, sortValue: (r) => r[key],
  render: (r) => <DateCell value={r[key]} />,
});
// 사용 여부(boolean) → 도메인 어휘 배지('사용 중'/'미사용'). 일반 badgeCol의 '예/아니오'는
// 같은 화면의 필터('사용 중'/'미사용')·체크박스 어휘와 어긋나므로 이 렌더로 통일한다.
// 미사용(active=false)은 이 화면이 관리하는 핵심 상태(새로 배정 가능 여부를 가른다)라 눈에 잘
// 안 띄는 중립(neutral) 톤 대신 주의(warn) 톤을 준다 — 훑어보다 놓치기 쉬웠다.
export const activeCol = (label) => ({ key: "active", label, render: (r) => <Badge value={r.active ? "사용 중" : "미사용"} kind={r.active ? "ok" : "warn"} /> });
// 켬/꺼짐(boolean) → 도메인 어휘 배지('활성'/'비활성'). activeCol과 같은 이유(VIS-13):
// 일반 badgeCol의 '예/아니오'는 화면 필터의 '활성'/'비활성' 어휘와 어긋나고, 꺼짐이 중립(회색)
// 톤이라 훑어보다 놓치기 쉬웠다 — 스케줄·연동·러너·워크플로 4곳이 이 패턴이 필요했다.
export const enabledCol = (label) => ({ key: "enabled", label, render: (r) => <Badge value={r.enabled ? "활성" : "비활성"} kind={r.enabled ? "ok" : "warn"} /> });
/* 요구사항 boolean → **평문**. 상태가 아니라 성질이라 배지를 주지 않는다(지시 11).
 *
 * `badgeCol("approval_required")` 는 원시 boolean 이 statusText 를 타 `아니요` 라는 알약이
 * 됐다 — 지시 11 이 이름까지 들어 지적한 그 알약이다. 표 한 줄에 상태 알약과 성질 알약이
 * 나란히 있으면 무엇이 지금 벌어지는 일이고 무엇이 이 항목의 성질인지 구분되지 않는다.
 * 단순 텍스트가 맞는 곳에서는 배지를 뺀다. */
export const boolCol = (key, label, yes, no) => ({
  key, label, render: (r) => (r[key] ? yes : no),
});
// 외부 링크 열 - http(s) URL만 앵커로, 그 외엔 평문(CSP상 앵커는 안전).
export const linkCol = (key, label) => ({ key, label, render: (r) => {
  const v = r[key];
  if (v == null || v === "") return "-";
  const s = String(v);
  return /^https?:\/\//i.test(s) ? <Link href={s} target="_blank" rel="noopener noreferrer" underline="hover">{s}</Link> : s;
} });
// 긴 문자열을 목록에서 말줄임(…)으로 자르되, title 속성으로 전체 텍스트를 마우스 오버 시 볼 수
// 있게 한다(예전엔 '길면 말줄임, title 속성으로 전체 확인'이라는 주석만 있고 실제 title이 없었다).
export const truncateCol = (key, label, max) => ({ key, label, render: (r) => {
  const v = r[key];
  if (v == null || v === "") return "-";
  const s = String(v);
  return s.length > max ? <span title={s}>{s.slice(0, max) + "…"}</span> : s;
} });
// 읽음 여부 — nullable 타임스탬프를 읽음/안읽음 배지로(원시 시각 노출 방지).
export const readCol = (key, label) => ({ key, label, render: (r) => <Badge value={r[key] ? "읽음" : "안읽음"} kind={r[key] ? "neutral" : "warn"} /> });
// 상세 전용: 객체/JSON 값을 보기 좋게 펼쳐 보여준다(정책 규칙·승인 payload·감사 전후 등).
export const jsonField = (key, label) => ({ key, label, render: (r) => {
  const v = r[key];
  // 빈 객체/배열({}/[])도 '값 없음'으로 취급한다, 서버 기본값이 default_factory=dict인 필드(예:
  // 연동의 capabilities)는 문자열 "{}"로 JSON.stringify되어 <pre> 블록 안에 그대로 보였다(listField가
  // 이미 빈 배열을 '-'로 처리하는 것과 동일한 대우로 맞춘다).
  if (v == null || v === "" || (typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 0) || (Array.isArray(v) && v.length === 0)) return "-";
  const text = typeof v === "string" ? v : JSON.stringify(v, null, 2);
  return <JsonBlock>{text}</JsonBlock>;
} });
// 상세 전용: 객체(예: 승인 요청 내용 request_payload)를 최상위 키/값 행으로 펼쳐 읽기 쉽게 보여준다.
// '내용 없이 승인 금지' 원칙을 위해, 원시 JSON 한 덩어리 대신 각 필드를 라벨로 분해한다. 중첩 객체·
// 배열은 들여쓴 JSON으로 보여준다. 서버 데이터는 JSX 텍스트로만 렌더(textContent 상당) — CSP/XSS 안전.
export const objectField = (key, label) => ({ key, label, render: (r) => {
  const v = r[key];
  if (v == null || v === "") return "-";
  if (typeof v !== "object") return <JsonBlock>{String(v)}</JsonBlock>;
  const entries = Array.isArray(v) ? v.map((x, i) => [String(i), x]) : Object.entries(v);
  if (!entries.length) return "-";
  return (
    <div>
      {entries.map(([k, val], i) => (
        <KeyValueRow label={k} key={i}>
          <Box component="span">{val != null && typeof val === "object"
            ? <JsonBlock>{JSON.stringify(val, null, 2)}</JsonBlock>
            : (val == null || val === "" ? "-" : String(val))}</Box>
        </KeyValueRow>
      ))}
    </div>
  );
} });
// 상세 전용: 문자열 배열을 읽기 쉬운 목록으로(품질 문제 등). 배열이 아니면 JSON으로.
export const listField = (key, label) => ({ key, label, render: (r) => {
  const v = r[key];
  if (v == null || v === "" || (Array.isArray(v) && v.length === 0)) return "-";
  if (Array.isArray(v)) return <ul>{v.map((x, i) => <li key={i}>{typeof x === "string" ? x : JSON.stringify(x)}</li>)}</ul>;
  return <JsonBlock>{typeof v === "string" ? v : JSON.stringify(v, null, 2)}</JsonBlock>;
} });
// 상세 전용: 문서 미리보기를 읽을 수 있게(제목·본문·행수·링크). 본문을 JSON 문자열로 뭉개지 않는다.
// 서버 데이터는 JSX 텍스트로만 렌더(textContent 상당) — innerHTML 미사용(XSS/CSP 안전).
export const previewField = (key, label) => ({ key, label, render: (r) => {
  const p = r[key];
  if (p == null || p === "") return "-";
  if (typeof p === "string") return <JsonBlock>{p}</JsonBlock>;
  /* 여기 미리보기의 외부 링크 목록(`p.notion_links`)을 앵커로 그리는 줄이 있었다. 서버가
     그 필드를 싣는 경로가 없다 - 서버가 안 보내는 필드를 화면이 계속 기다리면, 다음
     사람은 그 코드를 보고 기능이 있다고 읽는다. */
  const links = [];
  return (
    <div>
      {p.title ? <div><strong>{String(p.title)}</strong></div> : null}
      {p.body != null && p.body !== "" ? <JsonBlock>{String(p.body)}</JsonBlock> : null}
      {p.source_row_count != null ? <div>원본 행 수: {String(p.source_row_count)}</div> : null}
      {links.length ? <div>{links.map((l, i) => { const s = String(l); return /^https?:\/\//i.test(s)
        ? <Link key={i} href={s} target="_blank" rel="noopener noreferrer" underline="hover">{s} </Link>
        : <span key={i}>{s} </span>; })}</div> : null}
    </div>
  );
} });
