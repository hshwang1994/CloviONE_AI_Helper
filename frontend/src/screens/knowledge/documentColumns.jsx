import React from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import StarRoundedIcon from "@mui/icons-material/StarRounded";
import StarOutlineRoundedIcon from "@mui/icons-material/StarOutlineRounded";
import { OverflowMenu } from "../../ui/kit.jsx";
import { UserAvatar } from "../../ui/UserAvatar.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { fmtDateTimeCompact } from "../../lib/format.js";
import { PROJECT_UNASSIGNED_LABEL } from "./constants.js";

/* 문서 목록의 열 — 열이 이름을 갖는다.
 *
 * ## 좁은 칸에서 무엇이 접히는가 (P-59 · D-380)
 *
 * 제목 열은 `type:"title"` 이라 **남는 폭**을 받는다. 옛 3칸 배치에서는 목록 칸이 582px
 * 까지 좁아져 고정폭 열의 합(712px)이 남는 폭을 0 으로 만들었다 — 문서 이름이 한 글자도
 * 안 보였다. 지금은 배치가 넓어졌고, 그래도 칸이 좁아지면 `hideNarrow` 열이 **뒤에서부터**
 * 접힌다(counts → 최종 수정 → 작성자 → 분류 → 폴더). 접힌 열은 표가 한 줄로 알린다
 * (`HiddenColumnsNote`). 별·제목·프로젝트는 이 목록의 뼈대라 접지 않는다. */
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
      key: "title", label: "제목", type: "title", minWidth: "16rem", rowName: (d) => d.title,
      render: (doc) => (
        <Box sx={{ display: "grid", gap: 0.25, minWidth: 0 }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}>
            {doc.title}
          </Typography>
          {doc.excerpt ? (
            <Typography variant="caption" color="text.secondary" sx={KO_WORD_BREAK}>
              {doc.excerpt}
            </Typography>
          ) : null}
          {/* 제목 칸의 칩은 태그만이다(§11.3) — 분류는 프로젝트 열의 보조 글자다. */}
          {(doc.tags || []).length > 0 ? (
            <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", rowGap: 0.5, mt: 0.25 }}>
              {(doc.tags || []).map((t) => <Chip key={t.id} size="small" label={t.name} />)}
            </Stack>
          ) : null}
        </Box>
      ),
    },
    /* 🔴 한 칸에 프로젝트·폴더·분류 셋이 겹쳐 쌓여 있었고 열 이름은 「프로젝트」 하나였다.
       화면에는 「SK하이닉스 [용인 클러스터]」 아래에 「회의록」이 붙어 서는데, 그 「회의록」이
       폴더인지 분류인지 열 이름이 말해 주지 않았다 — 라벨이 내용에 대해 거짓말을 하는 자리다.
       셋은 뜻이 다르므로 열도 셋이다: 어디에 속하는가(프로젝트) · 어디에 정리했는가(폴더) ·
       무슨 종류인가(분류). 뒤 둘은 칸이 좁아지면 접힌다(`hideNarrow`) — 접힌 사실은 표가
       한 줄로 알린다. */
    {
      key: "place", label: "프로젝트", type: "name", minWidth: "10rem",
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
      /* 분류는 칩이 아니라 글자다(§11.3) — 태그와 섞이면 "이 문서가 다루는 기술"과
         "이 문서의 종류"가 같은 모양으로 보인다. 정본은 분류(0026)이고, 분류가
         없는 이관 문서만 옛 doc_type 이 그대로 보인다. */
      key: "category", label: "분류", type: "name", minWidth: "7rem", hideNarrow: true,
      render: (doc) => (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
          {doc.category?.name || doc.doc_type || "-"}
        </Typography>
      ),
    },
    {
      /* 🔴 작성자는 **세 가지 사실**이다. 우리 사용자가 썼거나, 원본에 이름만 적혀
         있거나, 모른다. 예전에는 가운데가 없어서 가져오기를 돌린 관리자가 작성자로
         섰고 — 화면이 「이 사람이 524건을 썼다」고 거짓말했다. Confluence 는 작성자의
         이메일을 안 주므로(실측: 8명 중 1명, 그마저 우리 계정에 없다) 우리 계정으로
         이을 수 없다. 이름만 남기고, 그것이 우리 사용자가 아니라는 것도 함께 보인다. */
      key: "author", label: "작성자", type: "name", minWidth: "8rem", hideNarrow: true,
      render: (doc) => (
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
          {doc.author ? <UserAvatar person={doc.author} size="sm" /> : null}
          <Typography variant="body2" sx={KO_WORD_BREAK}>
            {doc.author?.display_name || doc.legacy_author_name || "-"}
          </Typography>
        </Stack>
      ),
    },
    {
      key: "updated_at", label: "최종 수정", type: "datetime", minWidth: "9.5rem", hideNarrow: true,
      render: (doc) => fmtDateTimeCompact(doc.updated_at),
    },
    {
      /* 첨부와 댓글이 있다는 사실은 **문서를 고르는 근거**다. 열어 봐야 아는 값이면
         목록에서 못 고른다. 0 은 안 그린다 — 대부분이 0 이라 그리면 소음이다.
         셋 중 **가장 먼저 접히는** 열이다 (D-380). */
      key: "counts", label: "첨부, 댓글", type: "enum", minWidth: "8rem", hideNarrow: true,
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
      key: "more", label: "작업", type: "actions", width: "6.5rem",
      render: (doc) => (
        <OverflowMenu
          ariaLabel={`${doc.title} 작업`}
          items={[
            { label: "문서 열기", onClick: () => onOpen(doc) },
            {
              label: "휴지통으로 보내기",
              onClick: async () => {
                const ok = await confirm(
                  "휴지통에서 되살릴 수 있습니다. 판 이력과 댓글은 그대로 남습니다.",
                  { title: `${doc.title}을(를) 휴지통으로 보낼까요?`, confirmLabel: "보내기" },
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
