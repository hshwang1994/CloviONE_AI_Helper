import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DevicesOtherRoundedIcon from "@mui/icons-material/DevicesOtherRounded";
import { api } from "../lib/api.js";
import { fmtDateTime, fmtRelative, shortUA } from "../lib/format.js";
import { useInstantSave } from "../lib/useInstantSave.js";
import { useAuth } from "../app/auth.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";
import { AvatarCropDialog } from "../ui/AvatarCropDialog.jsx";
import { DefaultAvatarPicker } from "../ui/DefaultAvatarPicker.jsx";
import { ROLE_KO } from "../app/navConfig.js";
import { invalidateNotifications } from "../app/notification-keys.js";
import { invalidatePersonFaces } from "./ticket-views.js";
import {
  Badge, Button, Callout, Card, EmptyState, ErrorState, Field, FieldRow, PageHeader, SectionTitle, Skeleton,
  useConfirm, useToast,
} from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "../ui/theme.js";
import { Note, SettingRow } from "../ui/adminKit.jsx";
import { GRID_GAP, pairTracks } from "../ui/density.js";
/* 화면 강조색은 예전에 자기 라우트(`/my-display`)를 갖고 있었다 — 설정 하나뿐인 화면이
 * 사이드바 항목도 없이 계정 메뉴에서만 열렸고, 그래서 그 화면에서는 사이드바 선택 표시가
 * 통째로 사라졌다. 개인 설정은 이미 이 화면이 전부 갖고 있으므로(알림·방해금지·둘러보기)
 * 여기로 합친다(S19). 옛 주소는 이 화면으로 넘긴다. */
import { AccentPicker } from "./settings/AccentPicker.jsx";
import { MailNotificationCard } from "./profile/MailNotificationCard.jsx";

/* 내 프로필 — 신원 머리 · 알림 설정 · 내 기기 · 방해금지 · 강조색 · 둘러보기.
 *
 * 예전에는 상단바 메뉴의 작은 모달 하나가 역할·부서·마지막 로그인만 읽어 주고 끝이었다.
 * "활성 세션 3개"라고 알려 주면서 정작 끊을 방법은 없어서, 그 숫자를 본 사람이 할 수 있는
 * 일이 비밀번호 변경뿐이었다. 이 화면이 그 공백을 메운다.
 *
 * 이 화면이 지키는 두 가지:
 *   1) **방해금지는 미루는 것이지 삼키는 것이 아니다.** 화면 문구도 그렇게 쓴다 —
 *      "알림은 그대로 쌓이고 배지만 조용해집니다". 사용자가 무엇을 포기하는지 모르는 채
 *      켜게 두면, 놓친 다음 날 이 기능을 영영 안 쓴다.
 *   2) **지금 쓰는 기기를 표시한다.** 어느 줄이 이 창인지 모르면 무서워서 아무것도 못 끊는다.
 *
 * px 폰트 크기를 쓰지 않는다(4K 레버는 루트 폰트사이즈 하나다). MUI Grid 도 쓰지 않는다
 * (MUI 7 에서 xs={12} 가 조용히 무시된다) — Box + display:grid 다.
 */

/* 격자의 정본은 `ui/density.js::pairTracks` 다 — 관리자 설정 4탭이 같은 격자를 쓴다(D-457).
 * 여기서 `pairTracks` 자체는 안 건드린다: 소비처 여덟 곳이 서로 다른 값을 넘기고 있고,
 * 이 화면의 사정을 공용 층 기본값으로 만들면 나머지 일곱이 함께 움직인다(CLAUDE.md §5).
 *
 * **반반이다**(D-470). 폭을 실제로 재면 두 열의 요구가 거의 같다 — 판을 복제해
 * `width:max-content` 로 펴서 잰 값(2560)이 열 위치별 최대 824 대 833, 비 1.01 이었다.
 * 그 값을 정하는 것은 항목 개수가 아니라 판마다 하나씩 있는 설명문 한 줄이라, 알림 유형이
 * 스물이든 마흔이든 폭은 그대로다. 기울이면 열 사이 이음매가 어긋나고("네모 칸 4개가 따로
 * 노는 것 같다"), 좁은 쪽(뷰포트 1200)에서는 좁은 열의 값 칸이 접힌다.
 *
 * 세로 간격도 같은 값이다. 판끼리의 간격은 `GRID_GAP`(24px) 하나이고, 가로 이음매를
 * 그것으로 그리면서 세로만 20px 로 두면 한 화면에서 두 값이 나란히 보인다. */
/** 알림 설정 | 내 기기·방해금지·강조색·둘러보기. **한 줄이고 반반이다.** */
const TWO_COL_EVEN = pairTracks("minmax(0, 1fr) minmax(0, 1fr)");

/* 신원 머리와 설정 판의 여백 리듬 — 판 안쪽 줄 사이는 12px 하나다. */
const CARD_ROWS = { display: "grid", rowGap: 1.5, minWidth: 0 };

