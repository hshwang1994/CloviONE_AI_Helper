import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { paletteAt, StatusDot, statusKind, TONE_ACCENT } from "./kit.jsx";
import { CARD_PADDING, fixedTileTrack, KPI_TILE_TRACK, TILE_GRID_GAP, TILE_PADDING } from "./density.js";
import { useRevealOnce } from "./motion.js";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, MOTION, NUMERIC, RADIUS, remPx } from "./theme.js";

/* 보드·회의의 상태 숫자. 홈의 세로선 `MetricStrip` 과 **다른 부품**이다.
 *
 * 칸마다 위색 띠 · 숫자 · 라벨 · (있으면) 비율이 선다. 숫자는 처음부터 최종값이다 —
 * 세어 올라가는 연출은 값을 늦게 읽게 만든다. 등장만 짧게 한 번 한다. */

/* 톤 표는 `ui/kit.jsx` 한 곳이다 — 논의 갈래 카드(`DiscussBucket`)가 같은 표를 본다.
   두 벌이면 신호 하나가 두 화면에서 다른 색으로 선다. */
function accentOf(kind) {
  return TONE_ACCENT[kind] || "brand.core";
}

/* 7px 점의 정본은 `kit.jsx::StatusDot` 이다 — 점 + 낱말(`DotLabel`)이 같은 점을 쓰려고 키트로
 * 올렸다. 이 파일에서 가져가던 소비처(`DiscussBucket`)가 깨지지 않게 다시 내보낸다. */
export { StatusDot };

/** 판독 하나가 **누를 수 있는가**. `onClick` 을 주면 단추가 된다.
 *
 * 🔴 예전에는 이 부품이 순수 `Box` 였다. 그래서 「지연 3」을 보고도 **그래서 어떤
 * 티켓인지** 알 방법이 없었다 — 숫자가 죽은 픽셀이었다. 회의 화면과 작업 보드가 같은
 * 부품을 쓰므로 여기 한 곳에서 열면 두 화면이 함께 얻는다.
 *
 * 접근 이름은 「라벨 값」 한 덩어리다(`지연 3`). 목록을 고르는 자리면 `aria-pressed` 로
 * 지금 고른 칸을 말한다.
 */
