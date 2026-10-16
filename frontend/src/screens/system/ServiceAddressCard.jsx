import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { errorText } from "../../lib/failure.js";
import { fmtDateTime } from "../../lib/format.js";
import { Button, Card, DotLabel, TechRows } from "../../ui/kit.jsx";
import { SettingList, SettingRow } from "../../ui/adminKit.jsx";
import { Disclosure } from "../../ui/Disclosure.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";
import { DomainChangeDialog } from "./DomainChangeDialog.jsx";
import {
  CHECK_LABEL, CHECK_TONE, CHECK_WORD, accessState, certCoverage, orderedChecks, publicDnsText,
} from "./serviceAddress.js";

/* 서비스 주소 카드 (계획 M4, D-574 · 서버 계약 D-573) — 「설정 › OS와 서비스 동작」 맨 위.
 *
 * 사람이 알아야 하는 것을 위에서 아래로 둔다: 대표 주소(알림 메일 · 링크가 쓰는 주소) → 지금 이 화면을 연 주소(대표와 다르면 별칭인지,
 * 이 서버가 모르는 이름인지) → 함께 쓰는 주소 → 인증서가 그 이름을 담는가 → 확인 넷 → 최근 적용 · 최근 오류. 원문 값(바인드 주소 ·
 * server_name · 인증서 경로 · env 값)은 「고급」 안이다.
 *
 * DNS 는 **이 서버가 쓰는 해석기 기준**이다. 공개 해석기의 답은 정보로만 따로 적고 완료로 표시하지 않는다 — 공개 DNS 는 이 서버가 바꿀
 * 수 없고, 사내와 공개가 다른 답을 주는 것(분리 DNS)이 정상인 설치가 있다. 확인은 화면을 열 때 한 번 하고(DNS 조회가 든다) 「다시
 * 확인」으로만 다시 한다.
 */

export const DOMAIN_KEY = ["system-domain"];

/* 판이 넓으면 두 열이다 — 왼쪽은 주소(대표 · 지금 접속 · 함께 쓰는), 오른쪽은 확인(인증서 · 상태 · 최근 적용 · 최근 오류). 한 열 목록은
   1920 에서 값이 판 폭의 3할만 쓰고 나머지가 비었다(캡처 m4-svc-1). 좁으면 한 열로 쌓이고 두 묶음 사이에 줄 선 하나가 선다. */
const TWO_COLUMN_REM = 60;
const COLUMNS_SX = {
  display: "grid", gridTemplateColumns: "minmax(0, 1fr)", columnGap: 4, minWidth: 0,
  [`@container service-address (min-width: ${TWO_COLUMN_REM}rem)`]: { gridTemplateColumns: "repeat(2, minmax(0, 1fr))" },
};
const RIGHT_COLUMN_SX = {
  minWidth: 0, borderTop: 1, borderColor: "divider",
  [`@container service-address (min-width: ${TWO_COLUMN_REM}rem)`]: { borderTop: 0 },
};

function StatusDots({ checks }) {
  return (
    <Box data-testid="service-address-checks" sx={{ display: "flex", flexWrap: "wrap", columnGap: 2, rowGap: 0.5, minWidth: 0 }}>
      {checks.map((c) => (
        <DotLabel key={c.key} data-check={c.key} data-check-state={c.state}
          tone={CHECK_TONE[c.state] || "neutral"} label={`${CHECK_LABEL[c.key] || c.label} ${CHECK_WORD[c.state] || CHECK_WORD.unknown}`} />
      ))}
    </Box>
  );
}

function certValue(cert, names) {
  const coverage = certCoverage(cert, names);
  if (!coverage.known) return { text: "확인하지 못했습니다", muted: true };
  const expiry = cert.not_after ? `${fmtDateTime(cert.not_after)}까지 유효합니다` : "만료일을 읽지 못했습니다";
  const kind = cert.self_signed ? "자체 서명 인증서이고 " : "";
  if (coverage.missing.length) {
    return { text: `이 이름이 없습니다(${coverage.missing.join(", ")})`, warn: true, detail: `${kind}${expiry}.` };
  }
  return { text: "이 이름이 들어 있습니다", detail: `${kind}${expiry}.` };
}

/* 최근 적용 — 감사에 남은 대표 주소 적용. 성공은 가장 새 성공 하나, 오류는 그 성공보다 뒤에 난 실패만이다(고친 뒤의 옛 실패는 오류가 아니다). */
export function recentRows(recent) {
  const list = recent || [];
  const success = list.find((r) => r.ok) || null;
  const failure = list.find((r) => !r.ok) || null;
  const failureIsOpen = failure && (!success || String(failure.at) > String(success.at));
  return { success, failure: failureIsOpen ? failure : null };
}

function who(row) {
  return row && row.actor ? ` ${row.actor}님이 적용했습니다.` : "";
}

