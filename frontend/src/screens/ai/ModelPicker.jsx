import React from "react";
import { useQuery } from "@tanstack/react-query";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { api } from "../../lib/api.js";
import { Button, Callout, Field } from "../../ui/kit.jsx";

/* 모델 (계획 A3, D-539) — 인증이 끝나면 목록을 저절로 받는다. 사람이 「모델 불러오기」를 누르지 않는다.
 *
 * - 모델이 비어 있고 추천이 있으면 그 하나를 **명시적으로** 저장한다(`auto_model`, 감사에 auto) — 「추천 모델로 정했습니다.
 *   바꿀 수 있습니다.」. 사람이 고른 모델은 바꾸지 않는다.
 * - 모델을 고르면 곧바로 저장한다. 저장 응답이 연결 확인을 열고, 그 모델로 실제 생성이 성공해야 「정상」이다(그동안 확인 중).
 * - 목록을 못 받으면 까닭과 함께 [다시 불러오기] · [직접 입력]이 선다. 단추는 회복 동작뿐이다.
 */

export const MODELS_KEY = (provider, method) => ["ai-models", provider || "", method || ""];

export function ModelPicker({ config, method, onSave, saving = false, onAutoPicked }) {
  const ready = Boolean(config.provider && config.auth_method && method && method.ready);
  const models = useQuery({
    queryKey: MODELS_KEY(config.provider, config.auth_method),
    queryFn: () => api(
      "/api/admin/ai/models?provider=" + encodeURIComponent(config.provider)
      + "&auth_method=" + encodeURIComponent(config.auth_method),
    ),
    enabled: ready,
    retry: false,
    staleTime: 60_000,
  });
  const [manual, setManual] = React.useState(false);
  const [typed, setTyped] = React.useState("");

  /* 모델이 비었을 때 추천을 한 번만 저장한다 — 같은 연결로는 다시 하지 않는다(사람이 비워 둔 것을 되살리지 않는다). */
  const picked = React.useRef(null);
  const recommended = models.data && models.data.recommended_id;
  React.useEffect(() => {
    const key = `${config.provider}/${config.auth_method}`;
    if (!ready || config.model || !recommended || picked.current === key) return;
    picked.current = key;
    onSave({ model: recommended, auto_model: true });
    if (onAutoPicked) onAutoPicked(recommended);
  }, [ready, config.model, config.provider, config.auth_method, recommended, onSave, onAutoPicked]);

  const list = (models.data && models.data.models) || [];
  const known = list.some((m) => m.id === config.model);
  const failed = models.isError;
  const help = !ready
    ? "인증을 마치면 사용할 수 있는 모델 목록을 자동으로 가져옵니다."
    : "연결하면 사용할 수 있는 모델 목록을 자동으로 가져옵니다. 모델을 바꾸면 곧바로 저장하고 연결을 다시 확인합니다.";

  if (manual) {
    return (
      <Field
        label="모델" htmlFor="ai-model-manual" width="xl"
        help="제공자가 알려 준 모델 이름을 그대로 넣습니다."
        action={(
          <>
            <Button variant="primary" aria-label="모델 저장" disabled={!typed.trim() || saving} loading={saving}
              onClick={() => { onSave({ model: typed.trim() }); setManual(false); }}>
              저장
            </Button>
            <Button variant="ghost" onClick={() => { setManual(false); models.refetch(); }}>목록에서 고르기</Button>
          </>
        )}
      >
        <TextField
          id="ai-model-manual" size="small" fullWidth value={typed}
          onChange={(e) => setTyped(e.target.value)}
          inputProps={{ "aria-label": "모델 이름", spellCheck: false }}
        />
      </Field>
    );
  }

  return (
    <>
      <Field
        label="모델" htmlFor="ai-model" width="xl" help={help}
        action={(
          <Button disabled={!ready} loading={models.isFetching} onClick={() => models.refetch()}>
            모델 목록 새로고침
          </Button>
        )}
      >
        <TextField
          id="ai-model" select size="small" fullWidth disabled={!ready || saving || (!list.length && !config.model)}
          value={config.model || ""}
          SelectProps={{ displayEmpty: true }}
          onChange={(e) => { if (e.target.value && e.target.value !== config.model) onSave({ model: e.target.value }); }}
          inputProps={{ "aria-label": "모델" }}
        >
          <MenuItem value="" disabled>{ready ? (models.isFetching ? "목록을 가져오는 중입니다" : "모델을 고르세요") : "인증을 먼저 마치세요"}</MenuItem>
          {config.model && !known ? (
            <MenuItem value={config.model}>{`${config.model} (목록에 없음)`}</MenuItem>
          ) : null}
          {list.map((m) => (
            <MenuItem key={m.id} value={m.id}>{m.recommended ? `${m.label} (추천)` : m.label}</MenuItem>
          ))}
        </TextField>
      </Field>
      {failed ? (
        <Callout
          tone="warn" compact
          action={<Button size="sm" onClick={() => { setTyped(config.model || ""); setManual(true); }}>직접 입력</Button>}
        >
          {(models.error && models.error.message) || "모델 목록을 가져오지 못했습니다."}
        </Callout>
      ) : null}
    </>
  );
}

export default ModelPicker;
