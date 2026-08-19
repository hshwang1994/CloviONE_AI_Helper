import React from "react";
import Box from "@mui/material/Box";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import { BREAKPOINTS, CONTROL, FONT_SIZE, NAV_BREAKPOINT, RADIUS } from "../ui/theme.js";

/* 상단바 검색 — 기준선의 `.top-search`.
 *
 * 입력을 여기서 직접 받지 않는다. 결과 목록이 뜰 자리가 상단바에는 없고, 커맨드 팔레트가
 * 이미 그 일(키보드 이동, 그룹, 최근 항목)을 한다. 기준선도 같은 이유로 이 자리를
 * `<button class="top-search" data-action="command">` 로 둔다 — 입력처럼 생긴 버튼이 아니라
 * **같은 기능의 더 큰 표적**이다. 그래서 커서도 text 가 아니라 pointer 다(눌리는 것이다).
 *
 * 색은 전부 테마 토큰에서 온다. 그리고 **어느 토큰이냐**가 이 파일이 두 번 틀린 자리다.
 * 처음에는 흰 글자 + 반투명 남색 바탕 리터럴이었고(어두운 상단바 전제), D-141 로 chrome 이
 * 캔버스 계열이 되자 대비 1.21 로 떨어졌다. 그래서 캔버스 토큰(`background.plate`)으로
 * 옮겼는데, D-179 가 chrome 을 다시 인디고로 되돌리자 이번에는 **인디고 하우징에 뚫린
 * 675px 짜리 순백 구멍**이 됐다(라이트 14.13:1 로 셸에서 가장 밝은 면. 독립 리뷰
 * F-W1R-01·F-W1R-13·F-W1R-32 가 배포본 픽셀에서 잡았다).
 *
 * 두 번 다 원인이 같다: **면을 소유한 층이 그 위 컨트롤의 색을 말하지 않았다.** 세 번째를
 * 막는 방법은 값을 또 고르는 것이 아니라 **chrome 자신의 반전 컨트롤 토큰**을 쓰는 것이다 —
 * `chrome.track`/`trackSelected`/`edge` 는 알파 흰빛이라 셸 밝기가 또 바뀌어도 같은 방향으로
 * 따라온다. `theme.js:204` 의 그 토큰 주석이 소비처로 "ConsoleSwitch·**검색 inset**" 을
 * 명시해 뒀는데 W1 은 둘 중 하나만 배선했다. 여기가 나머지 하나다.
 * (`shell-surface-contract.test.js` 가 셸 위 컨트롤이 캔버스 토큰으로 되돌아가는 것을 막는다.)
 */

/* 반응형 두 지점을 **제품의 공통 정책**에서 가져온다. 예전에는 기준선에서 옮겨 온 사설 값
 * 두 개(960 / 720)를 그대로 적어 뒀는데, R-6 이 "Breakpoint 를 페이지마다 따로 만들지 않는다"
 * 고 못박는다. 게다가 그 값들은 셸의 다른 경계와도 어긋나 있었다 — 사이드바가 서랍으로
 * 접히는 860 과 좁은 화면용 검색 아이콘이 나타나는 900(md) 사이에서 **검색 막대와 검색
 * 아이콘이 동시에** 보였다.
 *
 *   검색 막대: 사이드바가 열로 서 있는 폭에서만 보인다(NAV_BREAKPOINT=860, TopBrand 의
 *              락업 경계와 같은 값). 그 아래에서는 셸이 검색 아이콘 하나로 대신한다.
 *   Ctrl K 힌트: lg(1200) 미만에서는 감춘다 — 그 폭에서 막대는 이미 좁다. */
const HIDE_KBD_BELOW = `@media (max-width:${BREAKPOINTS.lg - 0.05}px)`;
const HIDE_BELOW = `@media (max-width:${NAV_BREAKPOINT}px)`;

/* WF1 R4 — 예전엔 "채팅"이 들어 있었다. app/search/models.py(SEARCH_KINDS)는 채팅을 **의도적으로,
 * 타협 없이** 뺀다(1:1 DM이 공용 검색 인덱스에 들어가는 순간 방 멤버십 확인 코드 한 줄만
 * 틀려도 남의 DM이 유출된다 — tests/security/test_search_no_chat.py가 그 경계를 못박는다).
 * 검색되지 않는 것을 검색된다고 광고하고 있었다. 실제 4종(KIND_LABELS와 맞춘다) + 메뉴로 교체. */
