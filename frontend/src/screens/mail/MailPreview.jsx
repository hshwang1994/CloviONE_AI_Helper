import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { ErrorState, Field, FieldRow, Segmented, Skeleton } from "../../ui/kit.jsx";
import { FONT_SIZE, KO_WORD_BREAK, RADIUS } from "../../ui/theme.js";

/* 메일 모양 미리 보기 (계획 M3, D-549) — 관리자가 사람들이 받는 메일의 모양을 본다. 디자인 검수 도구다.
 *
 * 종류(열 가지) · 보기(HTML · 텍스트) · 폭(데스크톱 680 · 모바일 375)을 고른다. 보기와 폭은 보는 방식 전환이라 세그먼티드다(RULES §3).
 * 서버는 **표본만** 준다(`app/mail/samples.py` — 실제 사용자 · 티켓 · 토큰이 없다). HTML 은 빈 `sandbox` 의 `srcDoc` 틀 안에 그린다:
 * 문서가 아무것도 실행하지 못하고(스크립트 · 양식 · 팝업 없음), 전역 `X-Frame-Options: DENY` 라 `src` 주소는 쓸 수 없다.
 */

const VIEWS = [{ value: "html", label: "HTML" }, { value: "text", label: "텍스트" }];
const WIDTHS = [{ value: "desktop", label: "데스크톱" }, { value: "mobile", label: "모바일" }];
const WIDTH_PX = { desktop: 680, mobile: 375 };

export function MailPreview() {
  const [kind, setKind] = React.useState("ticket_assigned");
  const [view, setView] = React.useState("html");
  const [width, setWidth] = React.useState("desktop");
  const kinds = useQuery({ queryKey: ["mail-templates"], queryFn: () => api("/api/admin/mail/templates") });
  const preview = useQuery({
    queryKey: ["mail-template-preview", kind],
    queryFn: () => api(`/api/admin/mail/templates/${encodeURIComponent(kind)}/preview`),
  });
  const items = (kinds.data && kinds.data.items) || [];
  const data = preview.data;
  return (
    <Box sx={{ display: "grid", gap: 2, minWidth: 0 }} data-testid="mail-preview">
      <FieldRow columns={["16rem", "max-content", "max-content"]}>
        <Field label="종류" labelId="mail-preview-kind-label">
          <TextField id="mail-preview-kind" select size="small" fullWidth value={kind} onChange={(e) => setKind(e.target.value)}
            SelectProps={{ labelId: "mail-preview-kind-label" }}>
            {(items.length ? items : [{ key: kind, label: "불러오는 중" }]).map((k) => (
              <MenuItem key={k.key} value={k.key}>{k.label}</MenuItem>
            ))}
          </TextField>
        </Field>
        <Field label="보기" fit>
          <Segmented ariaLabel="미리 보기 형식" value={view} options={VIEWS} onChange={setView} />
        </Field>
        <Field label="폭" fit>
          <Segmented ariaLabel="미리 보기 폭" value={width} options={WIDTHS} onChange={setWidth} />
        </Field>
      </FieldRow>
      {preview.isLoading ? <Skeleton lines={4} /> : preview.isError ? (
        <ErrorState layout="region" error={preview.error} onRetry={preview.refetch} />
      ) : data ? (
        <>
          <Typography sx={{ fontSize: FONT_SIZE.bodySm, ...KO_WORD_BREAK }} data-testid="mail-preview-subject">
            <Box component="span" sx={{ color: "text.secondary", mr: 1 }}>제목</Box>
            {data.subject}
          </Typography>
          <Box
            sx={{
              bgcolor: "background.inset", border: 1, borderColor: "divider", borderRadius: `${RADIUS.md}px`,
              p: 2, overflowX: "auto", display: "flex", justifyContent: "center",
            }}
          >
            {view === "html" ? (
              <Box
                component="iframe"
                title="메일 미리 보기"
                sandbox=""
                srcDoc={data.html}
                data-testid="mail-preview-frame"
                sx={{ width: WIDTH_PX[width], maxWidth: "none", height: "40rem", border: 0, bgcolor: "background.paper", flex: "0 0 auto" }}
              />
            ) : (
              <Box
                component="pre"
                data-testid="mail-preview-text"
                sx={{
                  m: 0, width: WIDTH_PX[width], maxWidth: "none", flex: "0 0 auto", whiteSpace: "pre-wrap",
                  fontSize: FONT_SIZE.bodySm, bgcolor: "background.paper", p: 2, borderRadius: `${RADIUS.sm}px`,
                }}
              >
                {data.text}
              </Box>
            )}
          </Box>
        </>
      ) : null}
    </Box>
  );
}

export default MailPreview;