/* 한 줄로 서는 글 — 넘치면 말줄임이고 전체 문구는 `title` 이 갖는다. */
const ONE_LINE = { minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

// 방해금지 빠른 시간. '무한'을 기본으로 두지 않는다 — 실수로 켜 두고 잊는 것이 이 기능의
// 가장 흔한 실패다.
const DND_PRESETS = [
  { minutes: 30, label: "30분" },
  { minutes: 60, label: "1시간" },
  { minutes: 180, label: "3시간" },
  { minutes: 0, label: "직접 끌 때까지" },
];

/* 폼 한 칸의 **고정 세로 트랙**(라벨 20 · 컨트롤 34 · 도움말 auto)은 `kit.jsx::Field` 가 그린다 — 이 화면이 먼저 만들었고
 * 새 티켓이 둘째 소비처라 키트로 올렸다(D-527). */

/* 값과 값 사이의 **점**. 글자가 아니라 도형이다.
 *
 * 이유가 둘이다. 하나, 이 저장소는 화면 문구에서 가운뎃점을 안 쓴다(`check_user_text.py`).
 * 둘, 구분 기호는 읽을 것이 아니라 볼 것이다 — 낭독기가 「플랫폼개발팀 가운뎃점 팀장」이라고
 * 읽으면 사실 사이에 없던 낱말이 하나 생긴다. `aria-hidden` 인 도형이 그 둘을 다 푼다. */
function Dot() {
  return (
    <Box
      aria-hidden="true"
      component="span"
      data-fact-dot=""
      sx={{ width: 3, height: 3, borderRadius: "999px", bgcolor: "text.faint", flexShrink: 0 }}
    />
  );
}

/* 신원의 사실들 — **라벨 없이 값만 한 줄**이다.
 *
 * 예전에는 `DetailRow` 여섯 줄이었고(이름·이메일·역할·부서·직책·마지막 로그인) 라벨이 10rem
 * 고정 열을 가졌다. 그것을 「라벨 위, 값 아래」 쌍 셋으로 바꿨더니 라벨 열이 세 개 나란히
 * 서서 여전히 **표로 읽혔다** — 열이 가로로 누웠을 뿐 라벨과 값이 격자를 이루는 것은 같다.
 *
 * 신원 정보는 이름표가 필요 없다. 팀 이름이 부서라는 것, 골뱅이가 든 문자열이 메일이라는
 * 것은 값 자체가 말한다. 이름표가 필요한 유일한 값은 마지막 로그인이다 — 날짜 하나만 놓으면
 * 그것이 무엇의 날짜인지 알 길이 없다. */
function FactLine({ values }) {
  const shown = values.filter(Boolean);
  if (!shown.length) return null;
  return (
    <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1, minWidth: 0 }}>
      {shown.map((v, i) => (
        <React.Fragment key={v}>
          {i ? <Dot /> : null}
          <Typography
            component="span" color="text.secondary" title={v}
            sx={{ fontSize: FONT_SIZE.bodySm, ...ONE_LINE }}
          >
            {v}
          </Typography>
        </React.Fragment>
      ))}
    </Box>
  );
}

/* 신원 머리 — **전폭 판 하나**. 아바타 · 이름과 역할 · 사실 넷 · 동작 셋이 한 줄이다.
 *
 * 업로드는 기존 네임스페이스 업로드 경로를 그대로 쓴다(서버가 매직바이트로 형식을 판정한다)
 * — 화면은 확장자를 믿지 않고 서버 판정 결과만 받는다. */
