import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Badge, FlatBadgeSurface, SectionTitle } from "./kit.jsx";
import { SECTION_GAP, SETTING_ROWS_FORM } from "./density.js";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, LINE_HEIGHT, MOTION } from "./theme.js";
import { centerPad } from "./layout.jsx";

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
  saved: "저장됨, 다음 주기부터 반영",
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

/* 한 행의 리듬은 하나다 (D-457) — `py: 1`, 설명은 caption. 예전에는 이 줄이 `py: 1.75` 였고
   `/profile` 의 알림 행은 `py: 0.75`, 계정 행은 `py: 1.25` 라 같은 종류의 줄이 셋 다 달랐다.
   `/profile` 도 이 부품을 쓴다. */
/* 🔴 `compact` 는 **개인 설정의 켜고 끄는 목록**을 위한 밀도다(내 프로필).
 *
 * 관리자 줄과 무엇이 다른가. 관리자 줄은 「지금 값」과 상태 배지를 나르고 설명이 두세 줄로
 * 이어지는 자리다 — 읽는 줄이다. 개인 설정의 유형 목록은 스무 줄이 한 판에 서고, 하는 일은
 * 「내가 끄고 싶은 것을 찾는」 훑기다. 훑는 목록에서 줄 높이가 들쭉날쭉하면 눈이 스위치의
 * 세로선을 못 따라간다.
 *
 * 그래서 셋이 다르다: 글자가 한 단 작고(이름 0.875 / 설명 0.75), 줄이 **절대 두 줄이 되지
 * 않으며**(넘치면 말줄임 + `title`), 실선이 줄 **위**에 온다. 위에 두는 이유는 첫 줄과
 * 제목 사이에도 선이 필요해서다 — 아래에 두면 마지막 줄 밑에 선이 하나 남아 판 테두리와
 * 겹쳐 두 줄로 보인다(표가 같은 이유로 마지막 행의 아래 선을 지운다).
 *
 * 관리자 줄을 이 밀도로 함께 옮기지 않는다. 두 목록은 같은 모양이지만 **같은 일이 아니다**
 * — 값과 배지를 나르는 줄에 말줄임을 걸면 읽어야 할 사실이 사라진다(CLAUDE.md §5).
 *
 * `controlId` — 이 줄의 이름을 `action` 안 컨트롤의 **라벨**로 잇는다(D-525). 주면 이름을
 * `<label htmlFor={controlId}>` 로 그려 이름을 눌러도 스위치가 바뀌고, 호출부는 같은 값을 컨트롤의 `id` 에 준다.
 * 이 줄은 컨트롤이 무엇인지 모른다 — id 하나만 안다. 단추나 세그먼티드가 선 줄에는 주지 않는다: 이름을 누르는
 * 것만으로 그 단추가 눌려 버린다. 접근 가능한 이름은 컨트롤의 aria-label 이 계속 정한다. */
const LABEL_FOR = { display: "block", cursor: "pointer" };

/* 줄의 폭은 줄이 아니라 묶음이 정한다 — `SettingRows width="form"`(D-590). 안 주면 지금처럼 담는 판의 폭을 다 쓴다. */
export function SettingRow({ label, value, description, tone, action, state, last, compact, controlId, children }) {
  const oneLine = { minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };
  return (
    /* 설정 줄도 목록 행이다 — 상태 배지는 면 없이 점 + 낱말로 선다(RULES §2). */
    <FlatBadgeSurface>
    <Box
      /* 줄 하나가 한 항목이라는 사실을 시험이 붙잡을 자리. 라벨에서 부모를 몇 번 거슬러
         올라가는 식으로 찾으면 안쪽 배치를 조금만 바꿔도 시험이 깨진다. */
      className={compact ? "k-settingrow k-settingrow--compact" : "k-settingrow"}
      sx={{
        ...(compact ? {
          display: "flex", alignItems: "center", gap: 1.5,
          py: 1.25, borderTop: 1, borderColor: (t) => t.palette.rule,
        } : {
          /* **첫 줄 정렬**(D-528). 예전에는 `center` 라 설명이 두 줄이 되면 스위치가 라벨이 아니라 라벨 + 설명 덩어리의
             가운데에 섰다. 이제 스위치(배치 높이 34)와 라벨 첫 줄(15px × 1.6)이 한 가운데선에 서고, 설명은 그 아래로 자란다. */
          display: "flex", alignItems: "flex-start", gap: 2, flexWrap: "wrap",
          py: 1, borderBottom: last ? 0 : 1, borderColor: "divider",
        }),
        /* 컨트롤이 비활성이면 이름도 누를 것처럼 보이지 않는다 — 눌러도 아무 일이 없다. */
        ...(controlId ? { "&:has(:disabled) label[for]": { cursor: "default" } } : null),
      }}
    >
      <Box
        sx={compact
          ? { flex: "1 1 auto", minWidth: 0, display: "grid", gap: 0.25 }
          : { flex: "1 1 18rem", minWidth: 0, display: "grid", gap: 0.125, ...(action ? { pt: centerPad(CONTROL.control, 15 * LINE_HEIGHT.body) } : null) }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: compact ? "nowrap" : "wrap", minWidth: 0 }}>
          <Typography
            component={controlId ? "label" : "div"}
            htmlFor={controlId}
            title={compact && typeof label === "string" ? label : undefined}
            sx={{
              ...(compact
                ? { fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, ...oneLine }
                : { fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }),
              ...(controlId ? LABEL_FOR : null),
            }}
          >
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
          <Typography
            component="div"
            color="text.secondary"
            /* 잘렸을 때 전체 문구가 사라지지 않게 `title` 로 남긴다 — 긴 UA 를 60자로 자르고
               툴팁에 원문을 두는 것과 같은 규칙이다. */
            title={compact && typeof description === "string" ? description : undefined}
            sx={compact
              ? { fontSize: FONT_SIZE.micro, ...oneLine }
              : { fontSize: FONT_SIZE.caption, ...KO_WORD_BREAK }}
          >
            {description}
          </Typography>
        ) : null}
        {children}
      </Box>
      {action ? <Box sx={{ flexShrink: 0 }}>{action}</Box> : null}
    </Box>
    </FlatBadgeSurface>
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
/* 판 안에 놓일 때는 `sx={{ mt: 0 }}` 로 바깥 간격을 끈다 — 설정성 화면은 이제 `/profile`
   처럼 판 2열 격자에 묶음을 담는다(D-457). 제목은 `SectionTitle` 이라 판 제목과 같은 단계다. */
