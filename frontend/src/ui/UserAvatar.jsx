import React from "react";
import Box from "@mui/material/Box";

import { DefaultAvatar } from "./DefaultAvatar.jsx";

/* 사용자 아바타 — **제품 전체에서 한 부품이다** (지시: Avatar 시스템).
 *
 * ## 무엇이 문제였나
 *
 * 사진을 그리는 자리가 넷이었고(게시판 작성자 줄 · 채팅 보낸 사람 · 상단바 · 내 프로필)
 * 넷이 각자 `<img>` 를 적고 있었다. 크기도 규칙도 조금씩 달랐고, 무엇보다 셋이 같은
 * 규칙을 갖고 있었다: **사진이 없으면 아무것도 안 그린다.**
 *
 * 그 규칙이 이 회차에 바뀐다. 이제 사진이 없는 사람도 그림을 갖는다 — 사용자 id 를
 * 씨앗으로 안정적으로 배정한 기본 아바타다(`DefaultAvatar`). 그래서 목록에서 사람을
 * 찾는 일이 이름을 읽는 일이 아니라 **알아보는 일**이 된다.
 *
 * ## 크기는 쓰임이 정한다
 *
 * 픽셀을 호출부가 적지 않는다. 자리마다 숫자를 적으면 같은 성격의 두 화면이 다른 크기로
 * 그리고, 4K 에서는 그 숫자만 안 자란다. 크기는 이름이고 값은 `rem` 이다.
 */
export const AVATAR_SIZE = {
  /** 표의 사람 칸과 검색 팝오버의 항목 — 32px 줄 안에 이름과 나란히 서는 크기(핸드오프 README
   *  §5 · §6: 「표 안의 사람은 아바타 22 + 이름」, 「32px 항목(아바타 22 + 이름 + 부서)」). */
  xs: "1.375rem",
  /** 목록 줄·댓글·채팅 — 글줄 옆에 붙는 크기. */
  inline: "1.25rem",
  /** 카드·표의 담당자 칸. */
  sm: "1.5rem",
  /** 상단바·회의 화면의 담당자 줄. */
  md: "1.875rem",
  /** 상세 화면의 사람 블록. */
  lg: "2.5rem",
  /** 내 프로필 신원 머리의 현재 사진.
   *
   * 96px 였다. 그때는 이 그림이 자기 판 하나를 통째로 쓰는 「사진 판」의 주인공이었다.
   * 지금은 이름·소속·마지막 로그인과 한 줄에 서는 신원 머리의 첫 칸이고, 96px 은 그
   * 글 덩어리보다 커서 사람이 아니라 사진이 주인공으로 읽힌다. 72px 은 글 세 줄과
   * 키가 맞는다. */
  xl: "4.5rem",
};

/** `person` 은 서버가 주는 identity dict 다(`app/core/people.py::identity`). */
export function UserAvatar({ person, userId, name, size = "inline", label, sx }) {
  const p = person || {};
  /* 씨앗은 **사용자 id** 다. 이름이 들어가면 같은 사람이 화면마다 다른 얼굴을 갖는다 —
     프로필 API 에 id 가 없던 동안 큰 원이 표시 이름으로, 상단바는 UUID 로 그려진 것이
     그 결함이다. id 를 아직 모르는 자리는 빈 씨앗의 색 원이 선다(지어내지 않는다). */
  const seed = p.user_id || p.id || userId || "";
  const url = p.avatar_url || null;
  const box = AVATAR_SIZE[size] || size;

  /* 이름이 바로 옆에 있으면 그림은 장식이다 — 스크린리더가 같은 사람을 두 번 읽지 않게
     `alt=""` 로 둔다. 이름 없이 혼자 서는 자리(보드 카드의 담당자)는 `label` 을 받는다. */
  const alt = label || "";

  return (
    <Box
      className="k-avatar"
      sx={{
        width: box, height: box, flexShrink: 0,
        borderRadius: "50%", overflow: "hidden",
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        /* 밝은 사진과 밝은 바탕이 만나면 원의 경계가 사라진다 — 아주 얇은 테두리 하나로
           어느 테마에서나 원이 원으로 보인다. */
        boxShadow: (t) => `inset 0 0 0 1px ${t.palette.divider}`,
        ...sx,
      }}
    >
      {url ? (
        <Box
          component="img"
          src={url}
          alt={alt}
          loading="lazy"
          decoding="async"
          sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
        />
      ) : (
        <DefaultAvatar seed={seed} avatarKey={p.avatar_default_key} title={label || undefined} />
      )}
    </Box>
  );
}

/** 아바타 + 이름 한 줄. 사람을 이름으로만 부르던 자리를 이것으로 바꾼다. */
/** 사람 줄(`PersonLine`)에서 이름 앞에 서는 폭(rem) — 아바타 + 사이 0.3125rem. 표의 이름 열이 `lead` 로 적어 값 폭에 더한다
 *  (`columnPlan.columnSpec`). */
export function personLineLead(size = "inline") {
  const box = parseFloat(AVATAR_SIZE[size] || size);
  return (Number.isFinite(box) ? box : 1.25) + 0.3125;
}

export function PersonLine({ person, name, size = "inline", bold, suffix, sx }) {
  return (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.625, minWidth: 0, maxWidth: "100%", lineHeight: 1.25, ...sx }}>
      <UserAvatar person={person} name={name} size={size} />
      <Box
        component="span"
        sx={{ fontWeight: bold ? 700 : "inherit", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
      >
        {name || "알 수 없음"}
      </Box>
      {suffix}
    </Box>
  );
}
