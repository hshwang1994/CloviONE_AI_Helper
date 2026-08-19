import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Badge } from "./kit.jsx";
import { SECTION_GAP } from "./density.js";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, MOTION } from "./theme.js";

/* 관리자 화면(Dashboard·진단·유지보수·작업 큐·개발자 리포트)이 함께 쓰는 껍데기·격자.
 * 예전엔 전부 Dashboard.jsx 안에 있어서, 그 화면 하나가 사실상 '관리자 전용 디자인 시스템'
 * 노릇을 했다(DS-17) — 5개 모듈이 화면 파일 하나를 import하는 구조였다. 여기로 옮겨 진짜
 * 공용 위치에 둔다. 순수 표시 헬퍼(serviceLabel·날짜/숫자 포맷 등)는 ops/opsHelpers.js로
 * 옮겼다 — 그쪽은 JSX 없는 순수 함수 모음이라는 기존 성격에 맞춘 것이다. */

/* 설정 한 줄 — **이름 · 지금 값 · 그것이 무엇인지 · 바꾸는 동작** (지시 32 · 33 · 45).
 *
 * 관리 화면이 공통으로 틀리던 자리가 여기였다. `변경` 이라는 상자에 기능명 버튼을 몰아 두고,
 * 지금 값은 다른 상자에 두거나 아예 안 보여 줬다. 그러면 화면은 "무엇을 바꿀 수 있는가"만
 * 말하고 "무엇이 설정돼 있는가"는 말하지 않는다 - 사용자는 버튼을 누른 **뒤에야** 현재
 * 설정을 알게 된다.
 *
 * `state` 는 저장·적용 상태다(지시 45). 값이 화면에 있다는 것과 그 값이 실제로 동작에
 * 반영됐다는 것은 다른 사실이다.
 *
 *   `dirty`    수정됨(아직 저장 안 함)
 *   `saved`    저장됨, 다음 실행 주기부터 반영
 *   `applied`  즉시 적용됨
 *   `restart`  재시작해야 반영됨
 *   `failed`   적용 실패
 *
 * 값을 읽을 수 없을 때는 `tone="muted"` 로 두고 **모른다고 쓴다** - 빈칸은 "설정 안 됨"으로
 * 읽힌다(§불변 6: 없는 것을 있는 척하지 않는다).
 */
export const SETTING_STATE_LABELS = {
  dirty: "수정됨",
  saved: "저장됨, 다음 주기부터",
  applied: "즉시 적용됨",
  restart: "재시작 필요",
  failed: "적용 실패",
};

const SETTING_STATE_KIND = {
  dirty: "warn",
  saved: "neutral",
  applied: "ok",
  restart: "warn",
  failed: "error",
};

export function SettingRow({ label, value, description, tone, action, state, last, children }) {
  return (
    <Box
      /* 줄 하나가 한 항목이라는 사실을 시험이 붙잡을 자리. 라벨에서 부모를 몇 번 거슬러
         올라가는 식으로 찾으면 안쪽 배치를 조금만 바꿔도 시험이 깨진다. */
      className="k-settingrow"
      sx={{
        display: "flex", alignItems: "flex-start", gap: 2, flexWrap: "wrap",
        py: 1.75, borderBottom: last ? 0 : 1, borderColor: "divider",
      }}
    >
      <Box sx={{ flex: "1 1 22rem", minWidth: 0, display: "grid", gap: 0.25 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
          <Typography component="div" sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
            {label}
          </Typography>
          {state ? <Badge value={SETTING_STATE_LABELS[state] || state} kind={SETTING_STATE_KIND[state] || "neutral"} /> : null}
        </Box>
        {value == null ? null : (
          <Typography
            component="div"
            color={tone === "muted" ? "text.secondary" : "text.primary"}
            sx={{ fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}
          >
            {value}
          </Typography>
        )}
        {description ? (
          <Typography component="div" color="text.secondary" sx={{ fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK }}>
            {description}
          </Typography>
        ) : null}
        {children}
      </Box>
      {action ? <Box sx={{ flexShrink: 0, pt: 0.25 }}>{action}</Box> : null}
    </Box>
  );
}

/* 설정 줄 묶음 — **판이 아니라 제목 + 괘선 목록** (PLAN «B10 Settings», «Surface 위계»).
 *
 * 판정 체크리스트를 돌리면 여기서 멈출 곳이 없다: 자체 생명주기 없음(저장은 줄마다다),
 * 독립 스크롤 없음, 떠 있지 않음, 함몰면 아님, Brand 순간 아님 -> **컨테이너 없음.**
 * B10 이 요구한 형태도 같다 — "설정 목록(라벨/현재값/출처/최근변경/Action)을 행 + 괘선으로,
 * 카드 아님". 판을 벗기면 설정 화면에서 흰 사각형이 사라지고 남는 것은 읽어야 할 줄들이다.
 *
 * 줄 사이 괘선은 `SettingRow` 가 이미 자기 아래 선으로 그린다 — 판이 없어져도 묶음은
 * 그 선들과 제목으로 읽힌다. */
export function SettingList({ title, action, children }) {
  return (
    <Box component="section" sx={{ mt: SECTION_GAP }}>
      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 2, mb: 1, flexWrap: "wrap" }}>
        <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle }}>{title}</Typography>
        {action}
      </Box>
      {children}
    </Box>
  );
}

