import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge, Button, Callout, Card, ErrorState, FormModal, PageHeader, Skeleton, useConfirm, useToast,
} from "../ui/kit.jsx";

/* Notion 관리 (9-4).
 *
 * ## 이 화면이 생긴 이유
 *
 * 고객사에 설치한 뒤 Notion 토큰을 바꾸려면 서버에 들어가 파일을 고치고 재시작해야 했다.
 * 셋업 마법사는 "데이터베이스 id 와 토큰을 넣으세요" 라고 말하는데 넣을 화면이 없었다.
 *
 * ## 세 가지를 절대 하지 않는다
 *
 * 1. **토큰을 다시 보여 주지 않는다.** 설정됨 여부와 연결 테스트 결과만 말한다.
 * 2. **못 하는 것을 되는 척하지 않는다.** 운영 서버의 웹 프로세스는 시크릿 디렉터리에
 *    쓸 수 없다(그것이 정상이다). 그때는 입력란 대신 무엇을 해야 하는지 보여 준다.
 * 3. **화면을 여는 것만으로 Notion 을 부르지 않는다.** Notion 은 초당 3요청 제한이 있어,
 *    열어 둔 탭이 몇 분마다 요청을 내면 정작 동기화가 밀린다. 실제 호출은 버튼에서만.
 *
 * ## 결과 어휘는 서버가 정한다
 *
 * 여기서 성공/실패를 다시 판정하지 않는다. 서버가 준 `result` 와 `message` 를 그대로 쓴다 -
 * 판정이 두 벌이 되면 한쪽만 고쳐지고, 그러면 화면과 진단이 다른 말을 하기 시작한다.
 */

// 결과 어휘 -> 배지 색. 문구는 서버가 준 것을 쓴다(여기서 다시 쓰지 않는다).
const RESULT_KIND = {
  ok: "ok",
  unset: "muted",
  token_missing: "warn",
  token_invalid: "error",
  database_not_found: "error",
  no_permission: "error",
  invalid_id: "error",
  rate_limited: "warn",
  unreachable: "error",
  failed: "error",
};

const RESULT_LABEL = {
  ok: "정상",
  unset: "설정 안 함",
  token_missing: "토큰 없음",
  token_invalid: "토큰 무효",
  database_not_found: "찾지 못함",
  no_permission: "권한 없음",
  invalid_id: "id 오류",
  rate_limited: "요청 제한",
  unreachable: "연결 실패",
  failed: "알 수 없음",
};

// SYS-10: app/notion_console/service.py의 스프린트 스펙 key(:71)와 같은 문자열.
const SPRINT_DB_KEY = "notion_sprint_database_id";
// 아래 "연결 테스트" 버튼의 실제 DOM 앵커 — 스프린트 진단 카드가 이 id로 스크롤+포커스한다.
const TEST_BUTTON_ID = "notion-test-button";

export function resultLabel(result) {
  return RESULT_LABEL[result] || "알 수 없음";
}

export function resultKind(result) {
  return RESULT_KIND[result] || "error";
}

