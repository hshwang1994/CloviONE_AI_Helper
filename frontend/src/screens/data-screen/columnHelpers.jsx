import React from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import { Badge } from "../../ui/kit.jsx";
import { fmtDateTime } from "../../lib/format.js";
import { JsonBlock, KeyValueRow } from "./JsonBlock.jsx";

// 열/필드 렌더 헬퍼 — registry에서 사용.
export const badgeCol = (key, label) => ({ key, label, render: (r) => <Badge value={r[key]} /> });
export const mapCol = (key, label, map) => ({ key, label, render: (r) => map[r[key]] || (r[key] == null ? "-" : String(r[key])) });
export const dateCol = (key, label) => ({ key, label, render: (r) => fmtDateTime(r[key]) });
// 사용 여부(boolean) → 도메인 어휘 배지('사용 중'/'미사용'). 일반 badgeCol의 '예/아니오'는
// 같은 화면의 필터('사용 중'/'미사용')·체크박스 어휘와 어긋나므로 이 렌더로 통일한다.
// 미사용(active=false)은 이 화면이 관리하는 핵심 상태(새로 배정 가능 여부를 가른다)라 눈에 잘
// 안 띄는 중립(neutral) 톤 대신 주의(warn) 톤을 준다 — 훑어보다 놓치기 쉬웠다.
export const activeCol = (label) => ({ key: "active", label, render: (r) => <Badge value={r.active ? "사용 중" : "미사용"} kind={r.active ? "ok" : "warn"} /> });
// 켬/꺼짐(boolean) → 도메인 어휘 배지('활성'/'비활성'). activeCol과 같은 이유(VIS-13):
// 일반 badgeCol의 '예/아니오'는 화면 필터의 '활성'/'비활성' 어휘와 어긋나고, 꺼짐이 중립(회색)
// 톤이라 훑어보다 놓치기 쉬웠다 — 스케줄·연동·러너·워크플로 4곳이 이 패턴이 필요했다.
export const enabledCol = (label) => ({ key: "enabled", label, render: (r) => <Badge value={r.enabled ? "활성" : "비활성"} kind={r.enabled ? "ok" : "warn"} /> });
// 외부 링크 열(예: 발행된 Notion 문서) — http(s) URL만 앵커로, 그 외엔 평문(CSP상 앵커는 안전).
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
  const links = Array.isArray(p.notion_links) ? p.notion_links : [];
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