export function StatusKpiTile({
  label, value, kind, pct, primary, reservePct = false,
  onClick, selected, ariaLabel, note,
}) {
  const k = kind || (primary ? "indigo" : statusKind(label));
  const accent = accentOf(k);
  const showPct = pct != null && Number.isFinite(pct);
  const pctSlot = showPct ? `${pct}%` : "\u00a0";
  const pressable = typeof onClick === "function";
  return (
    <Box
      component={pressable ? "button" : "div"}
      type={pressable ? "button" : undefined}
      onClick={onClick}
      aria-pressed={pressable && selected != null ? !!selected : undefined}
      aria-label={pressable ? (ariaLabel || `${label} ${value}`) : undefined}
      sx={{
        minWidth: 0,
        width: "100%",
        height: "100%",
        p: TILE_PADDING,
        borderRadius: `${RADIUS.md}px`,
        bgcolor: "background.plate",
        border: 1,
        borderColor: selected ? "brand.core" : "divider",
        font: "inherit",
        color: "inherit",
        textAlign: "start",
        cursor: pressable ? "pointer" : "default",
        /* 🔴 여기 **3px 위색 띠**가 있었다. 칸마다 다른 색 띠를 이고 있으면 무엇이 중요한지가
           사라진다 — 작업 보드는 일곱 칸이 각자 다른 색으로 서 있었다. 색은 이제 라벨 앞의
           점(7px) 하나가 맡고, 숫자는 잉크색이다. 상태를 색으로만 말하지 않는 것은 그대로다:
           라벨 글자가 언제나 함께 있고 점은 그 글자를 대신하지 않고 거든다. */
        display: "grid",
        gridTemplateRows: reservePct ? "auto auto 1.25rem" : "auto auto",
        gap: 0.25,
        alignContent: "start",
        transition: `border-color ${MOTION.fast} ${MOTION.ease}, background-color ${MOTION.fast} ${MOTION.ease}`,
        ...(pressable ? {
          "&:hover": { bgcolor: "action.hover" },
          "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.brand.core}`, outlineOffset: 2 }),
        } : null),
      }}
    >
      <Typography
        component="span"
        sx={{
          fontSize: FONT_SIZE.title,
          fontWeight: FONT_WEIGHT.extrabold,
          lineHeight: 1.1,
          /* 숫자는 **잉크색**이다. 상태색 숫자가 일곱 개 나란히 서면 어느 것이 큰 값인지가
             색에 묻힌다 — 크기와 굵기가 이미 위계를 말한다. */
          color: "text.primary",
          ...NUMERIC,
        }}
      >
        {value}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ ...KO_KEEP, display: "flex", alignItems: "center", gap: 0.75 }}>
        <StatusDot accent={accent} />
        {label}
      </Typography>
      {/* `note` — 이 숫자를 한정하는 각주(「보관 계정 포함」). 판독 줄이 칸마다 들던 셋째 줄을 그대로
          이어받는다 — 줄 아래 공용 각주로 빼면 어느 숫자를 한정하는지 다시 찾아야 한다(VIS-09). */}
      {note ? (
        <Typography variant="caption" color="text.secondary" sx={{ ...KO_KEEP }}>{note}</Typography>
      ) : null}
      {reservePct ? (
        <Typography
          variant="caption"
          color="text.secondary"
          aria-hidden={!showPct}
          sx={{ ...NUMERIC, minHeight: "1.25rem", lineHeight: 1.25 }}
        >
          {pctSlot}
        </Typography>
      ) : showPct ? (
        <Typography variant="caption" color="text.secondary" sx={{ ...NUMERIC }}>
          {`${pct}%`}
        </Typography>
      ) : null}
    </Box>
  );
}

const KO_KEEP = { wordBreak: "keep-all", overflowWrap: "break-word" };

/** KPI 타일 줄. 칸 수가 정해져 있으면 그 수만큼만 트랙을 만든다 — `auto-fill` 은 빈
 * 트랙을 오른쪽에 남긴다. */
/** KPI 타일 줄. 누를 수 있는 칸이 하나라도 있으면 **고르는 줄**이 된다.
 *
 * `value`(고른 키)와 `onSelect` 를 주면 각 항목의 `key` 가 선택 값이 된다 — 회의 화면의
 * 「오늘 논의할 항목」이 이 줄과 아래 목록을 같은 상태로 잇는다. 항목이 `href` 를 가지면
 * 다른 화면으로 간다(작업 보드의 그 조건으로).
 */
