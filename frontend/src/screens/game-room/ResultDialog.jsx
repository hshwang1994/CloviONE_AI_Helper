import React from "react";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import { keyframes } from "@mui/system";
import HowToVoteRoundedIcon from "@mui/icons-material/HowToVoteRounded";
import { ActionFooter, Badge, Button, FlatBadgeSurface, Modal, useToast } from "../../ui/kit.jsx";
import { AVATAR_SIZE, UserAvatar } from "../../ui/UserAvatar.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, LINE_HEIGHT, NUMERIC, RADIUS } from "../../ui/theme.js";
import { pop, rise } from "./constants.js";
import { initialOf } from "./people.js";

/* 결과 대화 상자 (D-576) — 여덟 게임의 결과 발표가 같은 상자 하나다.
 *
 * 몸은 두 단계다: `announcing`(「결과를 발표합니다」 + 비어 있는 영웅 자리가 숨 쉰다) → `revealed`(당첨자). 단계 · 열림은 컨트롤러의
 * 상태 기계(`revealMachine.js`)가 정하고 이 상자는 그리기만 한다 — 닫아도 판은 마지막 장면으로 남고, 툴바의 [결과 보기]가 같은
 * 단계로 다시 연다(재발표 · 축포 없음).
 *
 * 공개 단계의 얼굴:
 *   한 명    영웅 자리 — 「당첨을 축하합니다!」 · 96px 얼굴(브랜드 테두리 둘) · 이름(페이지 제목 크기) · 표지(당첨 · 우승 · 승리 · 선택됨) · 문장
 *   순위     (구슬 레이스의 여러 당첨자) 1 · 2 · 3 등이 시상대처럼 서고 나머지는 줄
 *   여럿     같은 무게의 카드 격자(`data-result-winners="grid"`), 12명을 넘으면 목록
 *   차분     (팀 나누기 · 사다리 · 무승부) 제목과 문장만, 상세가 펼쳐진 채
 * 상세(사다리 · 득표 · 점수 · 대진 · 숫자 · 손 · 완주 순위)는 접는 칸이다. 발은 [상세 보기/접기] [결과 복사] | [다시 하기](방장) [닫기].
 * 마스코트를 두지 않는다 — 결과의 주인공은 사람이다.
 *
 * 하네스 고리(`data-result-panel` = 단계 · `data-result-mood` · `data-result-winners` 안의 `[title]` 이름 · `data-result-detail`)는
 * `scripts/ui_qa/games_e2e.py` 가 읽는다. */

const breathe = keyframes`
  0%, 100% { transform: scale(.96); opacity: .55; }
  50% { transform: scale(1.02); opacity: 1; }
`;
const blink = keyframes`
  0%, 80%, 100% { opacity: .2; }
  40% { opacity: 1; }
`;

const NAME_CLAMP = {
  ...KO_WORD_BREAK, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
  maxWidth: "100%",
};

/* 머리글자 크기 — 얼굴 크기마다 글자 역할 하나(96 → 판독값 · 72 → 페이지 제목 · 40 → 제목 · 30 → 본문). */
const INITIAL_SX = {
  hero: { fontSize: FONT_SIZE.readout },
  xl: { fontSize: FONT_SIZE.pageTitle },
  lg: { fontSize: FONT_SIZE.title },
  md: { fontSize: FONT_SIZE.body },
};

const heroRing = (t) => `0 0 0 3px ${t.palette.background.paper}, 0 0 0 6px ${t.palette.primary.main}, 0 0 0 14px ${alpha(t.palette.primary.main, 0.18)}`;

/* 얼굴 — 사람은 제품의 얼굴(`UserAvatar`), 자유 이름 구슬은 구슬 색 원 + 머리글자, 투표 보기는 투표 표지. */
function Face({ w, size, ring = false }) {
  const box = AVATAR_SIZE[size] || size;
  if (w.kind === "option") {
    return (
      <Box aria-hidden="true" sx={(t) => ({
        width: box, height: box, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center",
        bgcolor: alpha(t.palette.primary.main, 0.12), color: "primary.main", ...(ring ? { boxShadow: heroRing(t) } : null),
      })}>
        <HowToVoteRoundedIcon sx={{ width: "46%", height: "46%" }} />
      </Box>
    );
  }
  if (w.user_id || w.person) {
    return (
      <UserAvatar person={w.person || { user_id: w.user_id, name: w.name }} name={w.name} size={size}
        sx={ring ? { boxShadow: heroRing } : undefined} />
    );
  }
  return (
    <Box aria-hidden="true" sx={(t) => ({
      width: box, height: box, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center",
      bgcolor: w.color || t.palette.primary.main, color: t.palette.common.white, fontWeight: FONT_WEIGHT.bold,
      ...(INITIAL_SX[size] || INITIAL_SX.md), textShadow: `0 1px 2px ${alpha(t.palette.common.black, 0.35)}`,
      /* 구슬의 빛 — 그라디언트 대신 안쪽 그림자 두 겹(왼쪽 위 밝게 · 오른쪽 아래 어둡게). */
      boxShadow: [
        `inset 0.35em 0.3em 0.7em ${alpha(t.palette.common.white, 0.35)}`,
        `inset -0.3em -0.35em 0.6em ${alpha(t.palette.common.black, 0.18)}`,
        ring ? heroRing(t) : `inset 0 0 0 2px ${alpha(t.palette.common.white, 0.35)}`,
      ].join(", "),
    })}>
      {initialOf(w.name)}
    </Box>
  );
}