function IdentityHeader({ profile, prefs, onChanged }) {
  const auth = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const fileRef = React.useRef(null);
  const [busy, setBusy] = React.useState(false);
  /* 고른 파일은 **바로 올리지 않는다.** 어디를 쓸지 사람이 정한 뒤에 올린다
     (`AvatarCropDialog`) — 예전에는 서버가 가운데를 잘랐고, 세로 사진에서는 그것이
     대개 어깨였다. */
  const [cropping, setCropping] = React.useState(null);
  const name = profile.display_name || (auth.data && auth.data.display_name) || "";
  /* 씨앗은 사용자 id. `/api/profile` 이 id 를 주기 전에는 여기가 비어 이름이 씨앗이 됐고,
     상단바(UUID)와 이 큰 원이 서로 다른 얼굴이었다. 세션의 id 를 폴백으로 둔다. */
  const userId = profile.id || (auth.data && auth.data.id) || "";
  const avatarUrl = (prefs && prefs.avatar && prefs.avatar.url) || profile.avatar_url || null;
  const defaultKey = (prefs && prefs.avatar && prefs.avatar.default_key) || null;
  const person = { user_id: userId, avatar_url: avatarUrl, avatar_default_key: defaultKey };

  async function upload(crop) {
    const file = cropping;
    if (!file) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      // 원본 짧은 변을 1.0 으로 본 비율. 서버가 같은 축으로 읽는다.
      form.append("crop_x", String(crop.crop_x));
      form.append("crop_y", String(crop.crop_y));
      form.append("crop_zoom", String(crop.crop_zoom));
      await api("/api/me/avatar", { method: "POST", body: form });
      toast("프로필 사진을 바꿨습니다.", "success");
      setCropping(null);
      onChanged();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
      // 같은 파일을 다시 고를 수 있게 값을 비운다(안 그러면 change 이벤트가 안 난다).
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function remove() {
    if (!(await confirm("사진을 지우면 기본 아바타로 돌아갑니다.", { title: "프로필 사진 삭제", confirmLabel: "삭제" }))) return;
    setBusy(true);
    try {
      await api("/api/me/avatar", { method: "DELETE" });
      toast("프로필 사진을 지웠습니다.", "success");
      onChanged();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function pickDefault(key) {
    setBusy(true);
    try {
      await api("/api/me/preferences", {
        method: "PATCH", body: { avatar_default_key: key },
      });
      toast(
        avatarUrl
          ? "기본 아바타를 저장했습니다. 지금은 올린 사진이 보이므로, 기본 그림을 보려면 사진을 지우세요."
          : (key ? "기본 아바타를 저장했습니다." : "기본 아바타를 자동으로 되돌렸습니다."),
        "success",
      );
      onChanged();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <Box
        sx={{
          display: "grid",
          /* 좁으면 동작 묶음이 아래 줄로 내려간다 — 셋을 눌러 아바타 옆에 끼우면 버튼
             글자가 두 줄이 된다. 아바타와 글은 어느 폭에서나 같은 줄이다. */
          gridTemplateColumns: { xs: "auto minmax(0, 1fr)", md: "auto minmax(0, 1fr) auto" },
          columnGap: 2.25, rowGap: 2, alignItems: "center",
        }}
      >
        {/* 사진이 없어도 빈 원이 아니다 — 이 사람의 기본 아바타가 선다. 제품 전체가
            같은 부품을 쓰므로 여기서 보는 그림이 채팅과 목록에서 보는 그것이다. */}
        <UserAvatar person={person} name={name} size="xl" userId={userId} />

        <Box sx={{ minWidth: 0, display: "grid", rowGap: 0.75 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap", minWidth: 0 }}>
            {/* 이 판의 제목은 **사람 이름**이다 — 「계정」이라는 이름표가 따로 설 자리가 없다.
                단독 라우트라 `PageHeader` 가 h1 이고 판 제목들이 h2 다(SEM-02). */}
            <Typography
              component="h2"
              sx={{ fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.bold, lineHeight: 1.25, ...KO_WORD_BREAK }}
            >
              {name || "이름 없음"}
            </Typography>
            {/* 역할은 **면을 갖는다.** 면을 쓰는 자리는 목록 밖 — 카드 머리와 상세다(D-476).
                여기가 그 카드 머리이고, 이 배지는 이름 옆에서 「이 사람이 무엇인가」를
                말하는 유일한 표지라 점 하나로는 이름의 무게를 못 받는다. */}
            <Badge
              value={profile.role ? (ROLE_KO[profile.role] || profile.role) : "역할 미상"}
              kind="indigo" emphasis="strong"
            />
          </Box>
          <FactLine values={[profile.department, profile.title, profile.email]} />
          {/* 마지막 로그인만 이름표를 갖는다 — 날짜 하나만 놓으면 무엇의 날짜인지 모른다. */}
          <Typography
            component="span" color="text.secondary"
            sx={{ fontSize: FONT_SIZE.micro, ...ONE_LINE }}
          >
            {`마지막 로그인 ${profile.last_login_at ? fmtDateTime(profile.last_login_at) : "-"}`}
          </Typography>
        </Box>

        {/* 동작 셋은 **무게가 같다.** 사진을 바꾸는 일이 비밀번호를 바꾸는 일보다 중요하지
            않다 — 하나를 채운 버튼으로 세우면 그 하나가 이 판의 목적처럼 보인다. */}
        <Box
          sx={{
            display: "flex", gap: 1, flexWrap: "wrap",
            gridColumn: { xs: "1 / -1", md: "auto" },
            justifyContent: { xs: "flex-start", md: "flex-end" },
          }}
        >
          {/* 파일 입력은 숨기고 버튼으로 연다 — 기본 파일 입력은 브라우저마다 생김새가 달라
              4K에서 혼자 작게 남는다. 라벨은 버튼이 갖는다(스크린리더도 버튼을 읽는다). */}
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            style={{ display: "none" }}
            onChange={(e) => setCropping((e.target.files && e.target.files[0]) || null)}
            aria-hidden="true"
            tabIndex={-1}
          />
          <Button disabled={busy} loading={busy} onClick={() => fileRef.current && fileRef.current.click()}>
            사진 바꾸기
          </Button>
          {/* 사진이 있을 때만 선다 — 지울 것이 없으면 누를 것도 없다. */}
          {avatarUrl ? <Button disabled={busy} onClick={remove}>사진 삭제</Button> : null}
          {/* 기본 아바타 고르기 — **사진과 다른 축이다.** 사진이 있으면 사진이 보이고, 사진을
              지운 뒤에 여기서 고른 그림이 살아난다. 아무것도 안 고르면 사용자 id 로 안정
              배정된 그림이 그대로 쓰인다. 부품이 자기 버튼과 대화상자를 함께 갖는다. */}
          <DefaultAvatarPicker
            seed={userId}
            value={defaultKey}
            busy={busy}
            onPick={pickDefault}
          />
          <Button component="a" href="/change-password">비밀번호 변경</Button>
        </Box>
      </Box>

      {avatarUrl ? (
        <Callout tone="info" compact>
          지금은 올린 사진이 보입니다. 기본 아바타에서 고른 그림은 사진을 지운 뒤에 쓰입니다.
        </Callout>
      ) : null}

      <AvatarCropDialog
        open={!!cropping}
        file={cropping}
        busy={busy}
        onClose={() => { setCropping(null); if (fileRef.current) fileRef.current.value = ""; }}
        onSave={upload}
      />
    </Card>
  );
}

/* PATCH 본문을 GET 모양에 미리 얹는다 — 누른 순간 스위치가 움직이게 하는 낙관적 반영이다(`useInstantSave`, D-525).
 * 서버가 계산하는 값(방해금지의 지금 조용한지 · 그 까닭)은 얹지 않는다 — 응답이 채운다. 끝나는 시각만 어림해서 얹어
 * 「직접 끌 때까지」가 잠깐 비치지 않게 한다(응답의 값이 곧 덮는다). */
function applyPrefsPatch(prefs, body) {
  const next = { ...prefs };
  if ("muted_types" in body) next.notifications = { ...prefs.notifications, muted_types: body.muted_types };
  if ("mail_enabled" in body || "mail_types" in body) {
    next.mail = { ...prefs.mail };
    if ("mail_enabled" in body) next.mail.enabled = body.mail_enabled;
    if ("mail_types" in body) next.mail.types = body.mail_types;
  }
  if ("celebration_enabled" in body) next.celebration = { ...(prefs.celebration || {}), enabled: body.celebration_enabled };
  const dndKeys = ["dnd_enabled", "quiet_hours_enabled", "quiet_start", "quiet_end"];
  if (dndKeys.some((k) => k in body)) {
    next.dnd = { ...prefs.dnd };
    if ("dnd_enabled" in body) {
      next.dnd.enabled = body.dnd_enabled;
      next.dnd.until = body.dnd_enabled && body.dnd_minutes > 0
        ? new Date(Date.now() + body.dnd_minutes * 60_000).toISOString()
        : null;
    }
    if ("quiet_hours_enabled" in body) next.dnd.quiet_hours_enabled = body.quiet_hours_enabled;
    if ("quiet_start" in body) next.dnd.quiet_start = body.quiet_start;
    if ("quiet_end" in body) next.dnd.quiet_end = body.quiet_end;
  }
  return next;
}

/* 알림 설정 — 유형별 뮤트. 목록은 **서버가 준다**(prefs.notifications.catalog).
 * 프런트에 유형 목록을 복사해 두면 서버가 유형을 늘려도 화면에는 영영 안 나온다.
 *
 * 스위치는 저장이 도는 동안에도 켜져 있다 — 저장은 한 줄로 나가고 누른 순간 반영된다(`useInstantSave`). 저장 중이라고
 * 스물여섯 개를 비활성으로 바꾸면 하나를 누를 때마다 목록 전체가 번쩍인다(D-525). */
function NotificationCard({ prefs, save }) {
  const muted = new Set(prefs.notifications.muted_types || []);
  const toggle = (key) => {
    const next = new Set(muted);
    if (next.has(key)) next.delete(key); else next.add(key);
    save({ muted_types: Array.from(next) });
  };
  return (
    <Card sx={CARD_ROWS}>
      <SectionTitle spacing="none"
        component="h2"
        title="알림 배지"
        help="끈 유형도 알림 목록에는 그대로 남습니다. 배지 숫자(빨간 점)에서만 빠집니다. 알림을 없애는 것이 아니라 조용히 하는 것입니다."
      />
      {/* 🔴 **평면 목록**이다 — 묶음 머리를 만들지 않는다.
          유형이 스물이라 「채팅」·「승인」·「시스템」으로 묶고 싶어지는데, 묶는 순간 줄을 찾는
          일이 두 단계가 된다(어느 묶음인지 먼저 정하고 그 안에서 찾는다). 사람이 여기서 하는
          일은 「거슬리는 그것」 하나를 끄는 것이고, 그 이름은 이미 알고 있다.

          🔴 대신 **판 안에서 두 열로 흐른다.** 스무 줄이 한 열로 서면 이 판 혼자 화면
          높이의 두 배가 되고, 옆 레일은 절반에서 끝나 페이지 아래 절반이 통째로 빈다.

          격자가 아니라 **다단(multi-column)** 인 이유: 격자의 자동 배치는 줄 단위라
          `repeat(auto-fit, ...)` 로 두면 1·2번이 첫 줄, 3·4번이 둘째 줄로 **가로로** 채워진다.
          그러면 왼쪽 열을 위에서 아래로 읽는 사람에게 순서가 1, 3, 5… 로 보인다. 다단은
          첫 열을 끝까지 채운 뒤 다음 열로 넘어가므로 목록의 순서가 그대로 보존된다.
          한 줄이 두 열에 걸쳐 쪼개지지 않게 `breakInside` 를 막는다. */}
      <Box
        component="ul"
        sx={{
          listStyle: "none", m: 0, p: 0,
          columnWidth: "20rem", columnGap: GRID_GAP,
        }}
      >
        {prefs.notifications.catalog.map((row) => (
          <Box component="li" key={row.key} sx={{ breakInside: "avoid" }}>
            <SettingRow
              compact label={row.label} description={row.help}
              controlId={`pref-badge-${row.key}`}
              /* MUI 7 의 Switch 는 `inputProps` 를 **조용히 버린다** — 그렇게 쓰면 스위치에
                 접근 가능한 이름이 아예 없어 스크린리더가 이름 없는 컨트롤로 읽는다(테스트에서
                 실제로 잡았다). slotProps.input 이 <input> 에 닿는 유일한 통로다. */
              action={(
                <Switch
                  id={`pref-badge-${row.key}`}
                  checked={!muted.has(row.key)}
                  onChange={() => toggle(row.key)}
                  slotProps={{ input: { "aria-label": `${row.label} 배지 알림` } }}
                />
              )}
            />
          </Box>
        ))}
      </Box>
      <Note sx={{ mt: 0 }}>
        계정 잠금처럼 보안에 관한 알림은 끌 수 없습니다. 침해를 알리는 유일한 신호이기 때문입니다.
      </Note>
    </Card>
  );
}

/* 방해금지 — '지금 조용히'(수동)와 '매일 이 시간대'(조용시간) 두 가지. */
function DndCard({ prefs, save }) {
  const dnd = prefs.dnd;
  const [start, setStart] = React.useState(dnd.quiet_start);
  const [end, setEnd] = React.useState(dnd.quiet_end);
  React.useEffect(() => { setStart(dnd.quiet_start); setEnd(dnd.quiet_end); }, [dnd.quiet_start, dnd.quiet_end]);
  /* 시각 칸은 조용시간을 켰을 때만 쓴다 — 저장 중이라는 이유로 끄지 않는다(저장은 한 줄로 나간다, D-525). */
  const fieldsOff = !dnd.quiet_hours_enabled;

  return (
    <Card sx={CARD_ROWS}>
      <SectionTitle spacing="none"
        component="h2"
        title="방해금지"
        help="방해금지 중에도 알림은 평소대로 쌓입니다. 사이드바 배지만 조용해지고, 비활성화하면 그동안 쌓인 것이 한꺼번에 다시 보입니다."
      />

      {dnd.quiet_now ? (
        <Callout tone="info" compact>
          지금 조용한 상태입니다({dnd.reason === "manual" ? "직접 켬" : "조용시간"}).
          {dnd.until ? ` ${fmtDateTime(dnd.until)}에 자동으로 풀립니다.` : ""}
          {" "}알림은 계속 쌓이고 있습니다.
        </Callout>
      ) : null}

      {/* 두 줄이 `SettingRow` 다 — 알림 설정과 같은 리듬. 스위치의 접근 가능한
          이름(「방해금지」·「조용시간」)은 그대로다. */}
      <Box>
        <SettingRow
          compact
          label="지금 조용히 하기"
          description={dnd.enabled ? (dnd.until ? `${fmtRelative(dnd.until)} 자동 해제` : "직접 끌 때까지") : undefined}
          controlId="pref-dnd-now"
          action={(
            <Switch
              id="pref-dnd-now"
              checked={!!dnd.enabled}
              onChange={(e) => save({ dnd_enabled: e.target.checked, dnd_minutes: e.target.checked ? 60 : 0 })}
              slotProps={{ input: { "aria-label": "방해금지" } }}
            />
          )}
        />
        {/* 켠 뒤에만 선다 — 끄고 있을 때는 고를 시간이 없다. 시안에 이 줄이 없는 이유도
            같다(꺼진 상태를 그린 그림이다). '무한'을 기본으로 두지 않는 것이 이 목록의 요점이라
            켠 순간 얼마나 조용할지 고를 자리가 반드시 있어야 한다. */}
        {dnd.enabled ? (
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", pt: 1.25 }}>
            {DND_PRESETS.map((p) => (
              <Button key={p.label} size="sm"
                onClick={() => save({ dnd_enabled: true, dnd_minutes: p.minutes })}>
                {p.label}
              </Button>
            ))}
          </Box>
        ) : null}

        <SettingRow
          compact
          label="매일 같은 시간대에 조용히 하기"
          description="한국 시간 기준입니다. 자정을 넘겨도 됩니다(예: 22:00 에서 08:00)."
          controlId="pref-dnd-quiet"
          action={(
            <Switch
              id="pref-dnd-quiet"
              checked={!!dnd.quiet_hours_enabled}
              onChange={(e) => save({ quiet_hours_enabled: e.target.checked })}
              slotProps={{ input: { "aria-label": "조용시간" } }}
            />
          )}
        />
        {/* 시각 두 칸과 저장 단추는 한 줄(`FieldRow`)이다 - 단추는 라벨 줄을 비운 같은 트랙의 동작 칸이라 입력칸과 윗선 ·
            높이(34)가 같다(D-527). 칸 폭은 값이 정한다 - 시각 입력은 「오후 10:00」을 오전 · 오후 글자까지 그리므로 7.5rem 에서는
            분 자리가 잘렸다(실측: 「오후 10:0」). 칸과 단추는 왼쪽에 붙고 남는 폭을 나누지 않는다(단추가 판 끝까지 늘지 않는다). */}
        <Box sx={{ pt: 1.5 }}>
          <FieldRow
            columns={["9.5rem", "9.5rem"]}
            action={(
              <Button
                disabled={fieldsOff || (start === dnd.quiet_start && end === dnd.quiet_end)}
                onClick={() => save({ quiet_start: start, quiet_end: end })}
              >
                시간 저장
              </Button>
            )}
          >
            <Field label="시작" htmlFor="dnd-quiet-start">
              <TextField
                id="dnd-quiet-start" type="time" size="small" value={start}
                onChange={(e) => setStart(e.target.value)}
                disabled={fieldsOff}
              />
            </Field>
            <Field label="종료" htmlFor="dnd-quiet-end">
              <TextField
                id="dnd-quiet-end" type="time" size="small" value={end}
                onChange={(e) => setEnd(e.target.value)}
                disabled={fieldsOff}
              />
            </Field>
          </FieldRow>
        </Box>
      </Box>
    </Card>
  );
}

/* 기기 한 줄 — 아이콘 · 이름과 지금 표시 · 주소와 활동 · 브라우저, 그리고 오른쪽에 그 줄로
 * 할 수 있는 일. 어느 줄도 두 줄이 되지 않는다: 길면 말줄임이고 원문은 `title` 이 갖는다. */
function DeviceRow({ session, onRevoke, busy }) {
  const s = session;
  return (
    <Box
      component="li"
      sx={{
        display: "grid", gridTemplateColumns: "auto minmax(0, 1fr) auto", columnGap: 1.5,
        alignItems: "center", px: 1.75, py: 1.5,
        border: 1, borderColor: "divider", borderRadius: `${RADIUS.sm}px`,
      }}
    >
      <DevicesOtherRoundedIcon fontSize="small" aria-hidden="true" color={s.current ? "primary" : "disabled"} />
      <Box sx={{ minWidth: 0, display: "grid", rowGap: 0.25 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold, ...ONE_LINE }}>
            {s.current ? "지금 이 창" : "다른 기기"}
          </Typography>
          {/* 「현재」는 **점 + 낱말**이다. 목록 안이라 면을 갖지 않는다 — 한 줄에서 어휘가
              갈리면 읽는 사람은 그 둘이 다른 종류의 사실이라고 읽는다. */}
          {s.current ? <Badge value="현재" kind="ok" /> : null}
        </Box>
        <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro, ...ONE_LINE }}>
          {`${s.client_ip || "IP 미상"}, 최근 활동 ${fmtRelative(s.last_seen_at)}`}
        </Typography>
        {s.user_agent ? (
          // Users.jsx(관리자의 다른 사용자 세션 목록)와 같은 이유로 원문 대신 60자로
          // 자른 표기 + Tooltip으로 전체 문구를 보존한다 — 원문 그대로 두면 긴 UA
          // 문자열이 이 카드의 폭을 밀어냈다.
          <Tooltip title={s.user_agent}>
            <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro, ...ONE_LINE }}>
              {shortUA(s.user_agent)}
            </Typography>
          </Tooltip>
        ) : null}
      </Box>
      {s.current ? (
        <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro, whiteSpace: "nowrap" }}>
          유지됩니다
        </Typography>
      ) : (
        <Button size="sm" disabled={busy} onClick={() => onRevoke(s.id)}>이 기기 로그아웃</Button>
      )}
    </Box>
  );
}