export function StatusKpiStrip({ items, ariaLabel, revealKey, sx, value, onSelect, note }) {
  const list = (items || []).filter(Boolean);
  const shown = useRevealOnce(revealKey == null ? null : String(revealKey));
  if (!list.length) return null;

  const wideTrack = fixedTileTrack(list.length);
  const reservePct = list.some((it) => it.pct != null && Number.isFinite(it.pct));
  const selectable = typeof onSelect === "function";

  /* `note` — 줄 아래 한 줄 캡션. 회의의 요약 줄이 「이 숫자는 회차 전체입니다」처럼 **이
     줄이 무엇을 세는가**를 말하는 자리다. 타일이 눌리지 않을 때 그 사실도 여기서 말한다 —
     예전에는 눌리는 타일과 안 눌리는 타일이 같은 얼굴이라 사용자가 규칙을 못 배웠다. */
  const grid = (
    <Box
      role="group"
      aria-label={ariaLabel}
      sx={{
        display: "grid",
        width: "100%",
        alignItems: "stretch",
        gridTemplateColumns: {
          xs: KPI_TILE_TRACK,
          md: wideTrack,
        },
        gap: TILE_GRID_GAP,
        ...(note ? null : sx),
      }}
    >
      {list.map((it, i) => (
        <Box
          key={it.key || it.label || i}
          sx={{
            height: "100%",
            opacity: shown ? 1 : 0,
            transform: shown ? "none" : "translateY(8px)",
            transition: `opacity ${MOTION.base} ${MOTION.ease}, transform ${MOTION.base} ${MOTION.ease}`,
            transitionDelay: shown ? `${i * 40}ms` : "0ms",
          }}
        >
          <StatusKpiTile
            label={it.label}
            value={it.value}
            kind={it.kind}
            pct={it.pct}
            primary={it.primary}
            reservePct={reservePct}
            onClick={it.onClick || (selectable && it.key ? () => onSelect(it.key) : undefined)}
            selected={it.key != null && value != null ? it.key === value : undefined}
            ariaLabel={it.ariaLabel}
            note={it.note}
          />
        </Box>
      ))}
    </Box>
  );
  if (!note) return grid;
  return (
    <Box sx={sx}>
      {grid}
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75, ...KO_KEEP }}>
        {note}
      </Typography>
    </Box>
  );
}

/** 상태 하나를 말하는 칩 — 점 · 이름 · 건수 · (있으면) 비율.
 *
 * 누를 수 있으면 진짜 `<button>` 이고 `aria-pressed` 로 지금 고른 것을 말한다 —
 * `StatusKpiTile` 과 **같은 계약**이다(그릇만 다르다). */
export function StatusChip({ label, value, accent, pct, onClick, selected, ariaLabel }) {
  const pressable = typeof onClick === "function";
  return (
    <Box
      component={pressable ? "button" : "span"}
      type={pressable ? "button" : undefined}
      /* 시험과 QA 프로브가 이 칸을 잡는 손잡이 — 판독 타일의 `.k-readout` 과 같은 자리다. */
      className="k-status-chip"
      onClick={onClick}
      aria-pressed={pressable && selected != null ? !!selected : undefined}
      aria-label={pressable ? (ariaLabel || `${label} ${value}`) : undefined}
      sx={{
        display: "inline-flex", alignItems: "center", gap: 0.875,
        height: remPx(CONTROL.buttonSm),
        px: 1.375,
        borderRadius: `${RADIUS.sm}px`,
        border: 1,
        borderColor: selected ? "dividerStrong" : "divider",
        bgcolor: selected ? "background.inset" : "background.plate",
        font: "inherit",
        fontSize: FONT_SIZE.caption,
        color: "text.secondary",
        cursor: pressable ? "pointer" : "default",
        transition: `border-color ${MOTION.fast} ${MOTION.ease}, background-color ${MOTION.fast} ${MOTION.ease}`,
        ...(pressable ? {
          "&:hover": { bgcolor: "background.inset" },
          "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
        } : null),
      }}
    >
      <StatusDot accent={accent} />
      <Box component="span" data-readout="label" sx={{ ...KO_KEEP }}>{label}</Box>
      <Box component="span" data-readout="value" sx={{ fontWeight: FONT_WEIGHT.bold, color: "text.primary", ...NUMERIC }}>{value}</Box>
      {pct != null ? <Box component="span" sx={{ ...NUMERIC }}>{pct}%</Box> : null}
    </Box>
  );
}

/** 0건인 상태들을 **한 칸으로 접은** 칩. 점선이라 「여기 값이 없다」를 모양으로 말한다. */
function ZeroChip({ labels }) {
  return (
    <Box
      component="span"
      sx={{
        display: "inline-flex", alignItems: "center",
        height: remPx(CONTROL.buttonSm), px: 1.375,
        borderRadius: `${RADIUS.sm}px`,
        border: "1px dashed",
        borderColor: "divider",
        fontSize: FONT_SIZE.caption,
        color: "text.secondary",
        ...KO_KEEP,
      }}
    >
      {`${labels.join(", ")} 0건`}
    </Box>
  );
}