export function SettingList({ title, action, children, sx }) {
  return (
    <Box component="section" sx={{ mt: SECTION_GAP, ...sx }}>
      <SectionTitle component="h2" title={title} action={action} />
      {children}
    </Box>
  );
}

/* 설정 줄 묶음의 그릇 — 첫 줄의 위 괘선과 위 여백을 지운다(구획 제목 바로 아래 줄이 선 하나를 더 그리지 않게).
 * 전에는 메일 · AI · 프로필 화면이 같은 `sx` 한 줄을 다섯 번 복사했다. 줄 사이 선은 `SettingRow` 가 그대로 그린다.
 * `width="form"` — 폼 판 안의 켜고 끄는 줄 · 확인 줄이다. 안의 줄이 같은 판의 반 칸 입력과 같은 폭으로 서서 줄 끝의 체크박스 ·
 * 단추가 반 칸 입력의 오른쪽 끝과 한 세로선에 선다(D-590, `density.js::SETTING_ROWS_FORM`). */
export function SettingRows({ children, className, width, sx }) {
  const classes = ["k-settingrows", width === "form" ? "k-settingrows--form" : null, className].filter(Boolean).join(" ");
  return (
    <Box
      className={classes}
      sx={{
        minWidth: 0, "& > .k-settingrow:first-of-type": { borderTop: 0, pt: 0 },
        ...(width === "form" ? SETTING_ROWS_FORM : null),
        ...sx,
      }}
    >
      {children}
    </Box>
  );
}

/* 🔴 여기 `HEADLINE_GRID` 가 있었다. 「경보 타일처럼 개수가 고정된 줄에만 남는다」고
   적혀 있었는데 **소비처가 0** 이었다 — 지표가 판독 줄(`kit.jsx::MetricStrip`)로 옮겨
   가면서 그 자리가 함께 없어졌고, 이름만 남았다. 소비처 없는 치수는 다음 사람에게
   「여기에 정본이 있다」고 거짓말을 한다(`ui/density.js` 가 같은 이유로 여덟 개를 걷었다). */

/* 🔴 여기 `DashSection` 이 있었다 — 대시보드·진단이 쓰던 **두 번째 구획 부품**이다.
 *
 * 사용자 화면은 `kit.jsx::Section` 을 쓰고 관리자 화면은 이것을 썼다. 간격은 둘 다
 * `SECTION_GAP` 이라 같았지만 제목 단계(h2 vs h3)와 계약(`rule`·`help` 유무)이 달라서,
 * 한쪽에 붙인 것이 다른 쪽에 영영 안 왔다. 갈라져 있던 이유는 `Section` 이 제목 단계를
 * 못 받는 것 하나뿐이었다 — 그 prop(`titleAs`)을 주고 이 부품을 걷었다.
 *
 * 옮기는 법: `<DashSection title="x">` → `<Section title="x" titleAs="h2">`. */

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
    /* 줄 목록이라 그 안의 배지는 면을 갖지 않는다(핸드오프 RULES §2 · F7) — 표(`DataTable`)가
       그러듯 그릇이 선언한다. 예전에는 「멈춤」 같은 위험 배지만 줄 안에서 붉은 면으로 섰다. */
    <FlatBadgeSurface>
      <Box
        className="k-statuslist"
        role="group"
        aria-label={ariaLabel}
        sx={{ "& > *:not(:first-of-type)": { borderTop: 1, borderColor: "divider" } }}
      >
        {children}
      </Box>
    </FlatBadgeSurface>
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