/* 개수가 고정(5개)인 머리 지표 줄의 격자.
 *
 * 지표를 낱장 카드 격자(옛 `STAT_GRID`)로 까는 방식은 폐기했다 — 열 수가 개수를 나누지
 * 못하면 마지막 줄이 비고, 무엇보다 카드 N장은 무엇이 핵심 지표인지 말해 주지 않는다.
 * 지표는 이제 판 하나를 나눠 쓰는 판독 줄(kit.jsx::MetricStrip)이다.
 *
 * 이 격자는 지표가 아니라 **경보 타일**처럼 개수가 고정된 줄에만 남는다. 좁은 화면에서는
 * 2열로 접히고, 그때는 5개가 세 줄이 되는 게 맞다(가로 스크롤보다 낫다). */
export const HEADLINE_GRID = {
  xs: "1fr",
  sm: "repeat(2, minmax(0,1fr))",
  lg: "repeat(5, minmax(0,1fr))",
};

/* 대시보드·진단이 공유하는 섹션 껍데기(제목 + 오른쪽 보조 링크).
 * 예전엔 .dash-section/.dash-h2/.dash-h2-row 세 클래스를 두 화면이 각자 손으로 붙였고,
 * 한쪽에만 h2-row를 빠뜨려 같은 성격의 섹션이 화면마다 다른 간격으로 보였다. */
export function DashSection({ title, action, children }) {
  return (
    /* 섹션 사이 간격의 정본은 `density.js::SECTION_GAP` 하나다(W4 에서 24 -> 32). 예전에는
       이 자리에 `{ xs: 4, xxl: 5 }` 같은 화면별 숫자가 있었고, 한 화면에 섹션이 대여섯 개인
       대시보드에서 화면 하나 분량의 빈 줄을 더 만들었다. */
    <Box component="section" sx={{ mb: SECTION_GAP }}>
      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 2, mb: 1.5 }}>
        <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle }}>{title}</Typography>
        {action}
      </Box>
      {children}
    </Box>
  );
}

/* 서비스/연동 상태 타일(이름 + 배지). 대시보드와 진단이 같은 사실을 같은 모양으로 보여야 한다 —
 * 예전엔 두 화면이 각자 .dash-svc 마크업을 손으로 복사해 뒀고, 한쪽만 hover 표시를 붙여
 * '누를 수 있는 카드'인지 아닌지가 화면마다 달라 보였다.
 * 이름 옆에 중첩 <button>을 두지 않는다 — role="button" 안의 포커스 가능한 자손은 WAI-ARIA 금지이고,
 * 실제로도 '이름을 누르면 다른 일이 일어난다'는 잘못된 기대를 만든다. 카드 하나만 클릭 대상이다. */
