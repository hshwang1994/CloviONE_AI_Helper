/* 비밀 값 한 칸 (계획 2.3).
 *
 * SMTP 비밀번호와 AI API 키를 **서버에 들어가지 않고** 넣는 칸이다. 값은 들어가기만 하고
 * 돌아오지 않는다 - 서버는 "저장돼 있는가" 와 "언제 바꿨는가" 만 알려 준다(`/api/admin/secrets`).
 * 그래서 이 칸은 저장된 값을 보여 주지 않고, 새 값을 넣으면 바꾸고, 삭제로 없앤다.
 *
 * 입력칸은 `type="password"` 와 `autoComplete="new-password"` 다. 브라우저가 로그인 비밀번호를
 * 여기에 자동으로 채우면 관리자 비밀번호가 SMTP 비밀번호로 저장되는 사고가 난다.
 */
import React, { useId, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { useGuardedMutation } from "../lib/useGuardedMutation.js";
import { Button, FieldLabel } from "./kit.jsx";

export const SECRETS_QUERY_KEY = ["admin-secrets"];

export function useSecretStatus(slot) {
  const q = useQuery({ queryKey: SECRETS_QUERY_KEY, queryFn: () => api("/api/admin/secrets") });
  const item = (q.data?.items || []).find((i) => i.slot === slot) || null;
  return { ...q, item };
}

export function SecretField({ slot, label, help, disabled = false, onChanged }) {
  const inputId = useId();
  const helpId = useId();
  const qc = useQueryClient();
  const { item, isLoading } = useSecretStatus(slot);
  const [value, setValue] = useState("");
  const [error, setError] = useState(null);

  const done = () => {
    setValue("");
    setError(null);
    qc.invalidateQueries({ queryKey: SECRETS_QUERY_KEY });
    if (onChanged) onChanged();
  };
  const save = useGuardedMutation({
    key: () => `save:${slot}`,
    mutationFn: (v) => api(`/api/admin/secrets/${encodeURIComponent(slot)}`, { method: "PUT", body: { value: v } }),
    onSuccess: done,
    onError: (e) => setError(e),
  });
  const clear = useGuardedMutation({
    key: () => `clear:${slot}`,
    mutationFn: () => api(`/api/admin/secrets/${encodeURIComponent(slot)}`, { method: "DELETE" }),
    onSuccess: done,
    onError: (e) => setError(e),
  });

  const stored = !!item?.stored;
  const busy = save.isPending || clear.isPending;
  const state = isLoading
    ? "저장 상태를 불러오는 중입니다."
    : stored
      ? `저장된 값이 있습니다. 마지막으로 바꾼 시각은 ${fmtDateTime(item.updated_at)}입니다.`
      : "저장된 값이 없습니다.";

  return (
    <Box sx={{ minWidth: 0 }}>
      <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
      <Box sx={{ display: "flex", gap: 1, alignItems: "center", minWidth: 0 }}>
        <TextField
          id={inputId}
          type="password"
          size="small"
          fullWidth
          disabled={disabled || busy}
          autoComplete="new-password"
          placeholder={stored ? "바꾸려면 새 값을 입력하세요." : "값을 입력하세요."}
          inputProps={{ "aria-describedby": helpId, spellCheck: false }}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && value.trim()) { e.preventDefault(); save.mutate(value); } }}
        />
        <Button size="small" onClick={() => save.mutate(value)} disabled={disabled || busy || !value.trim()} loading={save.isPending}>
          저장
        </Button>
        {stored ? (
          <Button size="small" variant="ghost" onClick={() => clear.mutate()} disabled={disabled || busy} loading={clear.isPending}>
            삭제
          </Button>
        ) : null}
      </Box>
      <Typography id={helpId} variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
        {state}{help ? ` ${help}` : ""}
      </Typography>
      {error ? (
        <Typography role="alert" variant="caption" color="error" sx={{ display: "block", mt: 0.5 }}>
          {error.message}
        </Typography>
      ) : null}
    </Box>
  );
}