function RankBadge({ rank }) {
  const top = rank <= 3;
  return (
    <Box component="span" aria-label={`${rank}등`} sx={{
      flexShrink: 0, minWidth: "1.75rem", height: "1.75rem", px: 0.75, borderRadius: `${RADIUS.full}px`,
      display: "inline-grid", placeItems: "center", ...NUMERIC,
      fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold,
      bgcolor: top ? "primary.main" : "action.hover", color: top ? "primary.contrastText" : "text.secondary",
    }}>
      {rank}
    </Box>
  );
}

function Hero({ model }) {
  const w = model.winners[0];
  return (
    <Box data-result-winners="single" sx={{ display: "grid", justifyItems: "center", gap: 1.25, textAlign: "center", pt: 0.5 }}>
      <Typography component="p" sx={{ fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.bold, color: "primary.main", ...KO_WORD_BREAK }}>
        {model.heroTitle}
      </Typography>
      <Box sx={{ my: 1.25, animation: `${pop} .55s cubic-bezier(.34,1.56,.64,1) both` }}>
        <Face w={w} size="hero" ring />
      </Box>
      <Typography component="h3" title={w.name} sx={{ ...NAME_CLAMP, fontSize: FONT_SIZE.pageTitle, fontWeight: FONT_WEIGHT.extrabold, lineHeight: LINE_HEIGHT.pageTitle }}>
        {w.name}
      </Typography>
      <FlatBadgeSurface><Badge value={model.winnerLabel} kind="info" emphasis="strong" /></FlatBadgeSurface>
      <Typography sx={{ color: "text.secondary", ...KO_WORD_BREAK }}>{model.sentence}</Typography>
    </Box>
  );
}

function Podium({ winners }) {
  const top = winners.slice(0, 3);
  const rest = winners.slice(3);
  /* 시상대 — 셋이면 2 · 1 · 3(가운데가 1등), 둘이면 1 · 2. 1등만 얼굴이 한 단 크다. */
  const order = top.length === 3 ? [top[1], top[0], top[2]] : top;
  return (
    <Box data-result-winners="ranked" sx={{ display: "grid", gap: 2 }}>
      <Box component="ol" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gridTemplateColumns: `repeat(${order.length}, minmax(0, 1fr))`, gap: 1.5, alignItems: "end" }}>
        {order.map((w) => {
          const first = w.rank === 1;
          return (
            <Box component="li" key={w.id} sx={(t) => ({
              display: "grid", justifyItems: "center", gap: 0.75, textAlign: "center", minWidth: 0, px: 1, pt: first ? 1.5 : 1, pb: 1.25,
              borderRadius: `${RADIUS.md}px`, border: 1, borderColor: first ? "primary.main" : "divider",
              bgcolor: first ? alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.18 : 0.08) : "transparent",
              animation: `${rise} .4s ${first ? 0 : 120}ms ease both`,
            })}>
              <RankBadge rank={w.rank} />
              <Face w={w} size={first ? "xl" : "lg"} ring={first} />
              <Typography component="span" title={w.name} sx={{ ...NAME_CLAMP, fontWeight: FONT_WEIGHT.bold, fontSize: first ? FONT_SIZE.title : FONT_SIZE.body }}>
                {w.name}
              </Typography>
            </Box>
          );
        })}
      </Box>
      {rest.length ? (
        <Box component="ol" start={4} sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
          {rest.map((w) => (
            <Box component="li" key={w.id} sx={{ display: "flex", alignItems: "center", gap: 1.25, px: 1, py: 0.5, borderRadius: `${RADIUS.sm}px`, bgcolor: "background.inset" }}>
              <RankBadge rank={w.rank} />
              <Face w={w} size="md" />
              <Typography component="span" title={w.name} sx={{ ...NAME_CLAMP, WebkitLineClamp: 1, flex: 1, minWidth: 0, fontWeight: FONT_WEIGHT.semibold }}>{w.name}</Typography>
            </Box>
          ))}
        </Box>
      ) : null}
    </Box>
  );
}