/* 내 기기 — 살아 있는 세션 목록 + 다른 기기 로그아웃. */
/* 축하 효과(D-563) — 게임 당첨자 발표와 티켓 완료의 축포는 하나이므로 스위치도 하나다. 끄면 축포만 빠지고 결과 · 완료는 그대로다.
 * OS 의 동작 줄이기 신호는 제품 결정(2026-09-03)대로 보지 않는다 — 끄는 자리는 이 스위치뿐이다. */
function CelebrationCard({ prefs, save }) {
  const on = !prefs.celebration || prefs.celebration.enabled !== false;
  return (
    <Card sx={CARD_ROWS}>
      <SectionTitle spacing="none"
        component="h2"
        title="화면 효과"
        help="축하 효과는 게임 당첨자 발표와 티켓 완료에 터지는 축포입니다. 꺼도 결과와 완료는 그대로 보입니다."
      />
      <Box>
        <SettingRow
          compact
          label="축하 효과"
          description={on ? "당첨자 발표와 티켓 완료에 축포가 터집니다." : "축포가 터지지 않습니다."}
          controlId="pref-celebration"
          action={(
            <Switch
              id="pref-celebration"
              checked={on}
              onChange={(e) => save({ celebration_enabled: e.target.checked })}
              slotProps={{ input: { "aria-label": "축하 효과" } }}
            />
          )}
        />
      </Box>
    </Card>
  );
}

function SessionsCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const q = useQuery({ queryKey: ["my-sessions"], queryFn: () => api("/api/me/sessions"), retry: false });
  const items = (q.data && q.data.items) || [];
  const others = items.filter((s) => !s.current);

  const revokeOthers = useMutation({
    mutationFn: () => api("/api/me/sessions/revoke-others", { method: "POST", body: {} }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["my-sessions"] });
      toast(`${res.revoked_count}개 기기의 로그인을 해제했습니다.`, "success");
    },
    onError: (e) => toast(e.message, "error"),
  });
  const revokeOne = useMutation({
    mutationFn: (id) => api("/api/me/sessions/" + id, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-sessions"] });
      toast("해당 기기의 로그인을 해제했습니다.", "success");
    },
    onError: (e) => toast(e.message, "error"),
  });

  async function askRevokeOthers() {
    const ok = await confirm(
      `지금 보고 있는 이 창은 그대로 두고 나머지 ${others.length}개의 로그인을 끊습니다.
끊긴 기기는 즉시 다시 로그인해야 합니다.`,
      { title: "다른 기기 모두 로그아웃", confirmLabel: "모두 로그아웃", danger: true },
    );
    if (ok) revokeOthers.mutate();
  }

  return (
    <Card sx={CARD_ROWS}>
      {/* 🔴 「다른 기기 모두 로그아웃」이 판 머리로 올라왔다. 예전에는 목록 아래 실선 밑에
          있어서, 세션이 많으면 그 단추가 화면 밖에 있었다 — 이 판이 존재하는 이유가 그
          단추인데 그것을 보려고 스크롤해야 했다. 끊을 대상이 없으면 비활성이고, 몇 개를
          끊는지는 라벨이 말한다. 되돌릴 수 없는 보안 동작이라 확인 단계는 그대로다. */}
      <SectionTitle spacing="none"
        component="h2"
        /* 단추는 **머리 오른쪽에 붙박이다.** 기본값(`wrap`)이면 설명문이 길어 첫 줄을 다 먹고
           단추가 아래 줄 왼쪽으로 떨어진다 — 그 자리에서는 판 제목의 동작이 아니라 목록의
           첫 항목처럼 보인다. 줄을 안 접고 글 칸을 줄인다(글은 안에서 접힌다). */

        title="내 기기"
        /* 「지금 보고 있는 이 창은 유지됩니다」가 여기 붙어 있었다. 그 사실은 이제 목록에서
           이 창의 줄이 오른쪽에 「유지됩니다」로 직접 말하고, 확인 대화상자가 한 번 더
           말한다 — 같은 사실을 세 곳에서 말하느라 설명이 두 줄로 감겼다. */
        help="공용 PC에 로그인해 둔 채로 왔거나, 모르는 기기가 보이면 여기서 끊으세요."
        action={(
          <Button
            variant="danger" size="sm"
            /* 라벨은 한 줄이다 — 접히면 30px 단추가 두 줄이 되어 머리 줄의 높이를 혼자
               정한다. 좁아지는 것은 옆의 설명문이고, 그쪽은 접혀도 읽힌다. */
            sx={{ whiteSpace: "nowrap" }}
            disabled={others.length === 0 || revokeOthers.isPending}
            loading={revokeOthers.isPending}
            onClick={askRevokeOthers}
          >
            {`다른 기기 모두 로그아웃${others.length ? ` (${others.length})` : ""}`}
          </Button>
        )}
      />
      {q.isLoading ? <Skeleton lines={3} /> : q.isError ? (
        <ErrorState layout="region" error={q.error} onRetry={() => q.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title="표시할 세션이 없습니다" />
      ) : (
        <>
          {/* 총계를 먼저 말한다 — 아래 목록은 높이가 묶여 있어 일부만 보인다. 숫자를 안 쓰면
              "몇 개인지"를 스크롤해서 세어야 하고, 잘린 마지막 줄이 오류처럼 보인다. */}
          <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro }}>
            총 {items.length}개, 다른 기기 {others.length}개{items.length > 6 ? " (목록은 스크롤됩니다)" : ""}
          </Typography>
          {/* 목록 높이를 묶고 안에서 스크롤한다 — 오래 쓴 계정은 세션이 수십 개까지 쌓여
              카드 하나가 화면 스무 개 길이가 된다(QA 캡처에서 실제로 22개였다). */}
          <Box
            component="ul"
            sx={{
              listStyle: "none", m: 0, p: 0, display: "grid", gap: 1,
              maxHeight: { md: "22rem" }, overflowY: { md: "auto" },
            }}
          >
            {items.map((s) => (
              <DeviceRow key={s.id} session={s} busy={revokeOne.isPending} onRevoke={(id) => revokeOne.mutate(id)} />
            ))}
          </Box>
          {others.length === 0 ? (
            <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.micro }}>
              지금은 이 창에서만 로그인되어 있습니다.
            </Typography>
          ) : null}
        </>
      )}
    </Card>
  );
}

