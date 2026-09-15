import React from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import StarRoundedIcon from "@mui/icons-material/StarRounded";
import StarOutlineRoundedIcon from "@mui/icons-material/StarOutlineRounded";
import { DotLabel, OverflowMenu, Tag } from "../../ui/kit.jsx";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { fmtDateTimeCompact, objectParticle } from "../../lib/format.js";
import { PROJECT_UNASSIGNED_LABEL } from "./constants.js";

/* 제목 칸에 세우는 태그 수 — 넘치면 「+N」 태그 하나로 남은 수를 말한다(핸드오프 README §B · ACCEPTANCE J2).
   태그가 많은 문서도 줄이 태그 때문에 여러 줄로 불어나지 않는다. 전체 태그는 문서를 열면 다 보인다. */
const TAG_LIMIT = 4;

/* 문서 목록의 열 — 열이 이름을 갖는다.
 *
 * ## 좁은 칸에서 무엇이 접히는가 (P-59 · D-380)
 *
 * 제목 열은 `type:"title"` 이라 **남는 폭**을 받는다. 옛 3칸 배치에서는 목록 칸이 582px
 * 까지 좁아져 고정폭 열의 합(712px)이 남는 폭을 0 으로 만들었다 — 문서 이름이 한 글자도
 * 안 보였다. 지금은 배치가 넓어졌고, 그래도 칸이 좁아지면 `hideNarrow` 열이 **뒤에서부터**
 * 접힌다(counts → 최종 수정 → 작성자 → 분류 → 폴더). 접힌 열은 표가 한 줄로 알린다
 * (`HiddenColumnsNote`). 별·제목·프로젝트는 이 목록의 뼈대라 접지 않는다. */
/* ## 열 트랙 (핸드오프 계획 D · ACCEPTANCE J2)
 *
 * 별 48 · 제목 남는 폭(바닥 320) · 프로젝트 176 · 분류 148 · 작성자 130 · 최종 수정 132 · 첨부와 댓글 96 · 작업 64.
 * 행은 제목 · 요약 · 태그 세 줄이 서는 두 줄 행이라 바닥 76 이다(`DataTable rowHeight="tall"`). 폭이 모자라면
 * 접히는 열의 순서와 안내 한 줄은 그대로다. */
