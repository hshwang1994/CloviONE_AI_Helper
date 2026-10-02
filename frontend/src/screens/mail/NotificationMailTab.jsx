import React from "react";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { useInstantSave } from "../../lib/useInstantSave.js";
import { Card, Field, FormSection, useToast } from "../../ui/kit.jsx";
import { SettingRow } from "../../ui/adminKit.jsx";
import { KO_WORD_BREAK } from "../../ui/theme.js";
import { MailPreview } from "./MailPreview.jsx";

/* 메일 · 알림 메일 탭 (계획 M1 · M3, D-548 · D-549).
 *
 * 메일로 보낼 수 있는 알림의 허용 목록(누르는 즉시 저장되는 스위치), 오래된 메일의 기준(선택 칸 - 설정 값이라 보기 전환용 세그먼티드를
 * 쓰지 않는다), 알림 받을 주소의 규칙 안내, 그리고 메일 모양 미리 보기. 한 판 위의 구획이다(F7).
 */

const AGE_CHOICES = [1, 3, 7, 14, 30];
const FIELD = { mail_notification_types: "allowed", mail_notification_max_age_days: "max_age_days" };

function applyNotificationMail(status, { key, value }) {
  const field = FIELD[key];
  if (!field || !status || !status.notification_mail) return status;
  return { ...status, notification_mail: { ...status.notification_mail, [field]: value } };
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
      <FormSection titleAs="h2" title="메일로 보내는 알림"
        description="여기서 허용한 알림만 사용자가 메일로 받을 수 있습니다. 사용자는 내 프로필에서 메일 알림을 켜고 받을 알림을 고릅니다.">
        {/* 여러 단으로 흐르는 목록이라 줄 사이 윗선을 긋지 않는다 - 단마다 첫 줄만 선이 있거나 없으면 단끼리 어긋나 보인다. */}
        <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, columnWidth: "20rem", columnGap: 3,
          "& .k-settingrow": { borderTop: 0 } }}>
          {catalog.map((row) => (
            <Box component="li" key={row.key} sx={{ breakInside: "avoid" }}>
              <SettingRow
                compact label={row.label} description={row.help} controlId={`mail-allow-${row.key}`}
                action={(
                  <Switch
                    id={`mail-allow-${row.key}`} checked={allowed.has(row.key)} disabled={!canWrite}
                    onChange={() => toggle(row.key)}
                    slotProps={{ input: { "aria-label": `${row.label} 메일 허용` } }}
                  />
                )}
              />
            </Box>
          ))}
        </Box>
      </FormSection>

      <FormSection titleAs="h2" title="오래된 메일"
        description="메일 서버가 멈춘 동안 쌓인 메일은 이 기간이 지나면 보내지 않습니다. 설정 전에 쌓인 메일을 다시 보낼 때도 이 기간 안의 것만 보냅니다.">
        <Field label="보내지 않는 기준" labelId="mail-max-age-label" width="sm">
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

      <FormSection titleAs="h2" title="메일 모양" description="사람들이 받는 메일을 표본 내용으로 미리 봅니다.">
        <MailPreview />
      </FormSection>
    </Card>
  );
}

export default NotificationMailTab;
