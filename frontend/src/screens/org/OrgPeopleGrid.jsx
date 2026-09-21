import React from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { ErrorState, Section, Skeleton } from "../../ui/kit.jsx";
import { PersonLine } from "../../ui/UserAvatar.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";

/* 사람 절 — 부서 판의 「구성원 N명」과 조직 판의 「부서 미지정 N명」이 같이 쓴다.
 *
 * ## 수는 절 제목에 한 번만 선다
 *
 * 예전 부서 판은 같은 인원을 세 번 말했다: 요약 타일 「소속 인원」, 절 제목 「소속 인원 N명」,
 * 트리 줄 「소속 N명」. 셋 중 둘은 보관된 계정을 세고 하나는 안 세서 서로 어긋나기까지 했다.
 * 지금은 이 절 제목이 그 인원의 유일한 자리이고, 세는 법은 **아래 목록과 같다**(보관된 계정은
 * 빠진다). 서버 기록의 인원(`recorded` — 보관 계정 포함)이 더 크면 그 차이를 목록 아래 한 줄이
 * 말한다. 가지 전체의 인원은 트리 줄이 말한다.
 *
 * ## 목록을 다시 만들지 않는다
 *
 * 여기 보이는 것은 여덟까지다. 더 있으면 그 조건이 걸린 사용자 화면으로 보낸다 — 같은 목록을
 * 두 화면이 각자 그리면 언젠가 다른 답을 한다.
 *
 * ## 한 줄이 아니라 격자다
 *
 * 옛 목록은 한 줄에 한 사람이었고 줄이 판 폭(1920 에서 1,200px)만큼 늘어나 이름과 직급 배지가
 * 양 끝으로 갈라졌다. 지금은 `16rem` 칸의 격자라 넓은 판에서는 여러 사람이 한 줄에 서고, 직급은
 * 배지가 아니라 이름 바로 뒤의 흐린 글자다 — 상태가 아니라 그 사람의 속성이기 때문이다. */

export const PEOPLE_PREVIEW = 8;

const PEOPLE_GRID_SX = {
  listStyle: "none", m: 0, p: 0,
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(min(16rem, 100%), 1fr))",
  columnGap: 3, rowGap: 1,
  fontSize: FONT_SIZE.bodySm,
};

function PersonCell({ person }) {
  const name = person.display_name || person.email || "";
  return (
    <Box component="li" sx={{ minWidth: 0 }}>
      <PersonLine
        person={person}
        size="sm"
        name={<Link href={"#/users/" + person.id} underline="hover">{name}</Link>}
        suffix={person.title ? (
          <Box component="span" sx={{ color: "text.secondary", flexShrink: 0, whiteSpace: "nowrap" }}>
            {person.title}
          </Box>
        ) : null}
      />
    </Box>
  );
}

/**
 * label     절 이름(「구성원」 · 「부서 미지정」). 수는 이 부품이 뒤에 붙인다.
 * count     제목의 수를 부르는 쪽이 이미 알 때 준다(부서 미지정 — 트리가 센 값). 없으면 목록의 전체 수다.
 * query     사람 목록 질의(`useDepartmentPeople` · `useUnassignedPeople`). 없으면 목록 대신 `note` 가 선다.
 * recorded  서버 기록의 인원(보관 계정 포함). 목록 전체 수보다 크면 그 차이를 한 줄로 말한다.
 * listHref  같은 조건이 걸린 사용자 화면 주소 — 절 머리의 링크와 「모두 보기」가 함께 쓴다.
 */
export function OrgPeopleSection({ label, count, query, recorded, listHref, emptyText, note }) {
  const loaded = Boolean(query && query.isSuccess);
  const items = (loaded && query.data && query.data.items) || [];
  const total = loaded
    ? (query.data && query.data.total != null ? query.data.total : items.length)
    : null;
  const shown = count != null ? count : total;
  const archived = loaded && recorded != null && recorded > total ? recorded - total : 0;

  return (
    <Section
      title={shown != null ? `${label} ${shown}명` : label}
      /* 판 머리 동작 자리라 글자 단추가 아니라 링크다(`check_composition.py` 의 `ghost-slot`). */
      action={<Link href={listHref} underline="hover" sx={{ fontSize: FONT_SIZE.bodySm }}>사용자 화면에서 보기</Link>}
      sx={{ mb: 0 }}
    >
      {!query ? note : null}
      {query && query.isPending ? <Skeleton lines={2} /> : null}
      {query && query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} layout="region" size="compact" />
      ) : null}
      {loaded && items.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{emptyText}</Typography>
      ) : null}
      {items.length ? (
        <Box component="ul" sx={PEOPLE_GRID_SX}>
          {items.slice(0, PEOPLE_PREVIEW).map((u) => <PersonCell key={u.id} person={u} />)}
        </Box>
      ) : null}
      {loaded && total > PEOPLE_PREVIEW ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5, ...KO_WORD_BREAK }}>
          {PEOPLE_PREVIEW}명만 표시했습니다.{" "}
          <Link href={listHref} underline="hover">사용자 화면에서 {total}명 모두 보기</Link>
        </Typography>
      ) : null}
      {archived ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1, ...KO_WORD_BREAK }}>
          {`보관된 계정 ${archived}명은 이 목록에 없습니다.`}
        </Typography>
      ) : null}
    </Section>
  );
}