export function buildDocumentColumns({ onToggleFavorite, onOpen, onArchive, confirm }) {
  return [
    {
      key: "star", label: "별", type: "select", width: "3rem",
      render: (doc) => (
        <Box
          component="button"
          type="button"
          aria-label={doc.is_favorite ? `${doc.title} 즐겨찾기 해제` : `${doc.title} 즐겨찾기`}
          aria-pressed={Boolean(doc.is_favorite)}
          onClick={(e) => {
            e.stopPropagation();
            onToggleFavorite(doc);
          }}
          sx={{
            background: "none", border: "none", cursor: "pointer", p: 0, lineHeight: 0,
            color: doc.is_favorite ? "warning.main" : "text.disabled",
          }}
        >
          {doc.is_favorite
            ? <StarRoundedIcon sx={{ fontSize: "1.125rem" }} />
            : <StarOutlineRoundedIcon sx={{ fontSize: "1.125rem" }} />}
        </Box>
      ),
    },
    {
      key: "title", label: "제목", type: "title", minWidth: "20rem", rowName: (d) => d.title,
      render: (doc) => {
        const tags = doc.tags || [];
        return (
          <Box sx={{ display: "grid", gap: 0.5, minWidth: 0, py: 0.5 }}>
            <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}>
              {doc.title}
            </Typography>
            {/* 요약은 두 줄에서 자른다 — 긴 요약이 줄 높이를 불리지 않는다. 전문은 문서를 열면 있다. */}
            {doc.excerpt ? (
              <Typography
                data-doc-excerpt=""
                color="text.secondary"
                sx={{
                  fontSize: FONT_SIZE.caption, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                  overflow: "hidden", ...KO_WORD_BREAK,
                }}
              >
                {doc.excerpt}
              </Typography>
            ) : null}
            {/* 제목 칸의 칩은 태그만이다(§11.3) — 분류는 분류 열의 점 + 낱말이다. */}
            {tags.length > 0 ? (
              <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", rowGap: 0.5 }}>
                {tags.slice(0, TAG_LIMIT).map((t) => <Tag key={t.id} label={t.name} />)}
                {tags.length > TAG_LIMIT ? (
                  <Tag label={`+${tags.length - TAG_LIMIT}`} title={tags.slice(TAG_LIMIT).map((t) => t.name).join(", ")} />
                ) : null}
              </Stack>
            ) : null}
          </Box>
        );
      },
    },
    /* 🔴 한 칸에 프로젝트·폴더·분류 셋이 겹쳐 쌓여 있었고 열 이름은 「프로젝트」 하나였다.
       화면에는 「SK하이닉스 [용인 클러스터]」 아래에 「회의록」이 붙어 서는데, 그 「회의록」이
       폴더인지 분류인지 열 이름이 말해 주지 않았다 — 라벨이 내용에 대해 거짓말을 하는 자리다.
       셋은 뜻이 다르므로 열도 셋이다: 어디에 속하는가(프로젝트) · 어디에 정리했는가(폴더) ·
       무슨 종류인가(분류). 뒤 둘은 칸이 좁아지면 접힌다(`hideNarrow`) — 접힌 사실은 표가
       한 줄로 알린다. */
    {
      key: "place", label: "프로젝트", type: "name", width: "11rem",
      render: (doc) => (
        <Typography variant="body2" sx={KO_WORD_BREAK}>
          {doc.project ? doc.project.name : PROJECT_UNASSIGNED_LABEL}
        </Typography>
      ),
    },
    /* 🔴 「폴더」 열이 여기 있었다. 폴더 축이 화면에서 걷히면서(문서 개편 1·5번) 값을
       넣거나 뺄 자리가 없어졌고, 남겨 두면 모든 줄이 「정리 안 함」인 열이 된다.
       서버 응답의 `folder_path` 는 그대로 온다 — 걷은 것은 그리는 자리뿐이다. */
    {
      /* 분류는 칩이 아니라 **점 + 낱말**이다(§11.3 · 핸드오프 계획 P-22) — 태그와 섞이면 "이 문서가 다루는 기술"과
         "이 문서의 종류"가 같은 모양으로 보인다. 점은 중립이고 면이 없다. 정본은 분류(0026)이고, 분류가
         없는 이관 문서만 옛 doc_type 이 그대로 보인다. 둘 다 없으면 점 없이 「-」다. */
      key: "category", label: "분류", type: "name", width: "9.25rem", hideNarrow: true,
      render: (doc) => {
        const name = doc.category?.name || doc.doc_type;
        return name ? <DotLabel label={name} /> : (
          <Typography variant="body2" color="text.secondary">-</Typography>
        );
      },
    },
    {
      /* 🔴 작성자는 **세 가지 사실**이다. 우리 사용자가 썼거나, 원본에 이름만 적혀
         있거나, 모른다. 예전에는 가운데가 없어서 가져오기를 돌린 관리자가 작성자로
         섰고 — 화면이 「이 사람이 524건을 썼다」고 거짓말했다. Confluence 는 작성자의
         이메일을 안 주므로(실측: 8명 중 1명, 그마저 우리 계정에 없다) 우리 계정으로
         이을 수 없다. 이름만 남기고, 그것이 우리 사용자가 아니라는 것도 함께 보인다. */
      key: "author", label: "작성자", type: "name", width: "8.125rem", hideNarrow: true,
      render: (doc) => (
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
          {/* 표 사람 칸의 얼굴은 22(`xs`)다 — 핸드오프 README §6. */}
          {doc.author ? <UserAvatar person={doc.author} size="xs" /> : null}
          <Typography variant="body2" sx={KO_WORD_BREAK}>
            {doc.author?.display_name || doc.legacy_author_name || "-"}
          </Typography>
        </Stack>
      ),
    },
    {
      key: "updated_at", label: "최종 수정", type: "datetime", width: "8.25rem", hideNarrow: true,
      render: (doc) => fmtDateTimeCompact(doc.updated_at),
    },
    {
      /* 첨부와 댓글이 있다는 사실은 **문서를 고르는 근거**다. 열어 봐야 아는 값이면
         목록에서 못 고른다. 0 은 안 그린다 — 대부분이 0 이라 그리면 소음이다.
         셋 중 **가장 먼저 접히는** 열이다 (D-380). */
      key: "counts", label: "첨부, 댓글", type: "enum", width: "6rem", hideNarrow: true,
      render: (doc) => {
        const c = doc.counts || {};
        const parts = [];
        if (c.attachments) parts.push(`첨부 ${c.attachments}`);
        if (c.comments) parts.push(`댓글 ${c.comments}`);
        if (c.relations) parts.push(`관련 ${c.relations}`);
        return parts.length ? (
          <Typography variant="caption" color="text.secondary">{parts.join(", ")}</Typography>
        ) : "";
      },
    },
    {
      key: "more", label: "작업", type: "actions", width: "4rem",
      render: (doc) => (
        /* 행 동작은 작은 단추(30)다 — 두 줄 행 안에서 34 는 칸보다 크게 선다(핸드오프 J2 「작업 30」). */
        <OverflowMenu
          size="sm"
          ariaLabel={`${doc.title} 작업`}
          items={[
            { label: "문서 열기", onClick: () => onOpen(doc) },
            {
              label: "휴지통으로 보내기",
              onClick: async () => {
                const ok = await confirm(
                  "휴지통에서 되살릴 수 있습니다. 판 이력과 댓글은 그대로 남습니다.",
                  { title: `${doc.title}${objectParticle(doc.title)} 휴지통으로 보낼까요?`, confirmLabel: "보내기" },
                );
                if (ok) onArchive(doc);
              },
            },
          ]}
        />
      ),
    },
  ];
}
