import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { editorContainerSx, editorSurfaceWidthSx } from "./BodyEditor.jsx";
import { Button, Callout, Skeleton, useConfirm, useToast } from "./kit.jsx";
import { FONT_SIZE } from "./theme.js";

/* 편집기는 **지연 로드**한다. TipTap 과 그 확장 열두 개는 진입 번들에 넣을 것이 아니고,
 * `ui/block-editor-lazy.test.jsx` 가 정적 import 를 소스 전체에서 금지한다. */
const BlockEditor = React.lazy(() =>
  import("./BlockEditor.jsx").then((m) => ({ default: m.BlockEditor })),
);

/* 편집 중인 표면(제목 행 + 안내문 + BodyEditor)의 컨테이너 질의 이름. 이 화면 전용 지역
 * 값이라 상수로 뽑는다 — editorSurfaceWidthSx 가 만드는 `@container` 규칙과
 * editorContainerSx 가 여는 조상이 같은 이름을 봐야 한다(BodyEditor.jsx 주석 참고). */
const EDIT_SURFACE_CONTAINER = "editable-body-edit";

/* 본문 읽기, 편집 패널 (티켓 본문과 문서 본문이 **같은 컴포넌트**를 쓴다).
 *
 * 처음에는 티켓에만 있었다(TicketBody.jsx). 문서 편집을 붙이면서 그대로 복사할 뻔했는데,
 * 이 패널이 다루는 것은 화면 장식이 아니라 **조용히 틀리면 가장 비싼 상태 두 가지**다:
 *
 * 1) **본문을 못 읽은 상태에서는 편집을 열지 않는다.** 빈 편집기로 저장하면 그게 곧 본문
 *    삭제다. 되돌릴 수 없는 종류의 실수다.
 * 2) **편집을 시작할 때 받은 지문(base_version)을 저장에 실어 보낸다.** 안 보내면 그 사이
 *    먼저 저장한 사람의 글을 통째로 지우고 양쪽 다 성공 토스트를 본다.
 *
 * 여기 세 번째가 있었다: "저장은 됐지만 원본(Notion)과 어긋남"을 성공으로 보고하지 않는
 * 것. 그 상태는 정본이 두 곳에 있을 때만 존재했고, 정본이 이 서버 하나가 된 뒤로는 밀어
 * 넣을 원본이 없어 어긋날 짝이 없다. 서버도 응답에서 synced 와 body_sync_error 를 걷었다.
 *
 * 이걸 두 벌로 두면 한쪽에서 고친 버그가 다른 쪽에 남는다. 이 저장소가 서버 쪽에서 반복해
 * 적어 온 그 이유("판정을 두 벌로 적지 않는다")가 화면에도 똑같이 적용된다.
 *
 * 소스 본문 렌더러(DocBody)는 **prop 으로 받는다**. 여기서 직접 import 하면 화면 모듈과
 * 순환 import 가 된다. 폭은 담는 열이 정한다 — 여기에 72ch 를 다시 걸면 열은 넓은데
 * 글만 왼쪽에 붙는다. */

/** 남은 소비처(시험)를 위한 헬퍼. 본문에는 이제 줄 상한이 없다 — 문서 본문과 같은 정본을
 * 쓰고, 그쪽에는 애초에 상한이 없었다. */
export function lineCount(text) {
  return (text || "").split("\n").length;
}

/* 본문에 이 편집기가 마크다운으로 표현할 수 없는 블록(이미지, 표, 컬럼…)이 있는가.
 * 저장이 그 블록을 지우지는 않는다 — 사라진다고 말하면 안 된다(사실이 아니다). */
export function hasUnsupportedBlocks(blocks) {
  return (blocks || []).some((b) => b && b.kind === "unsupported");
}

/* H-1: 이 블록들은 kind 로는 우리가 표현할 수 있는 타입(문단·글머리 목록·토글…)이지만
 * **자식이 있다**(접힌 토글 속 글, 중첩 목록). 본문 조회가 1레벨만 읽으므로 그 자식은 이
 * blocks 배열에 애초에 없다 — 서버(replace_page_body)는 그 사실을 알고 이 블록을 지우지
 * 않지만(이미지·표와 같은 취급), 화면에서 보기엔 평범한 문단처럼 보여 사용자가 그 사실을
 * 모른 채 저장을 누를 수 있다. hasUnsupportedBlocks 와 같은 이유로, 같은 시점에 미리 알린다. */