/** 상태 구성의 **스택 비율 바** — 전체를 한 줄로 나눠 보여 준다. 값이 0 인 상태는 조각을
 *  안 만든다(0px 조각은 색만 남기고 뜻을 못 만든다). 아래 칩이 같은 숫자를 글자로 말하므로
 *  이 바는 `aria-hidden` 이다 — 낭독기가 같은 사실을 두 번 읽지 않는다. */
function RatioBar({ parts, total }) {
  if (!total) return null;
  return (
    <Box
      aria-hidden="true"
      data-ratio-bar=""
      sx={{
        display: "flex", height: 8, borderRadius: "999px", overflow: "hidden",
        bgcolor: "background.sunken",
      }}
    >
      {parts.map((p) => (
        <Box
          key={p.key}
          component="span"
          sx={{ width: `${(100 * p.value) / total}%`, bgcolor: (t) => paletteAt(t, p.accent) }}
        />
      ))}
    </Box>
  );
}

/** 상태 요약 — **카드 하나**다. `StatusKpiStrip` 과 같은 숫자를 다른 그릇에 담는다.
 *
 * 예전에는 상태마다 카드 하나였다. 작업 보드는 일곱 칸이 각자 다른 색 띠를 이고 나란히
 * 섰는데, 그중 **다섯이 0건**이었다 — 빈 카드 다섯이 화면 폭을 먹고 무엇이 중요한지를
 * 지웠다. 담는 그릇을 바꾼다:
 *
 *   ① 전체 숫자 하나만 크게 세운다(잉크색).
 *   ② 비율은 칸마다 적던 세 번째 줄 대신 **스택 바 하나**로 보여 준다.
 *   ③ 상태는 그 아래 칩이 「이름 · 건수 · 비율」로 말하고, 0건인 것들은 한 칸으로 접힌다.
 *   ④ 신호(차단·지연·이슈)는 폭을 억지로 늘린 별도 카드 셋이 아니라 **머리 오른쪽**에
 *      붙는다. 그 자리에서 목록으로 넘어간다.
 *
 * 계약은 `StatusKpiTile` 과 같다 — 누를 수 있는 칩은 진짜 `<button>` 이고 `aria-pressed`
 * 로 지금 고른 것을 말한다. `value`/`onSelect` 로 상태를, `riskValue`/`onRiskSelect` 로
 * 신호를 고른다. 안 주면 칩은 그냥 읽는 것이다(호출부의 기존 동작이 그대로 남는다).
 *
 * `items`/`risks` 항목: `{ key, label, value, kind, onClick, ariaLabel }`. `value` 는
 * 문자열이어도 된다(화면들이 `String(n)` 으로 넘긴다) — 숫자로 읽어 비율을 낸다.
 */
