import React from "react";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { useInstantSave } from "../../lib/useInstantSave.js";
import { Card, Field, FormSection, useToast } from "../../ui/kit.jsx";
import { SettingRow, SettingRows } from "../../ui/adminKit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";
import { MailPreview } from "./MailPreview.jsx";

/* 메일 · 알림 메일 탭 (계획 M1 · M3, D-548 · D-549 · D-592).
 *
 * 메일 알림 종류(누르는 즉시 저장되는 스위치), 오래된 알림 발송 제한(선택 칸 - 설정 값이라 보기 전환용 세그먼티드를 쓰지 않는다), 알림
 * 받을 주소의 규칙 안내, 그리고 메일 미리 보기. 한 판 위의 구획이다(F7).
 *
 * 종류는 범주(서버의 `group` — 티켓 · 승인 · 채팅 · 문서와 게시판 · AI)마다 묶고 두 단까지만 흐른다. 예전에는 20rem 단이 1920 에서 넷으로
 * 흘러 스위치 열이 넷이었다(캡처 r23 45). 한 단 안에서는 스위치가 같은 오른쪽 세로선에 서고, 설명은 이름 바로 아래다.
 * 「발송 제한 기간」은 그 나이를 넘은 알림 · 초대 · 승인 요청 · 백업 실패 메일을 보내지 않는 만료 기준이다(`app/mail/relevance.py::
 * still_relevant` — 비밀번호 재설정 · 시험 메일 · 확인 코드 · 계정 보안 메일은 예외). 쌓인 메일을 다시 보내는 창도 같은 값이다.
 */

const AGE_CHOICES = [1, 3, 7, 14, 30];
const FIELD = { mail_notification_types: "allowed", mail_notification_max_age_days: "max_age_days" };

function applyNotificationMail(status, { key, value }) {
  const field = FIELD[key];
  if (!field || !status || !status.notification_mail) return status;
  return { ...status, notification_mail: { ...status.notification_mail, [field]: value } };
}

/* 범주별 묶음 — 서버가 준 순서 그대로 같은 범주끼리 모은다. 범주가 없는 응답(옛 서버)은 이름 없는 묶음 하나다. */
function groupRows(catalog) {
  const groups = [];
  for (const row of catalog) {
    const name = row.group || "";
    const last = groups[groups.length - 1];
    if (last && last.name === name) last.rows.push(row);
    else groups.push({ name, rows: [row] });
  }
  return groups;
}

export function NotificationMailTab({ status }) {
  const toast = useToast();
  const canWrite = Boolean((status.capabilities || {}).can_operate);
  const save = useInstantSave({
    queryKey: ["mail-status"],
    mutationFn: ({ key, value }) => api("/api/admin/settings/" + key, { method: "PUT", body: { value } }),
    apply: applyNotificationMail,
    onSaved: () => toast("알림 메일 설정을 저장했습니다.", "success"),
    onError: (e) => toast(e.message, "error"),
  });
  const info = status.notification_mail || {};
  const catalog = info.catalog || [];
  const allowed = new Set(info.allowed || []);
  const days = info.max_age_days;
  const ages = AGE_CHOICES.includes(days) ? AGE_CHOICES : [...AGE_CHOICES, days].filter((d) => d != null).sort((a, b) => a - b);
  const toggle = (key) => {
    const next = new Set(allowed);
    if (next.has(key)) next.delete(key); else next.add(key);
    save.mutate({ key: "mail_notification_types", value: catalog.map((row) => row.key).filter((k) => next.has(k)) });
  };
  return (
    <Card stack data-testid="mail-notification-tab">
      <FormSection titleAs="h2" title="메일 알림 종류"
        description="여기서 허용한 알림만 사용자가 메일로 받을 수 있습니다. 사용자는 내 프로필에서 메일 알림을 활성화하고 받을 알림을 고릅니다.">
        {/* 두 단까지만 흐르고(단 폭 20rem 이상), 범주 묶음은 단 사이에서 쪼개지지 않는다. */}
        <Box data-testid="mail-kind-groups" sx={{ columnCount: 2, columnWidth: "20rem", columnGap: 4 }}>
          {groupRows(catalog).map((group) => (
            <Box
              key={group.name || "all"} component="section" aria-label={group.name || undefined} data-kind-group={group.name}
              sx={{ breakInside: "avoid", display: "grid", gap: 0.5, pb: 2.5 }}
            >
              {group.name ? (
                <Typography component="h3" sx={{ m: 0, fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, color: "text.secondary" }}>
                  {group.name}
                </Typography>
              ) : null}
              <SettingRows>
                {group.rows.map((row) => (
                  <SettingRow
                    key={row.key} compact label={row.label} description={row.help} controlId={`mail-allow-${row.key}`}
                    action={(
                      <Switch
                        id={`mail-allow-${row.key}`} checked={allowed.has(row.key)} disabled={!canWrite}
                        onChange={() => toggle(row.key)}
                        slotProps={{ input: { "aria-label": `${row.label} 메일 허용` } }}
                      />
                    )}
                  />
                ))}
              </SettingRows>
            </Box>
          ))}
        </Box>
      </FormSection>

      <FormSection titleAs="h2" title="오래된 알림 발송 제한"
        description="메일 서버가 멈춘 동안 쌓인 알림, 초대, 승인 요청 메일은 이 기간이 지나면 보내지 않습니다. 쌓인 메일을 다시 보낼 때도 이 기간 안의 것만 보냅니다.">
        <Field label="발송 제한 기간" labelId="mail-max-age-label" width="sm">
          {canWrite ? (
            <TextField id="mail-max-age" select size="small" fullWidth value={days ?? ""}
              SelectProps={{ labelId: "mail-max-age-label" }}
              onChange={(e) => save.mutate({ key: "mail_notification_max_age_days", value: Number(e.target.value) })}>
              {ages.map((d) => <MenuItem key={d} value={d}>{d}일</MenuItem>)}
            </TextField>
          ) : <Typography sx={{ minHeight: 34, display: "flex", alignItems: "center" }}>{days}일</Typography>}
        </Field>
      </FormSection>

      <FormSection titleAs="h2" title="알림 받을 주소">
        <Typography variant="body2" sx={KO_WORD_BREAK}>
          알림 메일은 사용자의 계정 이메일로 갑니다. 사용자가 내 프로필에서 다른 주소를 확인 코드로 확인하면 그 주소로 보냅니다.
        </Typography>
      </FormSection>

      <FormSection titleAs="h2" title="메일 미리 보기" description="사람들이 받는 메일을 표본 내용으로 미리 봅니다.">
        <MailPreview />
      </FormSection>
    </Card>
  );
}

export default NotificationMailTab;