export function hasNestedBlocks(blocks) {
  return (blocks || []).some((b) => b && b.has_children);
}

/** 두 문서가 **같은 내용인가**. 저장 안 하고 나갈 때 물어볼지 정하는 데만 쓴다.
 *
 * 문자열 비교로 충분하다 — 편집기가 내는 문서는 키 순서가 안정적이고, 여기서 틀려도
 * 최악은 「안 바꿨는데 확인창이 뜬다」이지 글이 사라지는 것이 아니다. */
function sameDoc(a, b) {
  try {
    return JSON.stringify(a || null) === JSON.stringify(b || null);
  } catch {
    return false;
  }
}

export function EditableBody({
  editorId, endpoint, invalidateKeys = [], heading = "본문", placeholder,
  blocks, bodyDoc, bodyMarkdown, bodyVersion, sourceView, onSaved, onPickImage,
  // VIS-135: 화면에 이 버튼과 경쟁하는 다른 "수정" 입구가 따로 있을 때만(현재는 Ticket.jsx)
  // 그 차이를 밝히는 툴팁을 준다. TeamDoc.jsx처럼 경쟁하는 입구가 없는 소비처는 안 줘도
  // 되므로 기본값 없음 — 없는 문제를 있다고 말하면 안 된다.
  editButtonHint,
}) {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(false);
  /* 초안은 **문서**다. 예전에는 마크다운 문자열이었고, 그래서 이 편집기에는 굵게·표·
     이미지를 담을 자리가 없었다 — 문서 본문과 같은 정본을 쓰면서 그 벽이 없어졌다. */
  const [draft, setDraft] = React.useState(bodyDoc || null);
  // 저장에 실어 보낼 지문(base_version)도 draft 처럼 "편집을 시작한 시점" 값으로 얼려 둔다.
  // bodyVersion 은 부모가 주는 prop이라, 편집 중(예: 같은 티켓의 첨부를 올려 상세가
  // 재조회되는 동안) 다른 사람이 먼저 저장해 값이 바뀌면 저장 시점의 mutationFn 클로저는
  // **그 새 값**을 그대로 읽는다 — 하필 충돌을 감지해야 할 바로 그 순간에 "지금 서버 값과
  // 내가 보낼 값이 같냐"는 서버 검사를 그대로 통과시켜, 이 사용자의 옛 초안이 방금 저장된
  // 남의 글을 조용히 덮어쓴다(editable-body-stale-base-version.test.jsx 가 이 결함을 고정한다).
  const [editBaseVersion, setEditBaseVersion] = React.useState(bodyVersion);

  /* editorId 가 바뀌면 **다른 문서로 자리가 바뀐 것**이다(호출부가 "ticket-body-<id>"/
   * "doc-body-<id>" 처럼 문서 정체성을 그대로 실어 보낸다). `screens/Ticket.jsx` 는
   * `<Route path="/tickets/:id">` 하나에 붙어 있어 react-router 가 `:id` 만 바뀌어도 이
   * 컴포넌트를 다시 만들지 않는다 — 그 새 문서가 이미 캐시돼 있으면(알림 벨·검색 결과·뒤로가기로
   * 예전에 열어 본 문서) 로딩 화면 없이 곧바로 새 props 가 온다. 그 사이 이 컴포넌트는 한 번도
   * 언마운트되지 않으므로, 편집 중이던 이전 문서의 `editing`/`draft`/`editBaseVersion` 이 그대로
   * 남는다 — '저장'을 누르면 **이전 문서에서 쓰던 글이 새 문서의 엔드포인트로** 나간다(남의 문서를
   * 조용히 덮어쓰는 데이터 손상). 위 base_version 동결과는 다른 문제다: 그건 같은 문서를 계속
   * 보는 동안의 보호이고, 이건 문서 자체가 바뀌었을 때 남은 편집 상태를 버리는 것이다. */
  const editorIdRef = React.useRef(editorId);
  React.useEffect(() => {
    if (editorIdRef.current === editorId) return;
    editorIdRef.current = editorId;
    setEditing(false);
    setDraft(bodyDoc || null);
    setEditBaseVersion(bodyVersion);
  }, [editorId, bodyDoc, bodyVersion]);

  // 본문을 읽지 못했으면(blocks 실패) bodyDoc 은 null 이다. 그 상태로 편집기를 열면
  // 빈 칸이 뜨고, 저장이 곧 본문 삭제가 된다. 그래서 편집 자체를 막는다.
  const canEdit = bodyDoc != null;

  const save = useMutation({
    mutationFn: ({ body, baseVersion }) => api(endpoint, {
      /* 편집을 시작할 때 받은 지문을 함께 보낸다. 그 사이 누가 먼저 저장했으면 서버가
         409 로 막는다 — 예전에는 조건 없이 덮어써서 **앞사람 글이 통째로 사라지고
         양쪽 다 성공 토스트를 봤다.** 호출부가 넘기는 baseVersion 을 그대로 쓴다(위
         editBaseVersion 주석 참고) — 여기서 다시 prop(bodyVersion)을 읽으면 편집 중
         갱신된 최신값이 섞여 이 보호 장치가 무력화된다. */
      /* 정본을 보낸다. 서버가 이 문서에서 마크다운과 평문을 파생시켜 함께 저장하므로
         (검색·AI 문맥이 그 값을 읽는다) 화면이 두 벌을 만들 필요가 없다. */
      method: "PUT", body: { body, base_version: baseVersion },
    }),
    onSuccess: () => {
      setEditing(false);
      invalidateKeys.forEach((key) => qc.invalidateQueries({ queryKey: key, refetchType: "all" }));
      /* 여기 「저장은 됐지만 원본 반영에 실패했습니다」 갈래가 있었다. 밀어 넣을 원본이
         없어졌으므로 서버가 그 상태를 만들 수 없고, 응답에서 synced 도 걷었다. */
      toast("본문을 저장했습니다.", "success");
      if (onSaved) onSaved();
    },
    onError: (e) => toast((e && e.message) || "본문을 저장하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const startEditing = () => { setDraft(bodyDoc || null); setEditBaseVersion(bodyVersion); setEditing(true); };
  const cancel = async () => {
    if (!sameDoc(draft, bodyDoc)) {
      const ok = await confirm("수정한 내용을 버립니다. 계속할까요?", { title: "수정 취소", confirmLabel: "버리기", danger: true });
      if (!ok) return;
    }
    setEditing(false);
  };

  if (editing) {
    /* 폭: 읽기 모드도 담는 열을 그대로 쓴다. 예전엔 편집 모드를 78ch 로 묶어서, 편집 표면
     * (툴바+입력 상자+미리보기)이 좁은 고정 폭에 갇혀 왼쪽으로 쏠려 보였다. BodyEditor 안의
     * TextField 는 애초에 fullWidth 다. `editorContainerSx`/`editorSurfaceWidthSx` 는
     * 컨테이너의 실제 폭을 재서, 충분히 넓어졌을 때만(EDITOR_WIDE_STOP_REM) 상한을 건다. */
    return (
      <Box sx={editorContainerSx(EDIT_SURFACE_CONTAINER)}>
        <Box sx={editorSurfaceWidthSx(EDIT_SURFACE_CONTAINER)}>
          <Stack direction="row" gap={1} sx={{ alignItems: "center", mb: 1.5, flexWrap: "wrap" }}>
            <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, flex: 1 }}>{heading} 수정</Typography>
            <Button size="sm" onClick={cancel} disabled={save.isPending}>취소</Button>
            <Button size="sm" variant="primary" disabled={save.isPending}
              onClick={() => save.mutate({ body: draft, baseVersion: editBaseVersion })}>
              {save.isPending ? "저장 중…" : "저장"}
            </Button>
          </Stack>
          {/* 여기 「이 본문은 원본(Notion)에서 읽어온 것입니다 … '원본 열기'에서
              수정하세요」 경고가 있었다. body_is_local 이 거짓일 때 떴는데, 이관해 온
              문서 110건이 전부 그 상태라 전 건에서 떴다. 밀어 넣을 원본이 없고 저장은
              무손실이므로 그 경고는 사실이 아니었고, 가리키던 그 버튼도 이제 없다. 서버도 응답에서 body_is_local 을 걷었다. */}
          {/* 🔴 여기 경고가 셋 있었다 — 「이 편집기가 다루지 않는 블록이 있다」,
              「접힌 내용은 안 실린다」, 「N줄을 넘으면 저장할 수 없다」. 셋 다 **본문
              정본이 마크다운이던 시절의 사실**이었다. 지금은 문서 본문과 같은 정본을
              같은 편집기로 고치므로 표·이미지·중첩 목록이 그대로 실리고 줄 상한도 없다.
              사실이 아닌 경고를 남겨 두면 사용자는 안 일어나는 손실을 매번 걱정한다. */}
          {/* 이름은 바로 위 heading 과 같은 말로 준다. 이 자리에는 화면에 보이는 <label> 이
              없어서, 주지 않으면 스크린리더가 "편집" 이라고만 읽는다 — 티켓 본문인지 문서
              본문인지 알 수 없다. heading 을 따라가므로 문구가 두 벌로 갈리지 않는다. */}
          {/* 미리보기를 **여기서만** 켠다 — 이미 있는 긴 본문을 고치는 자리라 무엇을 쳤는지와
              어떻게 보일지를 나란히 대조하는 것이 실제로 일이다. 새로 쓰는 자리(새 티켓 폼)는
              끄고 폼을 짧게 둔다(`ui/BodyEditor.jsx` 의 `preview`). */}
          <React.Suspense fallback={<Skeleton kind="section" lines={6} />}>
            {/* 이름은 바로 위 제목과 같은 말로 준다 — 이 자리에는 화면에 보이는 `<label>`
                이 없어서, 안 주면 스크린리더가 「편집」이라고만 읽는다. */}
            <BlockEditor
              value={draft}
              onChange={setDraft}
              onPickImage={onPickImage}
              label={heading}
              ariaLabel={heading + " 수정"}
            />
          </React.Suspense>
        </Box>
      </Box>
    );
  }

  return (
    <Box>
      <Stack direction="row" gap={1} sx={{ alignItems: "center", mb: 1.5, flexWrap: "wrap" }}>
        <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, flex: 1 }}>{heading}</Typography>
        {/* canEdit이 false일 땐 버튼이 disabled라 MUI Tooltip이 그 위에서 마우스 이벤트를
            못 받는다(MUI 자체 경고) — 그리고 바로 아래 Callout이 "왜 못 고치는지"를 이미
            말하고 있어 이 시점엔 안내가 중복이다. 고칠 수 있을 때만 감싼다. */}
        {editButtonHint && canEdit ? (
          <Tooltip describeChild title={editButtonHint}>
            <Button size="sm" onClick={startEditing} disabled={!canEdit}>{heading} 수정</Button>
          </Tooltip>
        ) : (
          <Button size="sm" onClick={startEditing} disabled={!canEdit}>{heading} 수정</Button>
        )}
      </Stack>
      {!canEdit ? (
        <Box sx={{ mb: 1.5 }}>
          <Callout tone="danger">
            본문을 불러오지 못해 수정할 수 없습니다. 지금 저장하면 저장된 본문을 지우게
            되므로 수정을 막았습니다. 잠시 후 새로고침해 주세요.
          </Callout>
        </Box>
      ) : null}
      {/* 여기 「본문은 저장되었지만 원본(Notion)에 반영하지 못했습니다」 배너와
          「원본에 다시 반영」 버튼(누르는 동안 「동기화 중…」)이 있었다. 밀어 넣을
          원본이 없어졌으므로 그 상태를 만들 방법이 없고, 서버도 응답에서
          body_sync_error 를 걷었다. 그래서 본문은 언제나 소스 렌더러로 그린다. */}
      {sourceView}
    </Box>
  );
}
