import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { KO_WORD_BREAK } from "../ui/theme.js";
import {
  NO_HEALTH_SCORE, NO_PROGRESS_SAMPLE,
  formulaText, percentText, sampleText, weightModeText,
} from "./project-format.js";

/* 진행률과 Health 를 그리는 부품. 목록과 상세가 **같은 것**을 쓴다.
 *
 * ## 진행률은 포털이 계산한 값 하나다 (사용자 지시)
 *
 * 예전에는 포털 계산값과 Notion 값을 나란히 놓고, 다르면 "두 값이 다릅니다" 라고 경고했다.
 * 그 화면은 사용자에게 **어느 쪽도 믿지 말라**고 말하는 화면이었다. 정본은 포털이고
 * Notion 은 데이터 소스(DB)일 뿐이다 - 저쪽 숫자를 굳이 옆에 놓고 비교할 이유가 없다.
 *
 * 대신 **계산 근거는 남긴다**(`ProgressBasis`). 그건 "믿지 마라" 가 아니라 "이렇게 셌다"
 * 라서 성격이 반대다. 근거가 없으면 숫자 하나는 그냥 주장이고, 근거가 있으면 확인할 수
 * 있는 사실이 된다.
 *
 * ⚠️ 서버 응답의 `notion_progress_pct` / `notion_percent` 는 그대로 둔다(디버깅용). 화면이
 * 그것을 **눈에 띄게 그리지 않는 것**이 이 파일의 몫이다.
 *
 * ## Health 를 왜 점수만 그리지 않는가
 *
 * "이 프로젝트 47점"을 본 팀장이 할 수 있는 일이 없다. 이유가 곧 할 일 목록이라,
 * 점수 옆에는 **어떤 규칙이 몇 점을 깎았고 무엇을 보고 그랬는지**가 반드시 함께 온다.
 * 판정하지 못한 항목도 감추지 않는다 - 감추면 가장 정보가 없는 프로젝트가 화면에서
 * 가장 건강해 보인다(app/projects/health.py 모듈 docstring).
 */

function Metric({ label, value, dim }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography
        sx={{
          fontSize: dim ? "0.9375rem" : "clamp(1.25rem, 1rem + .8vw, 1.75rem)",
          fontWeight: dim ? 500 : 800, lineHeight: 1.2, ...KO_WORD_BREAK,
        }}
        color={dim ? "text.secondary" : "text.primary"}
      >
        {value}
      </Typography>
    </Box>
  );
}

function BasisRow({ label, children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "4.5rem minmax(0, 1fr)" }, gap: 1, py: 0.5 }}>
      <Typography component="dt" variant="body2" color="text.secondary">{label}</Typography>
      <Typography component="dd" variant="body2" sx={{ m: 0, ...KO_WORD_BREAK }}>{children}</Typography>
    </Box>
  );
}

/* 계산 근거. 이것이 없으면 위의 숫자는 확인할 수 없는 주장일 뿐이다. */
export function ProgressBasis({ basis }) {
  if (!basis) return null;
  return (
    <Box component="dl" sx={{ m: 0, mt: 1.5, pt: 1.5, borderTop: 1, borderColor: "divider" }}>
      <BasisRow label="계산식">{formulaText(basis)}</BasisRow>
      <BasisRow label="표본">{sampleText(basis)}</BasisRow>
      <BasisRow label="가중">{weightModeText(basis)}</BasisRow>
    </Box>
  );
}

/* 진행률 한 값 + 계산 근거. 상세 화면의 `/progress` 응답을 그린다.
 *
 * 값이 비면 **"작업이 아직 없다"** 다. 그 경로는 요청할 때마다 실제로 세므로, null 은
 * "세어 봤는데 분모가 0" 이라는 뜻 하나뿐이다. 목록의 `progress_pct` 는 캐시라 null 의 뜻이
 * 다르고("아직 한 번도 계산 안 함"), 그래서 목록은 다른 문구를 쓴다(`NO_PROGRESS_CACHE`).
 * 어느 쪽도 0% 가 아니다(project-format.js 의 계약). */
export function ProgressBlock({ percent, basis }) {
  const value = percentText(percent);
  return (
    <Box>
      <Metric label="진행률" value={value || NO_PROGRESS_SAMPLE} dim={!value} />
      <ProgressBasis basis={basis} />
    </Box>
  );
}

/* 점수와 **이유**. `reasons` 가 비어도 이 목록 자리는 남는다 - 자리 자체가 "점수는 규칙이
 * 깎아서 나온 값" 이라는 사실을 말한다. */
export function HealthBlock({ score, reasons, unknown }) {
  const list = Array.isArray(reasons) ? reasons : [];
  const unsure = Array.isArray(unknown) ? unknown : [];
  return (
    <Box>
      {score == null ? (
        <>
          <Typography sx={{ fontSize: "1.0625rem", fontWeight: 750 }}>{NO_HEALTH_SCORE}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, ...KO_WORD_BREAK }}>
            판정할 수 있는 지표가 하나도 없었습니다. 0점과는 다른 상태입니다.
          </Typography>
        </>
      ) : (
        <Typography sx={{ fontSize: "clamp(1.5rem, 1.2rem + .6vw, 2rem)", fontWeight: 800, lineHeight: 1.1 }}>
          {score + "점"}
        </Typography>
      )}

      <Typography component="h3" variant="body2" sx={{ fontWeight: 750, mt: 2 }}>
        점수를 깎은 이유
      </Typography>
      {list.length ? (
        <Box component="ul" sx={{ m: 0, mt: 1, pl: 0, listStyle: "none", display: "grid", gap: 1.25 }}>
          {list.map((r) => (
            <Box component="li" key={r.rule} sx={{ display: "grid", gap: 0.25 }}>
              <Box sx={{ display: "flex", gap: 1, alignItems: "baseline", flexWrap: "wrap" }}>
                <Typography component="span" sx={{ fontWeight: 700, fontSize: "0.9375rem" }}>
                  {r.label}
                </Typography>
                <Typography component="span" color="error.main" sx={{ fontWeight: 800, fontSize: "0.875rem" }}>
                  {"-" + r.penalty + "점"}
                </Typography>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{r.detail}</Typography>
            </Box>
          ))}
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          점수를 깎은 규칙이 없습니다.
        </Typography>
      )}

      {unsure.length ? (
        <>
          <Typography component="h3" variant="body2" sx={{ fontWeight: 750, mt: 2 }}>
            판정하지 못한 항목
          </Typography>
          <Box component="ul" sx={{ m: 0, mt: 1, pl: 0, listStyle: "none", display: "grid", gap: 1 }}>
            {unsure.map((u) => (
              <Box component="li" key={u.rule} sx={{ display: "grid", gap: 0.25 }}>
                <Typography component="span" sx={{ fontWeight: 700, fontSize: "0.9375rem" }}>
                  {u.label}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>{u.why}</Typography>
              </Box>
            ))}
          </Box>
        </>
      ) : null}
    </Box>
  );
}