export default function TopSearch({ onOpen, placeholder = "티켓, 문서, 게시판, 사용자, 메뉴 검색" }) {
  return (
    <Box
      component="button"
      type="button"
      onClick={onOpen}
      aria-label="통합 검색과 명령 열기"
      sx={(t) => ({
        position: "relative",
        display: "flex", alignItems: "center",
        /* 폭은 세 값이 함께 일한다.
           **rem basis** — 4K 에서 루트 폰트사이즈 레버(styles/root.css)를 타고 같이 커진다.
             720px 리터럴은 그 레버 밖이라 3840 에서 상단바만 혼자 안 자랐다(R-6: 특정
             해상도 전용 Pixel 값을 하드코딩하지 않는다).
           **grow 1** — 남는 폭을 양옆 신축 스페이서와 나눠 갖는다. 예전에는 grow 0 이라
             1920 에서 빈 폭이 33%, 3840 에서 59% 로 벌어져 상단바가 세 개의 섬으로 흩어졌다
             (독립 검수자 실측).
           **상한 56rem** — 그 반대쪽 실패를 막는다. 4K 에서 검색 막대가 1,600px 로 자라면
             그건 검색이 아니라 띠다.
           셸은 이 항목 양옆에 스페이서를 두어 검색을 브랜드 칸과 AI 앵커 사이 가운데에
           놓는다(AppShell). */
        flex: "1 1 45rem", maxWidth: "56rem", minWidth: 0,
        /* 높이도 rem 이다. 셸의 **틀**은 브레이크포인트로 커지는데(상단바 52→68, 사이드바
           248→320) 컨트롤만 px 로 고정되면 4K 에서 비율이 어긋난다 — 실측 1920→3840 에서
           틀은 1.31× 인데 검색 inset 은 1.00× 였다(독립 검수자). `rem` 은 root.css 의
           4K 레버를 그대로 타므로 틀과 같은 배율로 자란다. 나누는 16 은 그 레버의 기본
           단계(`--clv-root-fs: 16px`)이고, CONTROL 은 그 단계 기준의 px 표다. */
        height: `${CONTROL.button / 16}rem`, pl: "2.125rem", pr: "0.5rem",
        border: "1px solid", borderColor: t.palette.chrome.edge, borderRadius: `${RADIUS.sm}px`,
        bgcolor: t.palette.chrome.track, color: t.palette.chrome.onShellMuted,
        cursor: "pointer", textAlign: "left", font: "inherit",
        transition: "background-color .15s, border-color .15s",
        "&:hover": { bgcolor: t.palette.chrome.trackSelected, borderColor: t.palette.chrome.edge },
        /* 링은 면을 소유한 컨테이너(AppBar)가 `--clovir-focus-ring` 으로 내려 준다 —
           Canvas 용 링은 인디고 위에서 1.38~1.83:1 로 사실상 안 보인다. 이 컴포넌트를
           혼자 렌더하는 시험에서는 변수가 없으므로 Canvas 링으로 되돌아간다. */
        "&:focus-visible": {
          outline: `2px solid var(--clovir-focus-ring, ${t.palette.focusRing})`,
          outlineOffset: 2,
        },
        [HIDE_BELOW]: { display: "none" },
      })}
    >
      {/* 기준선 `.top-search .search-ico { position:absolute; left:14px; top:9px }` — 19px 아이콘. */}
      <Box
        aria-hidden="true"
        sx={(t) => ({
          position: "absolute", left: "0.625rem", top: "50%", transform: "translateY(-50%)",
          display: "grid", color: t.palette.chrome.onShellFaint,
        })}
      >
        <SearchRoundedIcon sx={{ fontSize: FONT_SIZE.title }} />
      </Box>
      <Box
        component="span"
        data-testid="top-search-placeholder"
        sx={{
          flex: 1, minWidth: 0,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          color: "inherit", fontSize: FONT_SIZE.bodySm,
        }}
      >
        {placeholder}
      </Box>
      {/* 기준선 `.kbd` + `.top-search .kbd { position:static; margin-left:12px }`. */}
      <Box
        component="kbd"
        sx={(t) => ({
          flexShrink: 0, ml: "0.75rem",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          border: "1px solid", borderColor: t.palette.chrome.edge, borderRadius: `${RADIUS.sm}px`,
          px: "0.3125rem", py: "1px", color: t.palette.chrome.onShellMuted,
          fontSize: FONT_SIZE.micro, fontFamily: "inherit",
          [HIDE_KBD_BELOW]: { display: "none" },
        })}
      >
        Ctrl K
      </Box>
    </Box>
  );
}