export function StatusSummaryCard({
  title, help, total, totalLabel = "전체", items, risks,
  value, onSelect, riskValue, onRiskSelect, ariaLabel, revealKey, action, notes, unit = "", sx,
}) {
  /* `unit` — 칩 건수 뒤에 붙는 낱말(「3건」). 같은 화면의 다른 자리(도넛 범례)가 「3건」이라 말하면 칩도 같은
     말을 한다. 비율은 숫자로 센다. */
  const shownValue = (v) => (unit && v != null && v !== "-" ? `${v}${unit}` : v);
  /* `notes` — 칩마다 「이 숫자가 무엇을 센 것인지」(`{ key, label, text }`). 판독 줄(MetricStrip)은 칸마다
     셋째 줄로 그 정의를 들었다 — 정의가 사라지면 숫자를 믿을 수 없다(개발자 리포트). 칩 줄 아래 한
     묶음의 정의 목록(dl)으로 선다. */
  const noteList = (notes || []).filter((n) => n && n.text);
  const noteBlock = noteList.length ? (
    <Box component="dl" data-summary-notes="" sx={{ m: 0, display: "flex", flexWrap: "wrap", columnGap: 2, rowGap: 0.25 }}>
      {noteList.map((n) => (
        <Box key={n.key || n.label} sx={{ display: "flex", alignItems: "baseline", gap: 0.5, minWidth: 0 }}>
          <Typography component="dt" variant="caption" sx={{ fontWeight: FONT_WEIGHT.semibold, ...KO_KEEP }}>{n.label}</Typography>
          <Typography component="dd" variant="caption" color="text.secondary" sx={{ m: 0, ...KO_KEEP }}>{n.text}</Typography>
        </Box>
      ))}
    </Box>
  ) : null;
  const shown = useRevealOnce(revealKey == null ? null : String(revealKey));
  /* 색은 톤에서 오지만 **항목이 직접 말할 수도 있다**(`accent`).
     비율 바에서 색을 여럿 쓰면 어느 조각이 주인지가 사라진다 — 뜻이 있는 조각 하나만
     색을 갖고 나머지는 중립으로 두는 화면이 있다. 그때 필요한 것이 이 통로다. */
  const withAccent = (it) => ({
    ...it,
    n: Number(it.value) || 0,
    accent: it.accent || accentOf(it.kind || statusKind(it.label)),
  });
  const list = (items || []).filter(Boolean).map(withAccent);
  const riskList = (risks || []).filter(Boolean).map(withAccent);
  /* **값 하나** 갈래 (RULES §10 — 값이 하나면 큰 숫자 하나, 차트 금지). 부분도 신호도 없고 전체만
     있으면 칩 줄과 비율 바를 그리지 않고 숫자 하나와 이름만 선다(「안 읽음 N」 · 「활성 스케줄」).
     예전에는 이 자리가 판독 줄(`MetricStrip`) 한 칸이었다. */
  if (!list.length && !riskList.length) {
    if (total == null || total === "") return null;
    return (
      <Box
        role="group"
        aria-label={ariaLabel}
        data-summary-single=""
        sx={{
          p: CARD_PADDING, borderRadius: `${RADIUS.md}px`, bgcolor: "background.plate",
          border: 1, borderColor: "divider", display: "grid", rowGap: 0.75,
          opacity: shown ? 1 : 0,
          transition: `opacity ${MOTION.base} ${MOTION.ease}`,
          ...sx,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "baseline", flexWrap: "wrap", gap: 1 }}>
          {title ? (
            <Typography component="span" sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold, ...KO_KEEP }}>{title}</Typography>
          ) : null}
          {/* 시험 · 프로브가 「이 카드의 큰 숫자와 그 이름」을 순서가 아니라 이름으로 짚는 손잡이(`data-readout`). */}
          <Box component="span" data-summary-total="" sx={{ display: "contents" }}>
            <Typography component="span" data-readout="value" sx={{ fontSize: FONT_SIZE.pageTitle, fontWeight: FONT_WEIGHT.bold, lineHeight: 1, ...NUMERIC }}>
              {total}
            </Typography>
            <Typography component="span" data-readout="label" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold }}>{totalLabel}</Typography>
          </Box>
          {action ? <Box sx={{ marginInlineStart: "auto" }}>{action}</Box> : null}
        </Box>
        {help ? <Typography variant="caption" color="text.secondary" sx={{ ...KO_KEEP }}>{help}</Typography> : null}
        {noteBlock}
      </Box>
    );
  }

  /* **전체를 준 카드와 안 준 카드는 다른 것을 말한다.**
   *
   * `total` 을 주면 「이 칩들은 한 전체의 부분이다」라는 선언이다 — 그때만 스택 바와 비율을
   * 그린다. 안 주면 칩들은 서로 겹칠 수 있는 축이라(홈의 「오늘 마감」과 「지연」은 한
   * 티켓이 둘 다일 수 있다) 합이 전체가 아니고, 그 합으로 낸 비율은 거짓이다. 그 경우
   * 칩은 건수만 말한다.
   *
   * 값이 `null` 인 항목은 **0 이 아니라 「모른다」** 다(티켓 원본과 끊겼을 때). 0건으로
   * 접으면 없는 사실을 만든다 — 따로 세우고 `-` 로 표시한다. */
  const sum = Number(total);
  const whole = Number.isFinite(sum) && sum > 0 ? sum : 0;
  const unknown = list.filter((it) => it.value == null);
  const known = list.filter((it) => it.value != null);
  const selectable = typeof onSelect === "function";
  /* 🔴 **누를 수 있는 칸은 접지 않는다.**
   *
   * 0건 접기의 값어치는 자리를 아끼는 것이다. 그런데 그 칸이 눌러서 목록을 거르는
   * 단추이면, 접는 순간 **작동하던 조작기가 사라진다** — 홈에서 「7일 내 마감 0건」을
   * 눌러 「그 조건으로는 없다」를 확인하는 길이 그렇게 막힌다(「필터 때문에 없다」와
   * 「원래 없다」는 이 화면이 일부러 구분하는 두 사실이다).
   * 작업 보드는 0건 상태에 `onClick` 을 안 주므로(갈 곳이 없다) 거기서는 그대로 접힌다.
   * 접히는 조건을 「값이 0」이 아니라 「값이 0이고 할 수 있는 일이 없다」로 둔다. */
  const pressableAt = (it) => typeof it.onClick === "function" || (selectable && it.key != null);
  const filled = known.filter((it) => it.n > 0 || pressableAt(it));
  const empty = known.filter((it) => it.n === 0 && !pressableAt(it));
  const riskSelectable = typeof onRiskSelect === "function";

  /* 위험 요약. 값이 0 인 신호는 안 세운다(누를 것이 없는 단추다). */
  const shownRisks = riskList.filter((it) => it.n > 0);
  const riskChip = (it) => (
    <StatusChip
      key={it.key || it.label}
      label={it.label}
      value={shownValue(it.value)}
      accent={it.accent}
      onClick={it.onClick || (riskSelectable && it.key ? () => onRiskSelect(it.key) : undefined)}
      selected={it.key != null && riskValue != null ? it.key === riskValue : undefined}
      ariaLabel={it.ariaLabel}
    />
  );

  /* 🔴 위험 칩이 **어디에 서는가**는 머리 오른쪽에 그림(`action`)이 있는가로 갈린다.
   *
   * 머리 오른쪽은 슬롯 하나다. 거기에 위험 칩과 그림이 함께 서면 둘이 한 덩어리로 읽힌다 —
   * 내 업무량에서 완료율 링 옆에 「지연 14」가 붙자 그렇게 됐다. 그 둘은 서로 다른 축이다:
   * 완료율은 **해낸 것**을 세고 지연은 **위태로운 것**을 센다. 한 묶음으로 보이면 어느
   * 쪽이 이 카드의 답인지가 흐려진다.
   *
   * 그림이 있으면 그림이 그 자리를 갖고 위험 칩은 아래 상태 칩 줄로 내려간다. 거기서도
   * 섞이지 않는 이유는 **구분 간격**이다 — 부분 셋과 위험 사이가 칩 사이 간격보다 넓어서
   * 같은 줄에 있어도 두 묶음으로 읽힌다. */
  const risksInHeader = !action;

  return (
    <Box
      role="group"
      aria-label={ariaLabel}
      sx={{
        /* 판의 여백은 판 규약값 하나다(`CARD_PADDING` 20 — 핸드오프 D-16). 안쪽 줄 사이는 12px
           하나라 숫자 줄 · 비율 바 · 칩 줄이 같은 간격으로 선다. */
        p: CARD_PADDING,
        borderRadius: `${RADIUS.md}px`,
        bgcolor: "background.plate",
        border: 1,
        borderColor: "divider",
        display: "grid",
        rowGap: 1.5,
        opacity: shown ? 1 : 0,
        transform: shown ? "none" : "translateY(8px)",
        transition: `opacity ${MOTION.base} ${MOTION.ease}, transform ${MOTION.base} ${MOTION.ease}`,
        ...sx,
      }}
    >
      {/* 머리 줄은 **두 덩어리**다 — 왼쪽은 이 카드가 무엇을 세는가, 오른쪽은 그 안에서
          지금 위험한 것과 한 장으로 요약한 그림. 예전에는 위험 칩과 `action` 이 왼쪽 글과
          같은 flex 줄의 형제라, 좁아지면 그림이 칩 사이로 끼어들어 서로 겹쳐 읽혔다.
          오른쪽을 한 덩어리로 묶으면 접힐 때도 그 둘이 함께 내려간다.
          세로 정렬이 `center` 인 이유: 오른쪽 덩어리는 글이 아니라 그림이라 글자 기준선
          (`baseline`)에 걸 것이 없다 — 걸면 링이 위로 떠서 아래 칩 줄과 겹친다. */}
      <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1.5 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", flexWrap: "wrap", gap: 1, minWidth: 0 }}>
          {title ? (
            <Typography component="span" sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold, ...KO_KEEP }}>
              {title}
            </Typography>
          ) : null}
          {Number.isFinite(sum) ? (
            <Box component="span" data-summary-total="" sx={{ display: "contents" }}>
              <Typography component="span" data-readout="value" sx={{ fontSize: FONT_SIZE.pageTitle, fontWeight: FONT_WEIGHT.bold, lineHeight: 1, ...NUMERIC }}>
                {total}
              </Typography>
              <Typography component="span" data-readout="label" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold }}>
                {totalLabel}
              </Typography>
            </Box>
          ) : null}
          {help ? (
            <Typography component="span" variant="caption" color="text.secondary" sx={{ ...KO_KEEP }}>{help}</Typography>
          ) : null}
        </Box>
        <Box sx={{ flex: 1 }} />
        <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1.25, minWidth: 0 }}>
          {risksInHeader ? shownRisks.map(riskChip) : null}
          {action}
        </Box>
      </Box>
      <RatioBar parts={filled.filter((it) => it.n > 0)} total={whole} />
      {/* 칩 줄은 **두 묶음**이다. 묶음 안은 8px, 묶음 사이는 12px — 그 한 단 차이가
          「전체를 나눈 부분」과 「그중 위태로운 것」의 경계다. */}
      <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.5 }} data-chip-row="">
        <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1 }} data-chip-group="parts">
          {unknown.map((it) => (
            <StatusChip
              key={it.key || it.label}
              label={it.label}
              value="-"
              accent={it.accent}
              onClick={it.onClick || (selectable && it.key ? () => onSelect(it.key) : undefined)}
              selected={it.key != null && value != null ? it.key === value : undefined}
              ariaLabel={it.ariaLabel}
            />
          ))}
          {filled.map((it) => (
            <StatusChip
              key={it.key || it.label}
              label={it.label}
              value={shownValue(it.value)}
              accent={it.accent}
              pct={whole ? Math.round((100 * it.n) / whole) : null}
              onClick={it.onClick || (selectable && it.key ? () => onSelect(it.key) : undefined)}
              selected={it.key != null && value != null ? it.key === value : undefined}
              ariaLabel={it.ariaLabel}
            />
          ))}
          {empty.length ? <ZeroChip labels={empty.map((it) => it.label)} /> : null}
        </Box>
        {!risksInHeader && shownRisks.length ? (
          <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1 }} data-chip-group="risks">
            {shownRisks.map(riskChip)}
          </Box>
        ) : null}
      </Box>
      {noteBlock}
    </Box>
  );
}