export function ServiceAddressCard({ system }) {
  const [open, setOpen] = React.useState(false);
  const domain = system.domain || {};
  const request = system.request || {};
  const query = useQuery({
    queryKey: DOMAIN_KEY,
    queryFn: () => api("/api/admin/system/domain"),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  const body = query.data || {};
  const preview = body.preview || {};
  const current = preview.current || {};
  const canonical = domain.canonical || current.canonical || "";
  const aliases = domain.aliases || current.aliases || [];
  const names = canonical ? [canonical, ...aliases] : [];
  const access = accessState(request, { canonical, aliases });
  const cert = certValue(current.cert, names);
  const checks = orderedChecks(preview.checks);
  const problems = checks.filter((c) => c.state !== "ok" && c.message);
  const publicDns = publicDnsText(preview.dns);
  const { success, failure } = recentRows(body.recent_applies);
  const queryError = query.isError ? errorText(query.error, "서비스 주소를 확인하지 못했습니다.") : null;
  const helperDown = body.available === false || (body.status && body.status !== "ok");
  const previewFailed = !query.isLoading && !queryError && !helperDown && body.ok === false;

  const statusValue = query.isLoading ? "확인하는 중입니다"
    : queryError || helperDown || previewFailed ? "확인하지 못했습니다"
      : <StatusDots checks={checks} />;
  const statusDescription = queryError || (helperDown || previewFailed ? body.detail : null)
    || ["DNS는 사내 해석기(이 서버가 쓰는 해석기) 기준입니다.", publicDns].filter(Boolean).join(" ");

  const techRows = [
    ["바인드 주소", domain.bind_ip || current.bind_ip],
    ["server_name", (current.server_names || []).join(" ") || null],
    ["APP_BASE_URL", domain.app_base_url || current.app_base_url],
    ["TLS_CERT_PATH", domain.cert_path || (current.cert && current.cert.path)],
    ["인증서 SAN", current.cert && current.cert.readable
      ? [...(current.cert.sans || []), ...(current.cert.ips || [])].join(", ") : null],
    ["인증서 만료", current.cert && current.cert.not_after ? fmtDateTime(current.cert.not_after) : null],
    ["인증서 발급자", current.cert && current.cert.issuer],
    ["매니페스트 dns_name", domain.dns_name || current.dns_name],
    ["매니페스트 alias_names", aliases.length ? aliases.join(",") : null],
    ["앞단 프록시", (domain.upstream_proxies || current.upstream_proxies || []).join(", ") || null],
    ["이 서버의 DNS 답", ((preview.dns && preview.dns.system) || [])
      .map((r) => `${r.name} = ${(r.answers || []).join(", ") || r.error}`).join("; ") || null],
    ...checks.filter((c) => c.technical).map((c) => [`${CHECK_LABEL[c.key]} 확인`, c.technical]),
  ];

  return (
    <Card stack data-testid="service-address">
      <SettingList
        title="서비스 주소" sx={{ mt: 0 }}
        action={<Button onClick={() => setOpen(true)} disabled={!canonical}>주소 바꾸기</Button>}
      >
        <Box sx={{ containerType: "inline-size", containerName: "service-address", minWidth: 0 }}>
        <Box sx={COLUMNS_SX}>
        <Box sx={{ minWidth: 0 }} data-testid="service-address-names">
        <SettingRow
          label="대표 주소" value={canonical ? `https://${canonical}` : "확인하지 못했습니다"} tone={canonical ? undefined : "muted"}
          description="알림 메일과 링크가 이 주소를 씁니다."
        />
        <SettingRow
          label="지금 접속한 주소"
          value={access.kind === "alias" || access.kind === "foreign"
            ? <DotLabel tone="warn" label={request.url || request.host} data-testid="service-address-access" />
            : (request.url || "확인하지 못했습니다")}
          description={access.message}
        />
        <SettingRow
          last label="함께 쓰는 주소" value={aliases.length ? aliases.join(", ") : "없습니다"} tone={aliases.length ? undefined : "muted"}
          description="대표 주소와 같은 화면을 엽니다. 다른 주소로 보내지 않습니다."
        />
        </Box>
        <Box sx={RIGHT_COLUMN_SX} data-testid="service-address-health">
        <SettingRow
          label="인증서"
          value={query.isLoading ? "확인하는 중입니다" : cert.warn ? <DotLabel tone="warn" label={cert.text} /> : cert.text}
          tone={query.isLoading || cert.muted ? "muted" : undefined}
          description={cert.detail || "브라우저가 이 서버를 믿게 하는 인증서입니다."}
        />
        <SettingRow
          label="상태" value={statusValue} tone={typeof statusValue === "string" ? "muted" : undefined}
          description={statusDescription}
          action={<Button size="sm" loading={query.isFetching && !query.isLoading} onClick={() => query.refetch()}>다시 확인</Button>}
        >
          {problems.length && !helperDown ? (
            <Box component="ul" data-testid="service-address-problems" sx={{ m: 0, pl: 2.5, display: "grid", gap: 0.25 }}>
              {problems.map((c) => (
                <Typography component="li" key={c.key} sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
                  {`${CHECK_LABEL[c.key]}: ${c.message}`}
                </Typography>
              ))}
            </Box>
          ) : null}
        </SettingRow>
        <SettingRow
          label="최근 적용" last={!failure}
          value={success ? fmtDateTime(success.at) : "아직 없습니다"} tone={success ? undefined : "muted"}
          description={success ? `${success.detail || "적용했습니다."}${who(success)}` : "이 화면에서 주소를 바꾼 기록이 없습니다."}
        />
        {failure ? (
          <SettingRow
            last label="최근 오류" value={<DotLabel tone="danger" label={fmtDateTime(failure.at)} />}
            description={`${failure.detail || "적용하지 못했습니다."}${failure.rolled_back ? " 바꾸기 전 설정으로 되돌렸습니다." : ""}`}
          />
        ) : null}
        </Box>
        </Box>
        </Box>
      </SettingList>
      <Disclosure id="service-address-advanced" title="고급" summary="설정 파일과 웹 서버에 적힌 값을 그대로 봅니다.">
        <TechRows rows={techRows} labelWidth="11rem" />
      </Disclosure>
      {open ? (
        <DomainChangeDialog
          open onClose={() => setOpen(false)}
          domain={{ canonical, aliases, bind_ip: domain.bind_ip || current.bind_ip }}
          currentCert={current.cert || null}
        />
      ) : null}
    </Card>
  );
}

export default ServiceAddressCard;