/* 상태 목록 한 벌. 줄이 실선으로 나뉜다.
 *
 * 예전에는 상태 하나가 흰 카드 한 장이었고 3~7장을 격자에 깔았다. 1920 실측에서 이름
 * 하나와 배지 하나가 530px 카드 안에 놓여 가운데가 통째로 비었고, 개수가 열 수의 약수가
 * 아니면 마지막 줄이 남았다 — 지표 카드 벽과 같은 결함이다(D-143).
 *
 * 위쪽 '확인이 필요한 항목'이 이미 "왼쪽에 무엇, 오른쪽에 상태/조치" 줄로 읽히므로 같은
 * 어휘를 쓴다 — 한 화면에서 같은 성격의 정보가 두 가지 모양으로 나오지 않게 한다. */
export function StatusList({ children, ariaLabel }) {
  return (
    /* W4 — 판을 벗겼다. PLAN «Surface 위계» 의 하드 금지에 이 형태가 이름으로 있다:
       "목록 하나뿐이고 Action 없는 plate 는 divider group 이다". 이 목록은 이름과 배지만
       담고 자기 Action 도 생명주기도 없다. B8(Operations console)의 «Health line(한 줄,
       카드 없음)» 도 같은 말이다. 실선이 줄을 나누고, 묶음은 제목이 만든다. */
    <Box
      className="k-statuslist"
      role="group"
      aria-label={ariaLabel}
      sx={{ "& > *:not(:first-of-type)": { borderTop: 1, borderColor: "divider" } }}
    >
      {children}
    </Box>
  );
}

/* 상태 한 줄. `StatusList` 안에서만 쓴다(자기 판을 갖지 않는다). */
export function StatusTile({ name, onClick, ariaLabel, children }) {
  return (
    <Box
      onClick={onClick}
      sx={{
        px: 2, py: 1.25, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1,
        cursor: onClick ? "pointer" : "default",
        transition: `background-color ${MOTION.instant} ${MOTION.ease}`,
        "&:hover": onClick ? { bgcolor: "background.inset" } : undefined,
        "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: -2 }),
      }}
      role={onClick ? "button" : undefined} tabIndex={onClick ? 0 : undefined}
      aria-label={onClick ? ariaLabel : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } } : undefined}>
      <Typography
        variant="body2" title={name}
        sx={{ fontWeight: FONT_WEIGHT.semibold, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
      >
        {name}
      </Typography>
      {children}
    </Box>
  );
}

/* 섹션 안의 부연(‘성공률 분모’ 설명 등). 예전 .pending-note를 대신한다 — 클래스 하나로
 * 문단·도움말·주석이 뒤섞여 있어서 한 곳을 고치면 엉뚱한 화면의 여백이 같이 움직였다.
 * id를 받는다 — 이 문단이 곧 입력의 설명(aria-describedby 대상)이 되는 자리가 있다(Ops의 점검 공지).
 *
 * ⚠️ **이것은 문단(`<p>`)이다. 안에 문단을 또 넣을 수 없다.**
 * `<p>` 안의 `<p>`는 브라우저가 앞 문단을 강제로 닫아 버려서, 겉보기엔 렌더되지만 DOM 구조가
 * 작성자의 의도와 달라진다(실제로 `UsersBulk` 에서 `Callout`→`Note` 로 옮기다 이 함정을 밟았다).
 * 여러 문단짜리 설명은 `Note` 를 **여러 개** 쓰고 두 번째부터 `sx={{ mt: 0.75 }}` 로 붙인다.
 * 그 제약이 컴포넌트 밖에서는 보이지 않으므로 여기 적어 둔다. */
export function Note({ children, sx, id }) {
  return (
    /* 한국어 설명 문단이라 `KO_WORD_BREAK` 가 필요하다 — 없으면 좁은 칸에서 "도와드/려요"
       처럼 단어 중간에서 줄이 바뀐다(ui/ko-wordbreak.test.jsx 가 지키는 그 결함). Callout 을
       대신해 설명을 받게 된 뒤로는 이쪽이 그 문장들의 집이다. */
    <Typography id={id} variant="body2" color="text.secondary" sx={{ mt: 1.5, lineHeight: 1.6, ...KO_WORD_BREAK, ...sx }}>
      {children}
    </Typography>
  );
}
