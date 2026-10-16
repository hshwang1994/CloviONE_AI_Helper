import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { ErrorState, Field, FieldRow, Segmented, Skeleton } from "../../ui/kit.jsx";
import { FONT_SIZE, KO_WORD_BREAK, RADIUS } from "../../ui/theme.js";

/* 메일 미리 보기 (계획 M3, D-549 · D-592) — 관리자가 사람들이 받는 메일의 모양을 본다. 디자인 검수 도구다.
 *
 * 종류(열 가지) · 보기(HTML · 텍스트) · 폭(데스크톱 680 · 모바일 375) · 테마(라이트 · 다크)를 고른다. 보기 · 폭 · 테마는 보는 방식 전환이라
 * 세그먼티드다(RULES §3). 테마는 서버가 그린다(D-571): 다크는 메일 앱의 다크 규칙을 강제로 세운 HTML 이고 라이트는 보는 사람의 운영체제가
 * 다크여도 밝은 HTML 이다. 라이트는 서버 기본값이라 주소에 싣지 않는다. 틀의 바탕은 서버가 준 그 모양의 메일 바탕색이다.
 * 서버는 **표본만** 준다(`app/mail/samples.py` — 실제 사용자 · 티켓 · 토큰이 없다). HTML 은 빈 `sandbox` 의 `srcDoc` 틀 안에 그린다:
 * 문서가 아무것도 실행하지 못하고(스크립트 · 양식 · 팝업 없음), 전역 `X-Frame-Options: DENY` 라 `src` 주소는 쓸 수 없다.
 */

const VIEWS = [{ value: "html", label: "HTML" }, { value: "text", label: "텍스트" }];
const WIDTHS = [{ value: "desktop", label: "데스크톱" }, { value: "mobile", label: "모바일" }];
const WIDTH_PX = { desktop: 680, mobile: 375 };
const SCHEMES = [{ value: "light", label: "라이트" }, { value: "dark", label: "다크" }];

export function MailPreview() {
  const [kind, setKind] = React.useState("ticket_assigned");
  const [view, setView] = React.useState("html");
  const [width, setWidth] = React.useState("desktop");
  const [scheme, setScheme] = React.useState("light");
  const kinds = useQuery({ queryKey: ["mail-templates"], queryFn: () => api("/api/admin/mail/templates") });
  const preview = useQuery({
    queryKey: ["mail-template-preview", kind, scheme],
    queryFn: () => api(`/api/admin/mail/templates/${encodeURIComponent(kind)}/preview${scheme === "dark" ? "?scheme=dark" : ""}`),
  });
  const items = (kinds.data && kinds.data.items) || [];
  const data = preview.data;
  return (
    <Box sx={{ display: "grid", gap: 2, minWidth: 0 }} data-testid="mail-preview">
      <FieldRow columns={["16rem", "max-content", "max-content", "max-content"]}>
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
        <Field label="테마" fit>
          <Segmented ariaLabel="미리 보기 테마" value={scheme} options={SCHEMES} onChange={setScheme} />
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
          {/* 견본 틀이다 — 메일 앱이 메일을 그리는 바탕을 흉내 내는 오목면이고, 그 안의 흰 판은 메일 자신이다. 판 안의 카드가 아니라
              부품 갤러리의 견본 틀과 같은 자리라 시각 프로브(`nested_card`)에 그 사실을 말한다(`data-allow-nested`).
              틀은 메일 폭(데스크톱 680 · 모바일 375)만큼만 서고 도구 줄과 같은 왼쪽 선에서 시작한다(D-592) — 판 폭 오목면 한가운데에
              메일만 떠 있으면 넓은 회색 안의 좁은 카드로 읽혔다(캡처 r23 45). 판이 메일보다 좁으면 틀 안에서 가로로 굴린다. */}
          <Box
            data-allow-nested=""
            data-testid="mail-preview-well"
            sx={{
              bgcolor: "background.inset", border: 1, borderColor: "divider", borderRadius: `${RADIUS.md}px`,
              p: 2, overflowX: "auto", display: "flex", width: "fit-content", maxWidth: "100%",
            }}
          >
            {view === "html" ? (
              <Box
                component="iframe"
                title="메일 미리 보기"
                sandbox=""
                srcDoc={data.html}
                data-testid="mail-preview-frame"
                data-scheme={scheme}
                sx={{
                  width: WIDTH_PX[width], maxWidth: "none", height: "40rem", border: 0, flex: "0 0 auto",
                  bgcolor: data.background || "background.paper", colorScheme: scheme,
                }}
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