function DatabaseRow({ item, testResult, onSave, onCreate, busy }) {
  const [value, setValue] = React.useState(item.value || "");
  React.useEffect(() => { setValue(item.value || ""); }, [item.value]);
  const dirty = (value || "") !== (item.value || "");
  return (
    <Box data-testid={"notion-db-" + item.key} sx={{ py: 1.5, borderTop: "1px solid", borderColor: "divider" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Typography sx={{ fontWeight: 700 }}>{item.label}</Typography>
        {/* SYS-11: 예전엔 이 칩 하나가 "설정됐는가"(상태)와 "어디서 왔는가"(출처)를 같은
            초록/주황 색으로 섞어서, 초록 "서버 환경변수"가 건강 판정처럼 잘못 읽혔다.
            TokenSection(아래)이 이미 쓰는 상태 어휘(설정됨/설정 안 함, ok/warn)와 통일하고,
            출처는 상태 의미가 없는 neutral(윤곽선) 칩으로 따로 낸다. */}
        <Badge value={item.configured ? "설정됨" : "설정 안 함"} kind={item.configured ? "ok" : "warn"} />
        {item.configured && (
          <Badge
            value={item.source === "settings" ? "화면에서 설정함" : "서버 환경변수"}
            kind="neutral"
          />
        )}
        {testResult && (
          <Badge value={resultLabel(testResult.result)} kind={resultKind(testResult.result)} />
        )}
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {item.used_for}
      </Typography>
      {!item.configured && (
        <Typography variant="body2" color="warning.main" sx={{ mt: 0.5 }}>
          {/* SYS-10: 스프린트 데이터베이스 미설정 경고는 이 줄과 아래 "스프린트 진단"
              카드가 같은 내용을 각자 다른 문장으로 두 번 말했다 — 여기는 짧은 이정표만
              남기고, 실제 설명은 진단 카드(더 나은 맥락을 가진 쪽) 한 곳에만 둔다. */}
          {item.key === SPRINT_DB_KEY
            ? "아래 “스프린트 진단” 카드를 확인하세요."
            : item.when_unset}
        </Typography>
      )}
      {testResult && testResult.result !== "ok" && testResult.result !== "unset" && (
        <Typography variant="body2" color="error.main" sx={{ mt: 0.5 }}>
          {testResult.message}
        </Typography>
      )}
      <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap", alignItems: "flex-start" }}>
        <TextField
          size="small"
          label="데이터베이스 id"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          inputProps={{ "aria-label": item.label + " 데이터베이스 id" }}
          sx={{ minWidth: 320, flex: 1 }}
          helperText="비우면 서버 환경변수 값을 그대로 씁니다."
        />
        <Button variant="primary" disabled={!dirty || busy} onClick={() => onSave(item.key, value.trim())}>
          저장
        </Button>
        {item.creatable && !item.configured && (
          <Button disabled={busy} onClick={() => onCreate(item)}>
            새로 만들기
          </Button>
        )}
      </Box>
      {!item.creatable && !item.configured && (
        // 사용자 지적: "새로운 DB 를 만들어주는 기능도있음?? ... 왜 다사라짐?" — 만들기
        // 버튼이 조용히 없으면 안 만들어 준 건지 고장인지 구별할 수 없다. 이 데이터베이스는
        // 설계상(app/notion_console/service.py 의 kind="") 자동 생성 대상이 아니라는 것을
        // 말로 남긴다.
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
          이 데이터베이스는 화면에서 자동으로 만들 수 없습니다. 기존 Notion 데이터베이스의 id를 위 칸에 직접 입력해 연결하세요.
        </Typography>
      )}
    </Box>
  );
}

function TokenSection({ token, testTokens, onSave, busy }) {
  const [field, setField] = React.useState("");
  const [value, setValue] = React.useState("");
  const byField = {};
  (testTokens || []).forEach((t) => { byField[t.field] = t; });
  return (
    <Card sx={{ mt: 2, p: 2 }}>
      <Typography variant="h6" sx={{ mb: 1 }}>토큰</Typography>
      <Typography variant="body2" color="text.secondary">{token.note}</Typography>
      {token.items.map((item) => (
        <Box
          key={item.field}
          data-testid={"notion-token-" + item.field}
          sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1.5, flexWrap: "wrap" }}
        >
          <Typography sx={{ minWidth: 180 }}>{item.label}</Typography>
          <Badge value={item.configured ? "설정됨" : "설정 안 함"} kind={item.configured ? "ok" : "warn"} />
          {byField[item.field] && (
            <Badge
              value={resultLabel(byField[item.field].result)}
              kind={resultKind(byField[item.field].result)}
            />
          )}
          {byField[item.field] && byField[item.field].integration_name && (
            <Typography variant="body2" color="text.secondary">
              통합 이름: {byField[item.field].integration_name}
            </Typography>
          )}
          <Box sx={{ flex: 1 }} />
          {token.writable && (
            <Button size="small" disabled={busy} onClick={() => { setField(item.field); setValue(""); }}>
              {item.configured ? "교체" : "입력"}
            </Button>
          )}
        </Box>
      ))}

      {!token.writable && (
        <Callout tone="warn">
          {token.manual_instruction}
        </Callout>
      )}

      {token.writable && field && (
        <Box sx={{ mt: 2, display: "flex", gap: 1, flexWrap: "wrap", alignItems: "flex-start" }}>
          <TextField
            size="small"
            type="password"
            label="새 토큰"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            inputProps={{ "aria-label": "새 토큰" }}
            sx={{ minWidth: 320, flex: 1 }}
            helperText="저장한 뒤에는 다시 보여 주지 않습니다."
          />
          <Button
            variant="primary"
            disabled={!value.trim() || busy}
            onClick={() => { onSave(field, value.trim()); setField(""); setValue(""); }}
          >
            저장
          </Button>
          <Button disabled={busy} onClick={() => { setField(""); setValue(""); }}>취소</Button>
        </Box>
      )}
    </Card>
  );
}

