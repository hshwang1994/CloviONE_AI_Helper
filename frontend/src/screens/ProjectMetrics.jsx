import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Callout } from "../ui/kit.jsx";
import { KO_WORD_BREAK } from "../ui/theme.js";
import {
  DIFFERS_NOTE, NO_HEALTH_SCORE, NO_NOTION_PROGRESS, NO_PROGRESS_CACHE, NO_PROGRESS_SAMPLE,
  formulaText, percentText, progressDiffers, sampleText, weightModeText,
} from "./project-format.js";

/* 진행률과 Health 를 그리는 부품. 목록 카드와 상세가 **같은 것**을 쓴다.
 *
 * ## 진행률을 왜 두 값으로 그리는가
 *
 * 포털과 Notion 의 진행률이 다른 것은 고장이 아니라 정상 상태다. Notion 의 rollup 은
 * 취소한 작업을 완료로 세고 하위 작업을 상위 작업과 두 번 센다(app/projects/progress.py 에
 * 실측 근거가 있다). 그래서 서버는 두 값을 나란히 보내고, 화면은 둘 다 그린다.
 *
 * 한쪽만 그리면 사용자는 Notion 화면과 포털을 번갈아 보다가 "포털이 틀렸다"고 결론 내리고,
 * 그 다음부터는 **둘 다** 안 본다. 그래서 숫자 옆에 계산식과 표본 수를 함께 적는다.
 *
 * ## Health 를 왜 점수만 그리지 않는가
 *
 * "이 프로젝트 47점"을 본 팀장이 할 수 있는 일이 없다. 이유가 곧 할 일 목록이라,
 * 점수 옆에는 **어떤 규칙이 몇 점을 깎았고 무엇을 보고 그랬는지**가 반드시 함께 온다.
 * 판정하지 못한 항목도 감추지 않는다 - 감추면 가장 정보가 없는 프로젝트가 화면에서
 * 가장 건강해 보인다(app/projects/health.py 모듈 docstring).
 */

const METRIC_GRID = {
  display: "grid", gap: 2,
  gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
};

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

/* 계산 근거. 이것이 없으면 위의 두 숫자는 서로를 부정하는 두 주장일 뿐이다. */
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

/* `missingMeans` 는 **비어 있음의 뜻**이다. 두 가지가 있고 서로 다른 말이라 문구도 다르다:
 *   "cache"  프로젝트 행의 캐시가 비었다 = 아직 한 번도 계산 안 했다
 *   "sample" 세어 봤는데 분모가 0이었다 = 걸린 작업이 아직 없다
 * 둘 다 0% 가 아니다(project-format.js 의 계약). */
export function ProgressPair({ appPercent, notionPercent, basis, missingMeans, footnote }) {
  const app = percentText(appPercent);
  const notion = percentText(notionPercent);
  const differs = progressDiffers(appPercent, notionPercent);
  const noSample = missingMeans === "sample";

  return (
    <Box>
      <Box sx={METRIC_GRID}>
        <Metric
          label="포털 계산"
          value={app || (noSample ? NO_PROGRESS_SAMPLE : NO_PROGRESS_CACHE)}
          dim={!app}
        />
        <Metric label="Notion 값" value={notion || NO_NOTION_PROGRESS} dim={!notion} />
      </Box>
      {differs ? (
        <Box sx={{ mt: 1.5 }}><Callout tone="warn">{DIFFERS_NOTE}</Callout></Box>
      ) : null}
      {/* 한쪽만 없는 경우도 말은 해 준다. 값 자리의 문구만으로는 "그래서 저 70% 를 믿어도
          되나" 에 답하지 못한다. */}
      {!app && notion ? (
        <Box sx={{ mt: 1.5 }}>
          <Callout tone="info">
            {noSample
              ? "포털은 셀 작업을 찾지 못했습니다. 옆의 Notion 값은 다른 규칙으로 계산된 값이라 그대로 옮겨 적지 않습니다."
              : "포털 계산값이 아직 없어 두 값을 비교할 수 없습니다."}
          </Callout>
        </Box>
      ) : null}
      <ProgressBasis basis={basis} />
      {footnote ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1, ...KO_WORD_BREAK }}>
          {footnote}
        </Typography>
      ) : null}
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
