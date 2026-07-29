import React from "react";

/* ClovirONE 공통 UI 키트 — 디자인 토큰 위에서 카드/배지/버튼/상태/빈 화면/스켈레톤을
 * 한 규칙으로 그린다. 색은 토큰만, 인라인 스타일 없음(CSP). 왼쪽 파란 선 모티프를
 * 데이터 카드에 반복하지 않는다(§7). */

// 상태 원본값 → 한국어 표시 + 톤(색은 톤으로만). 바닐라 common.js와 같은 어휘.
const STATUS_TEXT = {
  up: "정상", down: "중단", stale: "응답 없음", degraded: "성능 저하", ok: "정상",
  active: "사용 중", enabled: "활성화", disabled: "비활성화", verified: "확인됨",
  unmapped: "미연결", unknown: "알 수 없음", processing: "처리 중", running: "실행 중",
  queued: "대기 중", succeeded: "완료", success: "성공", failed: "실패", failure: "실패",
  error: "오류", conflict: "충돌", pending: "대기", approved: "승인됨", rejected: "거절됨",
  expired: "만료", cancelled: "취소됨", published: "발행됨", draft: "초안", read: "읽기",
  write: "쓰기", maintenance: "점검", normal: "정상", awaiting_approval: "승인 대기",
  quality_failed: "품질 미달", passed: "통과", not_run: "미실행", untested: "미검증",
  // 문서 화면 상태 필터 라벨('미리보기 완료')과 같은 값이라 배지도 같은 말을 쓴다(어긋나면 필터 결과가 배지와 안 맞아 보인다).
  preview_ready: "미리보기 완료", skipped: "건너뜀",
  // 라이프사이클 중간 상태(프롬프트·정책·템플릿) — 한국어 표시가 없으면 원시 영어가 새어 나온다.
  test: "테스트", review: "검토", archived: "보관됨",
  // 워크플로 테스트 도달성 — reachable/unreachable가 매핑되지 않으면 영어 그대로 회색으로 뜬다.
  reachable: "연결됨", unreachable: "연결 안 됨",
  // secret_ref 상태(연동·러너 배지) — 매핑 없으면 영어 'configured'/'missing'이 회색으로 샌다.
  configured: "등록됨", missing: "없음",
  // Notion 티켓 워크플로 상태(채팅 결과 카드) — 관리자 상태 어휘엔 없어 영어/무채색으로 뜨던 값들.
  "Not started": "시작 전", "In progress": "진행 중", "Done": "완료", "Todo": "할 일",
  "시작 전": "시작 전", "진행 중": "진행 중", "완료": "완료", "할 일": "할 일",
  // 조직마다 Notion 보드에서 흔히 쓰는 그 밖의 상태값 — 위 4종만 있으면 실제 워크스페이스가
  // 쓰는 'In Review'/'Blocked' 등이 여전히 원시 영어로 새어 나온다.
  "In Review": "검토 중", "Blocked": "막힘", "Cancelled": "취소됨", "On Hold": "보류",
  "Backlog": "백로그", "검토 중": "검토 중", "막힘": "막힘", "보류": "보류", "백로그": "백로그",
  // 이 워크스페이스 작업 DB의 실제 진행상태 6종(채팅 티켓 카드·배지) — 원시 그대로 통과하지만 명시해 둔다.
  "계획": "계획", "이슈": "이슈", "검증": "검증", "진행": "진행", "취소": "취소",
};
const STATUS_KIND = {
  up: "ok", verified: "ok", succeeded: "ok", success: "ok", published: "ok", active: "ok",
  enabled: "ok", approved: "ok", ok: "ok", normal: "ok", passed: "ok", reachable: "ok",
  "true": "ok",
  down: "danger", failed: "danger", failure: "danger", error: "danger", conflict: "danger", rejected: "danger",
  unreachable: "danger",
  degraded: "warn", stale: "warn", pending: "warn", queued: "warn", awaiting_approval: "warn",
  quality_failed: "warn", write: "warn", review: "warn", missing: "warn",
  // Notion 매핑 화면의 'unmapped'는 이 화면 존재 이유인 실행 가능한 상태다 — missing과 같은
  // 톤(주의/주황)으로 회색(중립, archived/disabled와 동급)과 구분한다(product-quality-audit AREA=D).
  unmapped: "warn",
  // 유지보수 모드('점검')는 사용자 쓰기를 막는 능동 상태다. STATUS_TEXT엔 있으나 톤이 없어
  // 회색(neutral)으로 떠, 정상(up=green)보다 덜 위험해 보이던 역전을 바로잡는다.
  maintenance: "warn",
  running: "info", processing: "info", read: "info", test: "info", preview_ready: "info",
  archived: "neutral", disabled: "neutral", "false": "neutral",
  // secret_ref: 등록됨=정상 / 없음=주의(위 missing:warn). 티켓 상태 톤.
  configured: "ok", "Done": "ok", "완료": "ok",
  "In progress": "info", "진행 중": "info",
  "Not started": "neutral", "시작 전": "neutral", "Todo": "neutral", "할 일": "neutral",
  "In Review": "info", "검토 중": "info", "Blocked": "danger", "막힘": "danger",
  "Cancelled": "neutral", "취소됨": "neutral", "On Hold": "warn", "보류": "warn",
  "Backlog": "neutral", "백로그": "neutral",
  // 작업 DB 실제 진행상태 6종의 톤 — 예전엔 대부분 매핑이 없어 회색 일색이었다. 의미 있는 색으로:
  // 계획=회색(대기) 이슈=빨강(주의) 검증=주황(리뷰) 진행=파랑(활성) 완료=초록 취소=회색(비활성).
  "계획": "neutral", "이슈": "danger", "검증": "warn", "진행": "info", "취소": "neutral",
};
export function statusText(v) {
  if (v === true) return "예"; if (v === false) return "아니오";
  // 빈 문자열도 null/undefined와 같이 취급한다 — 안 그러면 배지가 텍스트 없이(스크린리더도
  // 낭독할 게 없이) 빈 채로 그려진다(product-quality-audit AREA=D).
  const s = String(v == null || v === "" ? "unknown" : v);
  if (STATUS_TEXT[s]) return STATUS_TEXT[s];
  // 매핑에 없는 값(조직마다 다른 Notion 보드 커스텀 상태명 등) — 원시 snake_case/kebab-case를
  // 그대로 새어 나가게 두지 않고 사람이 읽는 형태로 다듬는다("in_review" → "In Review").
  // 완전한 한국어 번역은 아니어도 코드 냄새가 나는 원시 식별자보다는 낫다.
  if (/^[a-z0-9]+([_-][a-z0-9]+)+$/i.test(s)) {
    return s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return s;
}
// 상태값 → 톤(ok/danger/warn/info/neutral). 배지 밖(예: 티켓 카드 상태 띠)에서도 같은 색 언어를 쓰게 공유.
export function statusKind(v) {
  const raw = String(v == null ? "" : v);
  return STATUS_KIND[raw] || "neutral";
}
export function Badge({ value, kind }) {
  const raw = String(value == null ? "" : value);
  const k = kind || STATUS_KIND[raw] || "neutral";
  return <span className={"k-badge k-badge--" + k}>{statusText(value)}</span>;
}

export function Button({ variant = "default", size, children, ...rest }) {
  const cls = ["k-btn", "k-btn--" + variant, size ? "k-btn--" + size : ""].filter(Boolean).join(" ");
  return <button className={cls} type="button" {...rest}>{children}</button>;
}

export function Card({ className, children, ...rest }) {
  return <div className={"k-card" + (className ? " " + className : "")} {...rest}>{children}</div>;
}

export function Callout({ tone = "info", children }) {
  // 심각도는 색만으로 구분하지 않는다(WCAG 1.4.1). 클로드식 기호(⚠/✓/ⓘ) 대신 짧은 텍스트
  // 라벨로 톤을 알린다, 위험=오류, 경고=주의, 성공=완료, 정보=안내(틴트 배경, 테두리와 함께).
  const label = tone === "danger" ? "오류" : tone === "warn" ? "주의" : tone === "success" ? "완료" : "안내";
  return (
    <div className={"k-callout k-callout--" + tone}>
      <span className="k-callout-label">{label}</span>
      <div className="k-callout-body">{children}</div>
    </div>
  );
}

export function StatCard({ value, label, kind, onClick, active }) {
  const Tag = onClick ? "button" : "div";
  // 심각도는 색만으로 전하지 않는다(WCAG 1.4.1). 클로드식 경고 기호(✕/▲)는 쓰지 않고, 짧은
  // 텍스트 태그('주의'/'위험')로 비색상 단서를 준다, 틴트 배경, 테두리, 값 색과 함께 읽힌다.
  const sev = kind === "danger" ? "위험" : kind === "warn" ? "주의" : null;
  return (
    <Tag className={"k-stat" + (kind ? " k-stat--" + kind : "") + (onClick ? " k-stat--click" : "") + (active ? " is-selected" : "")}
         type={onClick ? "button" : undefined} onClick={onClick} aria-pressed={onClick ? !!active : undefined}>
      <div className="k-stat-value">{value == null ? "-" : value}</div>
      <div className="k-stat-label">{label}{sev ? <span className="k-stat-sev">{sev}</span> : null}</div>
      {/* 클릭 가능 여부가 hover(cursor)로만 드러나면 터치 사용자는 눌러보기 전까진 알 방법이
          없다, 실제 상호작용 태그(onClick)일 때만 상시 보이는 화살표를 붙인다
          (product-quality-audit AREA=D). */}
      {onClick ? <span className="k-stat-chevron" aria-hidden="true">›</span> : null}
    </Tag>
  );
}

export function Skeleton({ lines = 3 }) {
  // 스켈레톤은 장식(aria-hidden)이라 스크린리더엔 침묵이다, 별도 live 노드로 로딩을 낭독한다.
  return (
    <>
      <span className="sr-only" aria-live="polite">불러오는 중…</span>
      <div className="k-skel" aria-hidden="true">
        {Array.from({ length: lines }).map((_, i) => <div className="k-skel-row" key={i} />)}
      </div>
    </>
  );
}

/* 빈 화면 — 아이콘+제목만 두지 않고 "지금 무엇을 하면 되는지"를 설명한다(§9).
 * 하위호환: 기존 호출부의 {icon,title,help,action}은 그대로 동작한다.
 * 안내 props(모두 선택):
 *   situation   — 왜 비어 있는지 한 줄 상황 설명(help의 상위 개념. help가 오면 함께 표시)
 *   prerequisite— 이 작업에 필요한 선행 조건("먼저 …이(가) 있어야 합니다")
 *   steps       — 다음에 할 일(문자열 배열 → 번호 목록). CSP: textContent만, innerHTML 없음
 *   expected    — 제대로 하면 무엇이 보이는지(기대 결과)
 *   action      — 주요 동작(버튼/링크 노드)
 *   relatedLink — 관련 화면으로 가는 링크 { href, label }
 */
export function EmptyState({ icon = null, title = "표시할 항목이 없습니다", help, situation, prerequisite, steps, expected, action, relatedLink }) {
  const stepList = Array.isArray(steps) ? steps.filter((s) => s != null && s !== "") : null;
  // role="status" + aria-live로 빈 상태 전환을 낭독한다, 예전엔 Skeleton(aria-live)이 이
  // 평범한 <div>로 바뀌면 스크린리더에 아무 안내도 없어 사용자는 목록이 비었는지조차 몰랐다.
  // 제목은 heading으로 올려 탐색 가능하게 한다(product-quality-audit AREA=D).
  return (
    <div className="k-empty" role="status" aria-live="polite">
      {icon ? <div className="k-empty-icon" aria-hidden="true">{icon}</div> : null}
      <div className="k-empty-title" role="heading" aria-level={2}>{title}</div>
      {situation ? <div className="k-empty-help">{situation}</div> : null}
      {help ? <div className="k-empty-help">{help}</div> : null}
      {prerequisite ? (
        <div className="k-empty-note"><span className="k-empty-note-label">필요한 것</span>{prerequisite}</div>
      ) : null}
      {stepList && stepList.length ? (
        <ol className="k-empty-steps">
          {stepList.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
      ) : null}
      {expected ? (
        <div className="k-empty-note"><span className="k-empty-note-label">기대 결과</span>{expected}</div>
      ) : null}
      {action ? <div className="k-empty-action">{action}</div> : null}
      {relatedLink && relatedLink.href ? (
        <a className="k-empty-link" href={relatedLink.href}>{relatedLink.label || "관련 화면으로"}</a>
      ) : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  const msg = (error && error.message) || "문제가 발생했습니다.";
  const status = error && error.status;
  const code = error && error.body && error.body.error && error.body.error.code;
  const isAuth = status === 401;
  const isForbidden = status === 403;
  const isGone = status === 404;
  // password_change_required는 403이지만 '권한 부족'이 아니라 '본인이 비번을 안 바꿔서' 막힌
  // 것이다, 일반 권한부족 문구("관리자에게 문의하세요")로 뭉개면 정반대로 오해하게 만든다
  // (Layout이 이 상태를 감지해 곧장 /change-password로 보내지만, 그 전에 잠깐 이 화면이 보일 수 있다).
  const isPwChange = isForbidden && code === "password_change_required";
  // 401/403/404는 재시도해도 같은 실패가 반복된다, '다시 시도'는 일시적 오류(네트워크, 5xx)에만 준다.
  const noRetry = isAuth || isForbidden || isGone;
  const title = isAuth ? "로그인이 필요합니다"
    : isPwChange ? "비밀번호 변경이 필요합니다"
    : isForbidden ? "권한이 없습니다"
    : isGone ? "찾을 수 없습니다"
    : "불러오지 못했습니다";
  const help = isPwChange ? msg
    : isForbidden ? "이 항목에 접근할 권한이 없습니다. 관리자에게 문의하세요."
    : isGone ? "요청한 항목을 찾을 수 없습니다. 이미 삭제되었거나 이동했을 수 있습니다."
    : msg;
  // role="alert"로 오류 전환을 즉시 낭독한다(재조회 실패, 권한 오류 등), Skeleton이 이 화면으로
  // 바뀔 때 스크린리더가 침묵하던 문제(product-quality-audit AREA=D). 제목은 heading으로.
  return (
    <div className="k-empty" role="alert">
      <div className="k-empty-title" role="heading" aria-level={2}>{title}</div>
      <div className="k-empty-help">{help}</div>
      {isAuth
        ? <a className="k-btn k-btn--primary" href="/login">로그인 화면으로</a>
        // "홈으로"(#/)는 이 SPA 안이라 다시 같은 403을 부른다, 실제 페이지 이동이 필요하다.
        : isPwChange ? <a className="k-btn k-btn--primary" href="/change-password">비밀번호 변경하기</a>
        // 403/404는 재시도해도 소용없지만 아무 동작도 없으면 막다른 길이다, 이전 화면으로
        // 돌아갈 수 있는 링크는 준다(401의 로그인 링크와 같은 이유).
        : (isForbidden || isGone) ? <a className="k-btn k-btn--primary" href="#/">홈으로</a>
        : (!noRetry && onRetry ? <Button variant="primary" onClick={onRetry}>다시 시도</Button> : null)}
    </div>
  );
}

/* 반응형 표 — 넓은 화면은 표, 좁은 화면(≤760px)은 카드 목록으로 CSS가 전환한다(§21).
 * columns: [{key,label,render?}], rows: [obj], rowKey: (row)=>id. onRow: 행 클릭(상세).
 * 접근성: 예전엔 <tr role="button">이라 스크린리더가 모든 셀을 한 버튼 이름으로 이어 읽었다.
 * 이제 행은 표 의미(row)를 유지하고, 상세 열기는 마지막 칸의 실제 <button>이 담당한다.
 * 마우스 편의를 위해 행 클릭도 남기되(포커스 대상 아님) 키보드·SR은 버튼으로 조작한다. */
// 상세 열기 버튼의 낭독 라벨을 행마다 다르게 만든다 — 첫 번째(보통 이름/제목) 열의 원시 값을
// 쓴다. render()가 있는 열은 JSX를 돌려주므로 텍스트로 쓰기 애매해 건너뛴다.
function rowOpenLabel(columns, row) {
  const primary = columns[0];
  if (!primary) return "상세 보기";
  // 첫 열이 커스텀 render()를 쓰면(예: 설정 화면의 라벨+키 조합 렌더) 원시 값을 텍스트로
  // 못 쓴다 — 그동안 모든 행이 똑같은 "상세 보기"만 낭독됐다. 화면 쪽에서 openLabel(row)를
  // 넘기면 render 유무와 무관하게 그 값을 우선 쓴다(product-quality-audit AREA=D).
  if (typeof primary.openLabel === "function") {
    try { const v = primary.openLabel(row); if (v) return v; } catch (e) { /* ignore */ }
  }
  if (primary.render) return "상세 보기";
  const v = row[primary.key];
  if (v == null || v === "") return "상세 보기";
  return "상세 보기: " + String(v);
}
export function DataTable({ columns, rows, rowKey, onRow, empty }) {
  // 방어: 비정상 입력(undefined/비배열 rows·columns, 비함수 rowKey)이 와도 렌더 중 throw하지 않고
  // 빈-목록 안내로 폴백한다 — 공용 표라 한 화면의 실수나 한 번의 API shape 변화가 전역 크래시로
  // 번지지 않게 한다(위 '호출부가 가드를 잊어도 안전' 계약을 실제로 성립시킨다).
  const baseCols = Array.isArray(columns) ? columns : [];
  const safeRows = Array.isArray(rows) ? rows : [];
  const keyOf = typeof rowKey === "function" ? rowKey : (_, i) => i;
  const cols = onRow ? [...baseCols, { key: "__open", label: "", align: "right", open: true }] : baseCols;
  return (
    <div className="k-table-wrap">
      <table className="k-table">
        <thead>
          {/* 상세 열기 칸은 label이 빈 문자열이라 스크린리더가 헤더 이름 없이 침묵으로 읽었다
              (표 전체에서 유일하게 매 행의 상세 진입로인 칸인데도). sr-only 텍스트로 이름을 준다. */}
          <tr>{cols.map((c) => <th key={c.key} scope="col" className={c.align ? "is-" + c.align : ""}>{c.open ? <span className="sr-only">동작</span> : c.label}</th>)}</tr>
        </thead>
        <tbody>
          {/* 빈 목록이면 헤더만 남은 '깨진 표' 대신 안내 한 줄을 그린다(호출부가 가드를 잊어도 안전). */}
          {safeRows.length === 0 ? (
            <tr><td className="k-table-empty" colSpan={cols.length}>{empty || "표시할 항목이 없습니다."}</td></tr>
          ) : safeRows.map((row, i) => (
            // 셀 안의 링크/버튼 클릭은 행 클릭(상세 열기)으로 번지지 않게 한다, 문서 '발행 링크'를
            // 누르면 새 탭이 열리며 상세 드로어까지 같이 열리던 이중 동작 방지.
            <tr key={keyOf(row, i)} className={onRow ? "is-click" : ""}
              onClick={onRow ? (e) => { if (e.target.closest("a,button")) return; onRow(row); } : undefined}>
              {cols.map((c) => (
                <td key={c.key} data-label={c.label} className={c.align ? "is-" + c.align : ""}>
                  {c.open
                    ? <button type="button" className="k-row-open" aria-label={rowOpenLabel(baseCols, row)}
                        onClick={(e) => { e.stopPropagation(); onRow(row); }}>상세</button>
                    : (c.render ? c.render(row) : (row[c.key] == null || row[c.key] === "" ? "-" : String(row[c.key])))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* 공통 모달, 모든 생성, 수정, 확인, 상세가 중앙 모달을 쓴다(우측 드로어 완전 제거).
 * 오버레이, 그림자, 헤더, 닫기, 하단 버튼, 애니메이션 통일. Esc, 바깥 클릭으로 닫힘, 인라인
 * 스타일 없음(CSP). size: sm|md|lg(항목 많을 때 큰 모달). 모바일에서는 전체 화면(CSS @640). */
export function ModalHeader({ title, onClose, titleId }) {
  return (
    <header className="k-modal-head">
      <h2 id={titleId}>{title}</h2>
      <button type="button" className="k-modal-x" onClick={onClose} aria-label="닫기">✕</button>
    </header>
  );
}
export function ModalBody({ children }) { return <div className="k-modal-body">{children}</div>; }
/* 표준 하단 작업줄, 취소(고스트), 기본 작업(오른쪽). 전 화면 동일 위치, 크기.
 * (예전엔 왼쪽에 부가 버튼을 위한 `extra` prop이 있었으나 앱 전체에서 어떤 호출부도 실제로
 * 넘긴 적이 없는 죽은 API 표면이었다(product-quality-audit AREA=D), 지워서 키트 표면을
 * 실제 사용 범위와 맞춘다. 필요해지면 git 이력에서 되살릴 수 있다.) */
export function ModalFooter({ onCancel, onSubmit, submitLabel = "저장", cancelLabel = "취소", busy, submitVariant = "primary" }) {
  return (
    <div className="k-footer-row">
      <div className="k-footer-main">
        {onCancel ? <Button variant="ghost" onClick={onCancel} disabled={busy}>{cancelLabel}</Button> : null}
        {onSubmit ? <Button variant={submitVariant} onClick={onSubmit} disabled={busy}>{busy ? "처리 중…" : submitLabel}</Button> : null}
      </div>
    </div>
  );
}
/* 열린 모달 스택 — 겹쳐 뜬 모달(상세 위 확인창 등)에서 Esc가 맨 위 하나만 닫도록.
 * 예전엔 모달마다 전역 Esc 핸들러를 걸어, 확인창에서 Esc를 누르면 확인창과 그 아래 상세
 * 드로어가 동시에 닫혔다. 이제 스택의 최상단만 키를 처리한다. */
const _modalStack = [];
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
export function Modal({ open, onClose, title, size = "md", children, footer }) {
  const dialogRef = React.useRef(null);
  const tokenRef = React.useRef({});
  const titleId = React.useId();
  // onClose를 ref로 잡아 effect가 open 변화에만 반응하게 한다(리렌더마다 포커스가 튀지 않도록).
  const onCloseRef = React.useRef(onClose);
  onCloseRef.current = onClose;
  React.useEffect(() => {
    if (!open) return undefined;
    const token = tokenRef.current;
    _modalStack.push(token);
    // 배경 스크롤 잠금 — 전에는 오버레이 뒤 본문이 마우스 휠로 계속 스크롤됐다(오버레이가
    // 불투명하지 않아 진짜 모달처럼 느껴지지 않았다). 중첩 모달(스택)에서는 첫 모달이 열릴
    // 때만 잠그고, 스택이 완전히 비었을 때만(마지막 모달이 닫힐 때) 원래 값으로 되돌린다.
    const prevOverflow = document.body.style.overflow;
    if (_modalStack.length === 1) document.body.style.overflow = "hidden";
    const prevFocus = document.activeElement;
    // 열릴 때 포커스를 대화상자 안으로 옮긴다(첫 입력, 없으면 대화상자 자체).
    // 단 헤더의 닫기(✕)는 건너뛴다 — DOM상 첫 포커스 대상이라 그냥 두면 모든 폼이 닫기 버튼에서 시작된다.
    const node = dialogRef.current;
    if (node) {
      const focusables = Array.prototype.slice.call(node.querySelectorAll(FOCUSABLE));
      const first = focusables.find((el) => !el.classList.contains("k-modal-x"));
      (first || node).focus();
    }
    const onKey = (e) => {
      if (_modalStack[_modalStack.length - 1] !== token) return; // 최상단만 처리
      if (e.key === "Escape") { e.stopPropagation(); onCloseRef.current(); return; }
      if (e.key === "Tab" && node) {
        const els = Array.prototype.filter.call(node.querySelectorAll(FOCUSABLE), (el) => el.offsetParent !== null || el === document.activeElement);
        if (!els.length) { e.preventDefault(); node.focus(); return; }
        const firstEl = els[0], lastEl = els[els.length - 1];
        if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus(); }
        else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus(); }
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      const i = _modalStack.indexOf(token); if (i >= 0) _modalStack.splice(i, 1);
      if (_modalStack.length === 0) document.body.style.overflow = prevOverflow;
      if (prevFocus && typeof prevFocus.focus === "function") { try { prevFocus.focus(); } catch (e) { /* ignore */ } }
    };
  }, [open]);
  if (!open) return null;
  return (
    <div className="k-modal-overlay" onMouseDown={onClose}>
      <div ref={dialogRef} className={"k-modal k-modal--" + size} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}>
        <ModalHeader title={title} onClose={onClose} titleId={titleId} />
        <ModalBody>{children}</ModalBody>
        {footer ? <footer className="k-modal-foot">{footer}</footer> : null}
      </div>
    </div>
  );
}

/* 공통 입력 필드, 라벨, 필수(*), 도움말, 오류 스타일을 한곳에서. 라벨은 htmlFor/id로 입력과
 * 연결해 스크린리더가 이름을 읽게 한다(체크박스는 라벨이 입력을 감싸 이미 연결됨). */
export function FormField({ field: f, value, onChange, invalid }) {
  const id = "ff-" + f.name;
  // JSON 필드는 사람이 직접 중첩 구조를 손으로 편집한다, 가변폭 UI 폰트로는 중괄호/들여쓰기가
  // 눈으로 안 맞는다. Settings.jsx의 .c-json-input과 같은 처리를 공용 FormField에도 준다
  // (product-quality-audit AREA=D).
  const cls = "k-input" + (f.type === "json" ? " k-input--mono" : "") + (invalid ? " is-invalid" : "");
  const inv = invalid ? true : undefined;
  // 선택형에서 현재 값과 맞는 옵션이 없으면 빈 옵션을 앞에 붙인다(필수 여부와 무관하게).
  // (빈 옵션이 없으면 <select>는 첫 실제 옵션을 화면에 보여 주면서도 상태는 '' — '이미 뭔가
  //  골라진 것처럼' 보이다가 제출 시 '필수 항목을 선택하세요' 오류가 나거나, 조용히 null로
  //  바뀌어 화면과 실제 값이 어긋난다. 필수 필드는 이 옵션을 disabled로 둬 다시 고를 수 없게 한다.)
  const selNeedEmpty = f.type === "select" &&
    !(f.options || []).some((o) => String(o.value) === (value != null ? String(value) : ""));
  const hasOptions = (f.options || []).length > 0;
  // 도움말을 aria-describedby로 실제 입력과 연결한다, 예전엔 f.help가 시각적으로만 아래 붙어
  // 있어, 스크린리더가 입력에 포커스를 줘도 도움말/필수 여부를 함께 읽지 않았다.
  const helpId = f.help ? id + "-help" : undefined;
  const required = f.required || undefined;
  return (
    <div className="k-field">
      {f.type === "checkbox" ? null : (
        <label className="k-field-label" htmlFor={id}>{f.label}{f.required ? <span className="k-req"> *</span> : null}</label>
      )}
      {f.type === "textarea" || f.type === "json" ? (
        <textarea id={id} className={cls} aria-invalid={inv} aria-required={required} aria-describedby={helpId}
          rows={f.type === "json" ? 10 : 3} value={value || ""} onChange={(e) => onChange(e.target.value)} />
      ) : f.type === "select" ? (
        <select id={id} className={cls} aria-invalid={inv} aria-required={required} aria-describedby={helpId}
          value={value != null ? value : ""} onChange={(e) => onChange(e.target.value)}>
          {selNeedEmpty ? <option value="" disabled={f.required}>{hasOptions ? "선택 안 함" : "선택할 항목이 없습니다"}</option> : null}
          {(f.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      ) : f.type === "checkbox" ? (
        // 라벨(f.label)을 실제 입력과 연결되는 <label> 안에 둔다, 예전엔 위쪽의 비연결 <span>이
        // f.label을, 이 <label>은 checkLabel(없으면 고정 문구 "사용")만 담아 f.checkLabel이
        // 빠지면 체크박스의 실제 접근성 이름이 항목 의미와 무관한 "사용"이 되곤 했다.
        <label className="k-check" htmlFor={id}>
          <input id={id} type="checkbox" checked={!!value} aria-describedby={helpId} onChange={(e) => onChange(e.target.checked)} />
          {" "}{f.checkLabel || f.label || "사용"}{f.required ? <span className="k-req"> *</span> : null}
        </label>
      ) : f.type === "date" || f.type === "datetime-local" ? (
        // 날짜/일시 입력, 예전엔 이 분기가 없어 스케줄의 run_at 같은 필드가 일반 텍스트로
        // 떨어져 관리자가 ISO-8601을 손으로 입력해야 했다(product-quality-audit AREA=D).
        <input id={id} className={cls} aria-invalid={inv} aria-required={required} aria-describedby={helpId}
          type={f.type} value={value || ""} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input id={id} className={cls} aria-invalid={inv} aria-required={required} aria-describedby={helpId}
          type={f.type === "number" ? "number" : (f.type === "password" ? "password" : (f.type === "email" ? "email" : "text"))}
          {...(f.type === "email" ? { inputMode: "email", autoCapitalize: "none" } : {})}
          value={value != null ? value : ""} onChange={(e) => onChange(e.target.value)} />
      )}
      {f.help ? <div className="k-field-help" id={helpId}>{f.help}</div> : null}
    </div>
  );
}

/* 설정 주도 폼 — 항상 중앙 모달(우측 드로어 없음). 항목이 많으면(>5) 큰 모달(lg). Modal·
 * ModalFooter·FormField를 재사용해 전 화면 폼이 동일하게 보인다.
 * type: text|number|textarea|select|checkbox|json. JSON은 문자열 입력→파싱(검증). */
export function FormModal({ open, title, fields, initial, submitLabel, onSubmit, onClose, size }) {
  const [values, setValues] = React.useState({});
  const [err, setErr] = React.useState("");
  const [errField, setErrField] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const initialRef = React.useRef({});   // 열릴 때의 값 스냅샷 — 더티(변경) 판정 기준.
  const confirm = useConfirm();
  const toast = useToast();
  React.useEffect(() => {
    if (!open) return;
    const v = {};
    (fields || []).forEach((f) => {
      const iv = initial && initial[f.name] != null ? initial[f.name] : (f.value != null ? f.value : (f.type === "checkbox" ? false : ""));
      v[f.name] = f.type === "json" && iv && typeof iv === "object" ? JSON.stringify(iv, null, 2) : iv;
    });
    initialRef.current = v;
    setValues(v); setErr(""); setErrField(null);
  }, [open]);
  // 앱 전체의 유일한 생성·수정 표면이라, 긴 폼(러너/워크플로 JSON 등)을 채우던 중 오버레이·Esc
  // 오조작 한 번에 입력이 통째로 날아가던 문제. 변경이 있으면 닫기 전에 확인을 받는다(제출은 영향 없음).
  // 더티(변경) 비교 전에 number 필드를 문자열로 정규화한다 — 기본값은 숫자(f.value:60)로
  // 저장되지만 입력을 거치면 문자열('60')이 된다. 같은 값을 지웠다 다시 입력하면 60 vs '60'이
  // JSON.stringify에서 달라 '저장 안 됨, 닫을까요?' 헛경고가 떴다(product-quality-audit AREA=D).
  const normalizeForCompare = React.useCallback((vals) => {
    const out = {};
    (fields || []).forEach((f) => {
      const v = vals ? vals[f.name] : undefined;
      out[f.name] = f.type === "number" ? (v === "" || v == null ? "" : String(v)) : v;
    });
    return out;
  }, [fields]);
  const requestClose = React.useCallback(async () => {
    // 제출이 진행 중일 때는 취소/Esc/오버레이 클릭 모두 거부한다 — 예전엔 busy를 확인 생략
    // 조건으로만 썼다가 그대로 onClose()로 흘러, '처리 중…' 표시 중에도 닫기가 그냥 통과되며
    // 아무 취소도 실제로 일어나지 않은 채(요청은 계속 진행 중) 모달만 닫히던 문제가 있었다.
    if (busy) return;
    if (JSON.stringify(normalizeForCompare(values)) !== JSON.stringify(normalizeForCompare(initialRef.current))) {
      const ok = await confirm("입력한 내용이 저장되지 않았습니다. 창을 닫을까요?", { danger: true, title: "변경 사항 버리기", confirmLabel: "닫기" });
      if (!ok) return;
    }
    onClose();
  }, [busy, values, confirm, onClose, normalizeForCompare]);
  // 검증 실패 필드를 화면 안으로 스크롤·포커스한다(큰 폼에서 오류가 스크롤 아래 숨는 문제).
  React.useEffect(() => {
    if (!errField) return;
    const el = document.getElementById("ff-" + errField);
    if (el) { try { el.scrollIntoView({ block: "center", behavior: "smooth" }); el.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
  }, [errField]);
  if (!open) return null;
  const set = (name, val) => setValues((s) => ({ ...s, [name]: val }));
  const fail = (name, message) => { setErrField(name); setErr(message); };

  async function submit() {
    setErr(""); setErrField(null);
    const body = {};
    for (const f of (fields || [])) {
      // 수정 화면에서 원래 값이 있던 선택형 항목을 비우면, 키를 생략하지 않고 null로 보내 실제로 지운다.
      // (생략하면 PATCH는 옛 값 유지, PUT은 서버 기본값으로 리셋된다 — 둘 다 사용자가 의도한 '지움'이 아니다.)
      const hadValue = initial && initial[f.name] != null && String(initial[f.name]).trim() !== "";
      let val = values[f.name];
      if (f.type === "number") {
        if (val === "" || val == null) { if (f.required) { fail(f.name, f.label + "을(를) 입력하세요."); return; } if (hadValue) body[f.name] = null; continue; }
        val = Number(val); if (Number.isNaN(val)) { fail(f.name, f.label + ": 숫자를 입력하세요."); return; }
        body[f.name] = val; continue;
      }
      // required 체크박스도 다른 타입과 같은 검증을 받는다 — 예전엔 라벨에 '*'만 붙고 실제
      // 검증이 없어 체크 안 함(false)이 항상 통과됐다(product-quality-audit AREA=D). 지금은
      // 어떤 registry 필드도 checkbox required를 안 쓰지만(latent), 키트 계약을 맞춘다.
      else if (f.type === "checkbox") { if (f.required && !val) { fail(f.name, (f.checkLabel || f.label) + "을(를) 선택해야 합니다."); return; } body[f.name] = !!val; continue; }
      else if (f.type === "json") {
        if (!val || !String(val).trim()) { if (f.required) { fail(f.name, f.label + "을(를) 입력하세요."); return; } if (hadValue) body[f.name] = null; continue; }
        let parsed;
        try { parsed = JSON.parse(val); } catch (e) { fail(f.name, f.label + ": JSON 형식이 올바르지 않습니다."); return; }
        // 일부 필드(예: 정책 content)는 백엔드가 JSON 객체만 허용한다(배열·문자열·숫자는 거부).
        // 여기서 먼저 걸러내지 않으면 클라이언트는 통과시키고 서버 왕복 후에야 같은 메시지로
        // 실패한다 — registry가 f.jsonObject를 선언한 필드에 한해 서버와 같은 문구로 먼저 막는다
        // (product-quality-audit AREA=D).
        if (f.jsonObject && (parsed === null || typeof parsed !== "object" || Array.isArray(parsed))) {
          fail(f.name, f.label + "은(는) JSON 객체여야 합니다."); return;
        }
        body[f.name] = parsed;
        continue;
      }
      else if (f.type === "select") {
        val = val == null ? "" : String(val);
        if (f.required && !val.trim()) {
          // 옵션 자체가 없으면(예: 유일한 옵션 후보가 소진된 충돌 해결 선택) '선택하세요'는
          // 아무것도 고를 게 없는 사용자에게 헛도는 무한 루프다 — 원인이 다른 문구를 준다
          // (product-quality-audit AREA=D).
          if (!(f.options || []).length) { fail(f.name, f.label + ": 선택할 수 있는 항목이 없습니다, 다시 시도하거나 취소하세요."); return; }
          fail(f.name, f.label + "을(를) 선택하세요."); return;
        }
        body[f.name] = val === "" ? null : val; continue;
      }  // 빈 선택("없음")은 null로 보내 기존 값을 지운다.
      else { val = val == null ? "" : String(val); if (f.required && !val.trim()) { fail(f.name, f.label + "을(를) 입력하세요."); return; } if (val !== "") body[f.name] = val; else if (hadValue) body[f.name] = null; }
    }
    setBusy(true);
    try { await onSubmit(body); }
    catch (e) {
      // 세션 만료(401)는 다른 실패와 다르게 다룬다 — DataScreen.jsx의 handleApiError와 같은
      // 패턴이다. 여기서 재시도해도 항상 401이라 일반 폼 오류 문구만 띄우면 사용자는 자신이
      // 방금 입력한 내용이 왜 저장되지 않는지 모른 채 이 모달 안에 막힌다(product-quality-audit
      // AREA=D). FormModal은 ~15개 이상의 생성/수정 화면이 공유하는 유일한 표면이라 DataScreen
      // 전용 handleApiError를 그대로 재사용할 수 없어(파일 간 결합 없음) 여기 동일 로직을 둔다.
      if (e && e.status === 401) {
        toast("로그인이 필요합니다. 로그인 화면으로 이동합니다.", "error");
        window.setTimeout(() => { window.location.href = "/login"; }, 1200);
        return; // busy=true로 남겨 재제출을 막는다 — 곧 페이지가 이동한다.
      }
      // 백엔드가 검증 실패의 구체적 사유 목록을 details로 함께 보낼 때가 있다(예: 비밀번호
      // 정책 위반 — "비밀번호 정책 위반"이라는 포장 메시지만 있고 실제로 어떤 규칙을 어겼는지는
      // details 배열에만 있었다). 있으면 이어붙여 사용자가 무엇을 고쳐야 하는지 보이게 한다.
      // details가 문자열이 아니라 {loc,msg} 객체 배열일 수도 있다(예: RequestValidationError) —
      // 그대로 join하면 "[object Object]"가 새어 나온다(product-quality-audit AREA=D).
      const details = e.body && e.body.error && Array.isArray(e.body.error.details) ? e.body.error.details : null;
      const detailTexts = (details || []).map((d) => (d && typeof d === "object" ? (d.msg || JSON.stringify(d)) : d));
      const msg = [e.message || "저장하지 못했습니다.", ...detailTexts].filter(Boolean).join(" ");
      setErr(msg); setBusy(false); return;
    }
    setBusy(false);
  }

  const sz = size || ((fields || []).length > 5 ? "lg" : "md");
  const footer = <ModalFooter onCancel={requestClose} onSubmit={submit} submitLabel={submitLabel || "저장"} busy={busy} />;
  return (
    <Modal open={open} onClose={requestClose} title={title} size={sz} footer={footer}>
      {/* 필드를 <form>으로 감싸 Enter가 자연스럽게 제출되게 한다, 예전엔 <div>뿐이라 어떤
          입력에서 Enter를 눌러도 아무 일도 없었다(textarea/json은 여러 줄 입력을 위해 계속
          기본 Enter 동작을 유지한다, product-quality-audit AREA=D). */}
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {err ? <div className="k-form-err k-form-err--top" role="alert">{err}</div> : null}
        {(fields || []).map((f) => <FormField key={f.name} field={f} value={values[f.name]} invalid={errField === f.name} onChange={(val) => set(f.name, val)} />)}
        {/* 화면에 보이지 않는 제출 버튼, 실제 저장 버튼은 Modal footer(별도 DOM 트리)에 있어
            이 <form> 안에 없다. type="submit" 버튼이 하나도 없으면 브라우저에 따라 단일
            텍스트 입력에서 Enter가 폼을 제출하지 않을 수 있어, 표준 submit 이벤트 경로를
            보장하는 안전판으로 둔다. */}
        <button type="submit" className="sr-only" tabIndex={-1} aria-hidden="true" />
      </form>
    </Modal>
  );
}
// 하위호환 별칭 — 기존 호출부(FormDrawer/FormDialog/Drawer/DialogFooter)는 그대로 두되 전부 중앙 모달로 동작.
export const FormDrawer = FormModal;
export const FormDialog = FormModal;
export const Drawer = Modal;
export const DialogFooter = ModalFooter;

/* 스타일된 확인 대화상자(중앙 모달) — window.confirm 대체. useConfirm()이 async 함수를 준다. */
const ConfirmCtx = React.createContext(() => Promise.resolve(false));
export function ConfirmProvider({ children }) {
  const [state, setState] = React.useState(null);
  const confirm = React.useCallback((message, opts) =>
    new Promise((resolve) => setState({ message, resolve, danger: opts && opts.danger, title: (opts && opts.title) || "확인", confirmLabel: (opts && opts.confirmLabel) || "확인" })), []);
  const done = (val) => { setState((s) => { if (s) s.resolve(val); return null; }); };
  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      <Modal open={!!state} onClose={() => done(false)} title={state ? state.title : ""}
        footer={<DialogFooter onCancel={() => done(false)} onSubmit={() => done(true)}
          submitLabel={state ? state.confirmLabel : "확인"} submitVariant={state && state.danger ? "danger" : "primary"} />}>
        <p className="k-confirm-msg">{state ? state.message : ""}</p>
      </Modal>
    </ConfirmCtx.Provider>
  );
}
export function useConfirm() { return React.useContext(ConfirmCtx); }

/* 토스트 — window.alert 대체. useToast()(message, kind).
 * 오류는 더 오래 남기고(8s) 직접 닫기 버튼을 준다 — 3.5s에 사라지면 무엇이 실패했는지 놓친다.
 * aria: 정보/성공은 polite, 오류는 role="alert"(즉시 낭독). */
let _toastSeq = 0;
const ToastCtx = React.createContext(() => {});
export function ToastProvider({ children }) {
  const [toasts, setToasts] = React.useState([]);
  const dismiss = React.useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = React.useCallback((message, kind) => {
    const id = ++_toastSeq;
    const k = kind || "info";
    setToasts((t) => [...t, { id, message, kind: k }]);
    const ttl = k === "error" ? 8000 : 3500;
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ttl);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="k-toasts" aria-live="polite" aria-atomic="false">
        {toasts.map((t) => (
          <div key={t.id} className={"k-toast k-toast--" + t.kind} role={t.kind === "error" ? "alert" : undefined}>
            <span className="k-toast-msg">{t.message}</span>
            <button type="button" className="k-toast-x" aria-label="닫기" onClick={() => dismiss(t.id)}>✕</button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
export function useToast() { return React.useContext(ToastCtx); }

/* 페이지 헤더, 빵부스러기→제목 순서와 간격을 한곳에서 정한다.
 * crumbRoot: 빵부스러기 접두어(기본 '관리자'). 사용자 대면 화면은 다른 뿌리를 넘기거나
 *   area를 비워 빵부스러기 자체를 숨길 수 있다(§ 비관리자에게 '관리자 ›'가 새던 문제).
 * (예전엔 여기 `description` prop과 .k-page-desc 렌더가 있었으나, 앱 전체에서 어떤
 * 호출부도 실제로 넘긴 적이 없는 죽은 API 표면이었다(product-quality-audit AREA=D) -
 * 이 파일 아래쪽의 PageHelp/Toolbar/PageSection 정리와 같은 이유로 지운다. 필요해지면
 * git 이력에서 되살릴 수 있다.) */
export function PageHeader({ area, title, actions, crumbRoot = "관리자" }) {
  return (
    <div className="k-page-head">
      <div className="k-page-head-text">
        {area ? <div className="k-breadcrumb">{crumbRoot ? crumbRoot + " › " : ""}{area}</div> : null}
        <h1 className="k-page-title">{title}</h1>
      </div>
      {actions ? <div className="k-page-actions">{actions}</div> : null}
    </div>
  );
}

/* PageHelp/Toolbar/PageSection — 예전엔 여기 있었으나 어떤 화면도 실제로 가져다 쓰지 않는
 * 죽은 export였다(DataScreen.jsx는 자체 인라인 툴바/섹션 마크업을 쓴다, product-quality-audit
 * AREA=D 발견사항). 표준화를 노렸다면 소비자(DataScreen.jsx, 이 파일 소유 범위 밖)를 그쪽으로
 * 옮겨 붙이는 게 진짜 수정이지만, 이 파일 단독으로는 미사용 export를 남겨 두는 대신 지운다 —
 * 필요해지면 언제든 git 이력에서 되살릴 수 있다. */