function WinnerGrid({ winners }) {
  const asList = winners.length > 12;
  return (
    <Box component="ul" data-result-winners="grid" data-result-list={asList ? "" : undefined} sx={{
      listStyle: "none", m: 0, p: 0, display: "grid", gap: 1,
      gridTemplateColumns: asList ? "minmax(0, 1fr)" : { xs: "repeat(2, minmax(0, 1fr))", sm: "repeat(auto-fit, minmax(9rem, 1fr))" },
    }}>
      {winners.map((w, i) => (
        <Box component="li" key={w.id} sx={(t) => ({
          display: "flex", flexDirection: asList ? "row" : "column", alignItems: "center", gap: 1, p: 1.5, minWidth: 0,
          textAlign: asList ? "left" : "center", borderRadius: `${RADIUS.md}px`, border: 1, borderColor: alpha(t.palette.primary.main, 0.4),
          bgcolor: alpha(t.palette.primary.main, t.palette.mode === "dark" ? 0.16 : 0.07),
          animation: `${rise} .38s ${Math.min(i, 8) * 50}ms ease both`,
        })}>
          <Face w={w} size={asList ? "md" : "lg"} />
          <Typography component="span" title={w.name} sx={{ ...NAME_CLAMP, fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.body, flex: asList ? 1 : undefined, minWidth: 0 }}>
            {w.name}
          </Typography>
          {w.note ? <Typography variant="body2" color="text.secondary" sx={NUMERIC}>{w.note}</Typography> : null}
        </Box>
      ))}
    </Box>
  );
}

function Announcing() {
  return (
    <Box data-result-phase="announcing" aria-live="polite" sx={{ display: "grid", justifyItems: "center", gap: 2, py: 3 }}>
      <Box aria-hidden="true" sx={(t) => ({
        width: AVATAR_SIZE.hero, height: AVATAR_SIZE.hero, borderRadius: "50%",
        bgcolor: alpha(t.palette.primary.main, 0.1), boxShadow: `0 0 0 3px ${alpha(t.palette.primary.main, 0.35)}, 0 0 0 14px ${alpha(t.palette.primary.main, 0.08)}`,
        animation: `${breathe} 1.1s ease-in-out infinite`,
      })} />
      <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.title }}>
        결과를 발표합니다
        {[0, 1, 2].map((i) => (
          <Box key={i} component="span" aria-hidden="true" sx={{ display: "inline-block", animation: `${blink} 1.2s ${i * 0.2}s infinite` }}>.</Box>
        ))}
      </Typography>
    </Box>
  );
}

/**
 * props: model(`buildResultModel`) · reveal(`{ key, phase, open, closeDialog }`) · isHost · onReplay · replayPending · container · fullscreen
 */
/* 대화 상자의 몸 — 열릴 때와 새 결과로 바뀔 때 초점을 받는다.
 *
 * 대화 상자가 스스로 열리면(폴링이 결과를 가져온 순간 · 늦은 입장) MUI 초점 가두기가 판(Paper)에 초점을 주고, 전역 `:focus-visible`
 * 링이 판 전체를 둘렀다 — 마우스를 누른 적 없는 화면(지켜보기만 하는 참가자)에서 늘 보였다(Firefox 실측). 초점을 몸으로 옮긴다:
 * 키보드 사용자는 그대로 대화 상자 안이고(Tab 이 발의 단추로 간다) 판에 링이 서지 않는다. 이 효과는 **대화 상자 안의 자식**이라
 * 같은 커밋의 초점 가두기 효과보다 먼저 돈다(자식 효과가 먼저다) — 초점이 이미 안에 있으므로 가두기는 판으로 옮기지 않고, 닫을 때
 * 돌아갈 자리(초점 이벤트의 relatedTarget)도 가두기가 그대로 잡는다. 예전에는 이 효과가 대화 상자 바깥(부모)에 있어 포털이 몸을
 * 그리기 전에 돌았고 아무것도 하지 않았다. */
function FocusedBody({ focusKey, children, sx, ...rest }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    try { el.focus({ preventScroll: true }); } catch (e) { /* 오래된 브라우저 */ }
  }, [focusKey]);
  return (
    <Box ref={ref} tabIndex={-1} sx={{ outline: "none", "&:focus-visible": { outline: "none" }, ...sx }} {...rest}>
      {children}
    </Box>
  );
}