/* 둘러보기 — **판 하나에 한 줄**이다. 처음 들어왔을 때 나오는 안내를 다시 볼 자리. */
function TourCard({ tour, onReset, busy }) {
  return (
    <Card>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Box sx={{ minWidth: 0, display: "grid", rowGap: 0.375, flex: "1 1 12rem" }}>
          <Typography component="h2" sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold, ...KO_WORD_BREAK }}>
            둘러보기
          </Typography>
          <Typography color="text.secondary" sx={{ fontSize: FONT_SIZE.caption, ...KO_WORD_BREAK }}>
            {tour.show
              ? "처음 들어왔을 때 나오는 안내입니다. 아직 보지 않았고, 홈으로 가면 자동으로 시작됩니다."
              : tour.skipped
                ? "처음 들어왔을 때 나오는 안내입니다. 건너뛰었습니다."
                : "처음 들어왔을 때 나오는 안내입니다. 완료했습니다."}
          </Typography>
        </Box>
        <Button size="sm" disabled={tour.show || busy} onClick={onReset}>
          둘러보기 다시 보기
        </Button>
      </Box>
    </Card>
  );
}

export function Profile() {
  const qc = useQueryClient();
  const toast = useToast();
  const profileQuery = useQuery({ queryKey: ["profile"], queryFn: () => api("/api/profile"), retry: false });
  const prefsQuery = useQuery({ queryKey: ["me-preferences"], queryFn: () => api("/api/me/preferences"), retry: false });

  /* 알림 · 메일 · 방해금지는 누르는 즉시 저장되는 설정이다 — 누른 순간 반영하고 요청은 한 줄로 보낸다(D-525).
     응답은 설정 전체라 줄의 마지막 응답으로 캐시를 쓴다. */
  const savePrefs = useInstantSave({
    queryKey: ["me-preferences"],
    mutationFn: (body) => api("/api/me/preferences", { method: "PATCH", body }),
    apply: applyPrefsPatch,
    fromResponse: (data) => data,
    onSaved: () => {
      // 배지가 즉시 조용해지거나 다시 켜지도록 벨 폴링도 함께 무효화한다.
      invalidateNotifications(qc);
      toast("설정을 저장했습니다.", "success");
    },
    onError: (e) => toast(e.message, "error"),
  });

  const resetTour = useMutation({
    mutationFn: () => api("/api/me/tour", { method: "POST", body: { action: "reset" } }),
    onSuccess: (data) => {
      qc.setQueryData(["me-preferences"], data);
      toast("둘러보기를 다시 볼 수 있습니다. 홈으로 가면 시작됩니다.", "success");
    },
    onError: (e) => toast(e.message, "error"),
  });

  const loading = profileQuery.isLoading || prefsQuery.isLoading;
  const error = profileQuery.error || prefsQuery.error;

  return (
    <div className="c-screen">
      <PageHeader area="내 정보" title="내 프로필" crumbRoot="" />
      {loading ? (
        <Card><Skeleton lines={8} /></Card>
      ) : error ? (
        <ErrorState layout="region" error={error} onRetry={() => { profileQuery.refetch(); prefsQuery.refetch(); }} />
      ) : (
        <Box sx={{ display: "grid", gap: GRID_GAP }}>
          {/* 신원 머리는 **전폭**이다. 「내가 누구인가」는 두 열 중 한 열에 들어갈 사실이
              아니라 이 화면 전체의 머리다 — 아래 판들은 전부 그 사람의 설정이다. */}
          <IdentityHeader
            profile={profileQuery.data}
            prefs={prefsQuery.data}
            onChanged={() => {
              prefsQuery.refetch();
              profileQuery.refetch();
              // 상단바는 /api/me, 티켓·보드·채팅은 각자 캐시에 얼굴을 들고 있다.
              invalidatePersonFaces(qc);
            }}
          />
          <Box sx={TWO_COL_EVEN}>
            {/* 왼쪽은 판 둘이다 — 「메일 알림」(내가 어떤 메일을 어디에서 받는가)이 먼저, 「알림 배지」가 다음이다(D-550).
                관리자의 메일 설정과 나뉜 카드이고, 메일 서버의 말과 값이 없다. */}
            <Box sx={{ display: "grid", gap: GRID_GAP, alignContent: "start", minWidth: 0 }}>
              <MailNotificationCard mail={prefsQuery.data.mail} save={savePrefs.mutate} />
              <NotificationCard prefs={prefsQuery.data} save={savePrefs.mutate} />
            </Box>
            {/* 오른쪽은 **내 기기 → 방해금지 → 강조색 → 둘러보기**다. 앞의 둘은 계정과
                알림에 관한 것이고 뒤의 둘은 이 브라우저의 취향과 안내다 — 급한 것이 위다. */}
            <Box sx={{ display: "grid", gap: GRID_GAP, alignContent: "start", minWidth: 0 }}>
              <SessionsCard />
              <DndCard prefs={prefsQuery.data} save={savePrefs.mutate} />
              <CelebrationCard prefs={prefsQuery.data} save={savePrefs.mutate} />
              <AccentPicker />
              <TourCard
                tour={prefsQuery.data.tour}
                busy={resetTour.isPending}
                onReset={() => resetTour.mutate()}
              />
            </Box>
          </Box>
        </Box>
      )}
    </div>
  );
}

export default Profile;