export function NotionConsole() {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [test, setTest] = React.useState(null);
  // 부모 페이지 id 를 받는 중인 항목. null 이면 새로 만들기 다이얼로그가 닫혀 있다.
  const [creatingItem, setCreatingItem] = React.useState(null);

  const state = useQuery({
    queryKey: ["notion-console"],
    queryFn: () => api("/api/admin/notion"),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["notion-console"] });
    // 설정 화면과 진단이 같은 값을 그린다. 한쪽만 새로 읽으면 두 화면이 다른 말을 한다.
    qc.invalidateQueries({ queryKey: ["settings"] });
  };

  const saveId = useMutation({
    mutationFn: ({ key, value }) =>
      api("/api/admin/settings/" + key, { method: "PUT", body: { value } }),
    onSuccess: () => {
      invalidate();
      toast("저장했습니다. " + (state.data ? state.data.apply_note : ""), "success");
    },
    onError: (err) => toast((err && err.message) || "저장하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error"),
  });

  const saveToken = useMutation({
    mutationFn: ({ field, value }) =>
      api("/api/admin/notion/token", { method: "POST", body: { field, value } }),
    onSuccess: () => {
      invalidate();
      setTest(null);
      toast("토큰을 저장했습니다. 연결 테스트로 확인해 주세요.", "success");
    },
    onError: (err) => toast((err && err.message) || "토큰을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error"),
  });

  const runTest = useMutation({
    mutationFn: () => api("/api/admin/notion/test", { method: "POST", body: {} }),
    onSuccess: (result) => {
      setTest(result);
      toast(
        result.ok ? "연결에 성공했습니다." : "확인하지 못한 항목이 있습니다.",
        result.ok ? "success" : "error"
      );
    },
    onError: (err) => toast((err && err.message) || "연결 테스트를 하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error"),
  });

  const createDb = useMutation({
    mutationFn: (body) => api("/api/admin/notion/databases", { method: "POST", body }),
    onSuccess: (result) => {
      invalidate();
      toast(result.message || "", result.created ? "success" : "error");
    },
    onError: (err) => toast((err && err.message) || "만들지 못했습니다. 잠시 후 다시 시도해 주세요.", "error"),
  });

  if (state.isLoading) return <Skeleton lines={8} />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.refetch} />;

  const data = state.data || {};
  const busy = saveId.isPending || saveToken.isPending || runTest.isPending || createDb.isPending;
  const testByKey = {};
  ((test && test.databases) || []).forEach((d) => { testByKey[d.key] = d; });

  // 스타일 없는 브라우저 네이티브 팝업(window.prompt) 대신 테마 폼 다이얼로그로 부모 페이지
  // id 를 받는다 - 아래 FormModal 이 그 입력을 담당한다.
  const onCreate = (item) => setCreatingItem(item);

  const submitCreateDb = async (values) => {
    const item = creatingItem;
    const ok = await confirm(
      "노션에 실제로 데이터베이스가 생깁니다. 되돌리려면 노션에서 직접 지워야 합니다.",
      { title: item.label + " 를 새로 만들까요?", confirmLabel: "만들기" },
    );
    if (!ok) return;
    try {
      await createDb.mutateAsync({
        key: item.key,
        parent_page_id: values.parent_page_id.trim(),
        title: item.label,
        confirm: true,
      });
    } catch (e) {
      // createDb 의 onError 가 이미 토스트로 알린다 - 다이얼로그는 열어 둔다(재시도 가능하게).
      return;
    }
    setCreatingItem(null);
  };

  return (
    <Box className="c-screen">
      <PageHeader area="연동" title="Notion 관리" />

      <Callout tone="info">{data.apply_note}</Callout>

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6">데이터베이스</Typography>
        {(data.databases || []).map((item) => (
          <DatabaseRow
            key={item.key}
            item={item}
            testResult={testByKey[item.key]}
            busy={busy}
            onSave={(key, value) => saveId.mutate({ key, value })}
            onCreate={onCreate}
          />
        ))}
      </Card>

      <FormModal
        open={!!creatingItem}
        title={(creatingItem ? creatingItem.label : "") + " 새로 만들기"}
        fields={[
          {
            name: "parent_page_id",
            label: "부모 페이지 id",
            required: true,
            help: "새 데이터베이스를 넣을 노션 페이지의 id 입니다. 그 페이지를 미리 노션 통합에 공유해 두어야 합니다.",
          },
        ]}
        submitLabel="계속"
        onSubmit={submitCreateDb}
        onClose={() => setCreatingItem(null)}
      />

      <TokenSection
        token={data.token || { items: [], writable: false }}
        testTokens={test && test.tokens}
        busy={busy}
        onSave={(field, value) => saveToken.mutate({ field, value })}
      />

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>연결 테스트</Typography>
        <Typography variant="body2" color="text.secondary">
          토큰과 데이터베이스를 실제로 한 번씩 불러 봅니다. 결과는 누른 그 순간의 사실이며,
          여기서 성공해도 다음 동기화가 반드시 성공한다는 뜻은 아닙니다.
        </Typography>
        <Box sx={{ mt: 1.5 }}>
          <Button id={TEST_BUTTON_ID} variant="primary" disabled={busy} onClick={() => runTest.mutate()}>
            {runTest.isPending ? "확인하는 중" : "연결 테스트"}
          </Button>
        </Box>
        {test && (
          <Box data-testid="notion-test-result" sx={{ mt: 2, display: "grid", gap: 0.75 }}>
            {test.tokens.map((t) => (
              <Typography key={t.field} variant="body2">
                {t.label}: {resultLabel(t.result)}. {t.message}
              </Typography>
            ))}
            {test.databases.map((d) => (
              <Typography key={d.key} variant="body2">
                {d.label}: {resultLabel(d.result)}. {d.message}
              </Typography>
            ))}
          </Box>
        )}
      </Card>

      <Card sx={{ mt: 2, p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>스프린트 진단</Typography>
        <Typography variant="body2" color="text.secondary">
          {data.sprint && data.sprint.portal_window}
        </Typography>
        <Callout tone={data.sprint && data.sprint.linked ? "info" : "warn"}>
          {data.sprint && data.sprint.finding}
        </Callout>
        <Typography variant="body2" sx={{ mt: 1 }}>
          {data.sprint && data.sprint.next_step}{" "}
          {/* SYS-10: 예전엔 이 문구가 위 "연결 테스트" 버튼을 텍스트로만 가리켜서 실제로
              누를 수 있는 대상이 아니었다 — 그 버튼으로 스크롤+포커스하는 링크로 바꾼다. */}
          <Typography
            component="a"
            href={"#" + TEST_BUTTON_ID}
            variant="body2"
            sx={{ color: "primary.dark", textDecoration: "underline", cursor: "pointer" }}
            onClick={(e) => {
              e.preventDefault();
              const el = document.getElementById(TEST_BUTTON_ID);
              if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "center" });
                el.focus();
              }
            }}
          >
            연결 테스트 버튼으로 이동
          </Typography>
        </Typography>
      </Card>
    </Box>
  );
}

export default NotionConsole;