export function ResultDialog({ model, reveal, isHost, onReplay, replayPending = false, container, fullscreen = false }) {
  const toast = useToast();
  const [detailOpen, setDetailOpen] = React.useState(!!model.detailDefaultOpen);
  const [copied, setCopied] = React.useState(false);
  const detailId = React.useId();
  React.useEffect(() => { setDetailOpen(!!model.detailDefaultOpen); setCopied(false); }, [reveal.key]); // eslint-disable-line react-hooks/exhaustive-deps
  React.useEffect(() => {
    if (!copied) return undefined;
    const t = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(t);
  }, [copied]);
  const phase = reveal.phase === "none" ? "revealed" : reveal.phase;
  const revealed = phase === "revealed";
  const win = model.mood === "win" && model.winners.length > 0;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(model.copyText);
      /* 전체 화면에서는 토스트(문서의 포털)가 가려진다 — 그 자리에서 말한다. */
      if (fullscreen) setCopied(true);
      else if (toast) toast("결과를 복사했습니다.", "success");
    } catch (e) {
      if (toast && !fullscreen) toast("복사하지 못했습니다. 글을 직접 선택해 복사하세요.", "error");
    }
  };

  const footer = (
    <ActionFooter
      placement="modal"
      extra={revealed ? (
        <>
          {model.detail ? (
            <Button onClick={() => setDetailOpen((v) => !v)} aria-expanded={detailOpen} aria-controls={detailId}>
              {detailOpen ? `${model.detailLabel} 접기` : `${model.detailLabel} 보기`}
            </Button>
          ) : null}
          {model.copyText ? <Button onClick={copy}>결과 복사</Button> : null}
          {copied ? <Typography component="span" role="status" variant="body2" sx={{ color: "success.strong", fontWeight: FONT_WEIGHT.semibold }}>복사했습니다</Typography> : null}
        </>
      ) : null}
    >
      {/* 끝 동작 묶음 — 전화 폭(xs)에서는 한 줄을 다 차지해 상세 · 복사 아래 둘째 줄 오른쪽에 함께 선다. 넷이 한 줄에 안 들어가면
          「닫기」만 홀로 내려가 짝이 깨졌다(390 실측). 그 위 폭에서는 예전처럼 같은 줄 오른쪽이다. */}
      <Box data-result-actions="" sx={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 1, flexBasis: { xs: "100%", sm: "auto" }, minWidth: 0 }}>
        {isHost && revealed ? <Button variant="primary" onClick={onReplay} loading={replayPending}>다시 하기</Button> : null}
        <Button onClick={reveal.closeDialog}>닫기</Button>
      </Box>
    </ActionFooter>
  );

  return (
    <Modal open={!!reveal.open} onClose={reveal.closeDialog} title={`${model.game} 결과 발표`} size={model.size} container={container} footer={footer}>
      <FocusedBody
        focusKey={reveal.key}
        data-result-dialog=""
        data-result-panel={phase}
        data-result-mood={model.mood}
        /* 전화에서는 대화 상자가 화면 전체라(kit `Modal`) 몸을 세로 가운데에 세운다 — 위에 몰리고 아래가 비지 않게. */
        sx={{
          display: "grid", gap: 2.5, minWidth: 0,
          alignContent: { xs: "center", sm: "start" }, minHeight: { xs: "100%", sm: "auto" },
        }}
      >
        {!revealed ? <Announcing /> : (
          <>
            {win && model.winners.length === 1 ? <Hero model={model} /> : (
              <Box sx={{ display: "grid", gap: 0.75, textAlign: "center" }}>
                <Typography component="h3" sx={{ fontSize: FONT_SIZE.pageTitle, fontWeight: FONT_WEIGHT.extrabold, lineHeight: LINE_HEIGHT.pageTitle, ...KO_WORD_BREAK }}>
                  {model.headline}
                </Typography>
                {model.sentence ? <Typography sx={{ color: "text.secondary", ...KO_WORD_BREAK }}>{model.sentence}</Typography> : null}
              </Box>
            )}
            {win && model.winners.length > 1 ? (model.ranked ? <Podium winners={model.winners} /> : <WinnerGrid winners={model.winners} />) : null}
            {model.note ? (
              <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", ...KO_WORD_BREAK }}>{model.note}</Typography>
            ) : null}
            {model.detail ? (
              <Box id={detailId} data-result-detail={detailOpen ? "open" : "closed"}>
                <Collapse in={detailOpen} unmountOnExit>
                  <Box sx={{ pt: 0.5 }}>{model.detail}</Box>
                </Collapse>
              </Box>
            ) : null}
          </>
        )}
      </FocusedBody>
    </Modal>
  );
}
