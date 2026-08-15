import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { BodyEditor, BodyPreview, BODY_MAX_LINES, editorContainerSx, editorSurfaceWidthSx } from "./BodyEditor.jsx";
import { Button, Callout, useConfirm, useToast } from "./kit.jsx";
import { FONT_SIZE, PROSE_MAX_WIDTH } from "./theme.js";

/* 편집 중인 표면(제목 행 + 안내문 + BodyEditor)의 컨테이너 질의 이름. 이 화면 전용 지역
 * 값이라 상수로 뽑는다 — editorSurfaceWidthSx 가 만드는 `@container` 규칙과
 * editorContainerSx 가 여는 조상이 같은 이름을 봐야 한다(BodyEditor.jsx 주석 참고). */
const EDIT_SURFACE_CONTAINER = "editable-body-edit";

/* 본문 읽기, 편집 패널 (티켓 본문과 문서 본문이 **같은 컴포넌트**를 쓴다).
 *
 * 처음에는 티켓에만 있었다(TicketBody.jsx). 문서 편집을 붙이면서 그대로 복사할 뻔했는데,
 * 이 패널이 다루는 것은 화면 장식이 아니라 **조용히 틀리면 가장 비싼 상태 세 가지**다:
 *
 * 1) **"저장은 됐지만 원본과 어긋남"을 성공으로 보고하지 않는다.** 서버는 정본(우리 DB)을
 *    먼저 쓰고 그다음 원본(Notion)에 민다. 그래서 원본이 죽어도 사용자 글은 살아남지만,
 *    그 상태를 "저장했습니다"로만 알리면 사용자는 원본이 갱신된 줄 알고 회의에 들어간다.
 *    응답의 synced:false 와 상세의 body_sync_error 가 화면에 보여야 한다.
 * 2) **본문을 못 읽은 상태에서는 편집을 열지 않는다.** 빈 편집기로 저장하면 그게 곧 본문
 *    삭제다. 되돌릴 수 없는 종류의 실수다.
 * 3) **편집을 시작할 때 받은 지문(base_version)을 저장에 실어 보낸다.** 안 보내면 그 사이
 *    먼저 저장한 사람의 글을 통째로 지우고 양쪽 다 성공 토스트를 본다.
 *
 * 이걸 두 벌로 두면 한쪽에서 고친 버그가 다른 쪽에 남는다. 이 저장소가 서버 쪽에서 반복해
 * 적어 온 그 이유("판정을 두 벌로 적지 않는다")가 화면에도 똑같이 적용된다.
 *
 * 소스 본문 렌더러(DocBody)는 **prop 으로 받는다**. 여기서 직접 import 하면 화면 모듈과
 * 순환 import 가 된다(TeamDoc.jsx 가 이 파일을 쓴다). 폭 상한도 화면마다 달라서 그쪽이
 * 정하는 편이 맞다.
 *
 * 폭: 본문은 산문이라 78ch 에서 멈춘다. 4K 에서 남는 폭은 줄 길이가 아니라 옆 레일로 간다. */

export function lineCount(text) {
  return (text || "").split("\n").length;
}

/* 원본에 우리가 마크다운으로 표현할 수 없는 블록(이미지, 표, 컬럼…)이 있는가.
 * 2026-08 이전에는 저장이 그 블록을 지웠고 이 값은 '경고'용이었다. 지금은 지우지 않으므로
 * '위치가 앞으로 모인다'는 안내용이다 — 사라진다고 말하면 안 된다(사실이 아니다). */
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

export function EditableBody({
  editorId, endpoint, invalidateKeys = [], heading = "본문", placeholder,
  blocks, bodyMarkdown, bodyVersion, bodyIsLocal, bodySyncError, sourceView, onSaved,
}) {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(bodyMarkdown || "");
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
    setDraft(bodyMarkdown || "");
    setEditBaseVersion(bodyVersion);
  }, [editorId, bodyMarkdown, bodyVersion]);

  // 본문을 읽지 못했으면(blocks 실패) bodyMarkdown 은 null 이다. 그 상태로 편집기를 열면
  // 빈 칸이 뜨고, 저장이 곧 본문 삭제가 된다. 그래서 편집 자체를 막는다.
  const canEdit = bodyMarkdown != null;
  const tooManyLines = lineCount(draft) > BODY_MAX_LINES;
  const lossy = hasUnsupportedBlocks(blocks);
  const nested = hasNestedBlocks(blocks);

  const save = useMutation({
    mutationFn: ({ body, baseVersion }) => api(endpoint, {
      /* 편집을 시작할 때 받은 지문을 함께 보낸다. 그 사이 누가 먼저 저장했으면 서버가
         409 로 막는다 — 예전에는 조건 없이 덮어써서 **앞사람 글이 통째로 사라지고
         양쪽 다 성공 토스트를 봤다.** 호출부가 넘기는 baseVersion 을 그대로 쓴다(위
         editBaseVersion 주석 참고) — 여기서 다시 prop(bodyVersion)을 읽으면 편집 중
         갱신된 최신값이 섞여 이 보호 장치가 무력화된다. */
      method: "PUT", body: { body_markdown: body, base_version: baseVersion },
    }),
    onSuccess: (res) => {
      setEditing(false);
      invalidateKeys.forEach((key) => qc.invalidateQueries({ queryKey: key, refetchType: "all" }));
      if (res && res.synced === false) {
        // 절반의 성공을 성공으로 보고하지 않는다.
        toast("본문은 저장했지만 원본(Notion) 반영에 실패했습니다. 아래에서 다시 시도할 수 있습니다.", "error");
      } else {
        toast("본문을 저장했습니다.", "success");
      }
      if (onSaved) onSaved();
    },
    onError: (e) => toast((e && e.message) || "본문을 저장하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const startEditing = () => { setDraft(bodyMarkdown || ""); setEditBaseVersion(bodyVersion); setEditing(true); };
  const cancel = async () => {
    if (draft !== (bodyMarkdown || "")) {
      const ok = await confirm("수정한 내용을 버립니다. 계속할까요?", { title: "수정 취소", confirmLabel: "버리기", danger: true });
      if (!ok) return;
    }
    setEditing(false);
  };

  if (editing) {
    /* 폭: 읽기 모드(아래 non-editing return)는 산문이라 PROSE_MAX_WIDTH(78ch)에서 멈추는 게
     * 맞다. 그런데 예전엔 편집 모드도 같은 78ch 로 묶었다 — 편집 표면은 툴바+입력 상자+
     * 미리보기라 산문이 아니고, BodyEditor 안의 TextField 는 애초에 fullWidth 로 설계돼 있다
     * (BodyEditor.jsx 의 BodyPreview wide 설명 참고). 그 결과 4K 등 넓은 화면에서 편집기 전체가
     * 좁은 고정 폭에 갇혀 왼쪽으로 쏠려 보였다. `editorContainerSx`/`editorSurfaceWidthSx` 는
     * 컨테이너의 실제 폭을 재서, 충분히 넓어졌을 때만(EDITOR_WIDE_STOP_REM) 상한을 건다. */
    return (
      <Box sx={editorContainerSx(EDIT_SURFACE_CONTAINER)}>
        <Box sx={editorSurfaceWidthSx(EDIT_SURFACE_CONTAINER)}>
          <Stack direction="row" gap={1} sx={{ alignItems: "center", mb: 1.5, flexWrap: "wrap" }}>
            <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, flex: 1 }}>{heading} 수정</Typography>
            <Button size="sm" onClick={cancel} disabled={save.isPending}>취소</Button>
            <Button size="sm" variant="primary" disabled={save.isPending || tooManyLines}
              onClick={() => save.mutate({ body: draft, baseVersion: editBaseVersion })}>
              {save.isPending ? "저장 중…" : "저장"}
            </Button>
          </Stack>
          {/* 아직 우리 정본이 없는 본문(=원본에서 읽어온 근사치)을 여기서 저장하면 평문만 남는다.
              정본이 생긴 뒤에는 저장이 무손실이라 경고하지 않는다 — 늘 경고하면 아무도 안 읽는다. */}
          {/* 2026-08: 저장이 더 이상 이미지·표를 지우지 않는다(notion_write.py 의
              replace_page_body, team_docs 쪽은 notion_docs.py). 그래서 "사라집니다"라는 옛 경고를
              실제 동작에 맞춰 고쳤다 — 틀린 경고는 안 읽히는 데서 끝나지 않고, 되는 일을
              안 된다고 믿게 만든다. */}
          {!bodyIsLocal ? (
            <Box sx={{ mb: 1.5 }}>
              <Callout tone="warn">
                이 본문은 원본(Notion)에서 읽어온 것입니다. 여기서 저장하면 굵게, 링크 같은 인라인
                서식은 사라지고 글자만 남습니다. 서식을 지키려면 ‘원본 열기’에서 수정하세요.
              </Callout>
            </Box>
          ) : null}
          {lossy ? (
            <Box sx={{ mb: 1.5 }}>
              <Callout tone="info">
                원본에 이 편집기가 다루지 않는 블록(이미지, 표 등)이 있습니다. 저장해도
                그 블록은 지워지지 않습니다. 다만 원본에서의 위치는 글 앞쪽으로 모입니다.
              </Callout>
            </Box>
          ) : null}
          {nested ? (
            <Box sx={{ mb: 1.5 }}>
              <Callout tone="info">
                원본에 접히거나 중첩된 내용(토글 속 글, 여러 단계 목록 등)을 담은 블록이
                있습니다. 이 편집기에는 그 안쪽 내용까지는 실리지 않아, 저장해도 그 블록은
                지우지 않고 그대로 둡니다. 다만 여기서 같은 줄을 고쳐 저장하면 원본에는
                고치기 전 원래 블록과 고친 내용이 둘 다 남아 겹쳐 보일 수 있습니다. 온전히
                수정하려면 ‘원본 열기’를 이용하세요.
              </Callout>
            </Box>
          ) : null}
          {tooManyLines ? (
            <Box sx={{ mb: 1.5 }}>
              <Callout tone="danger">
                본문은 최대 {BODY_MAX_LINES}줄까지 저장할 수 있습니다(현재 {lineCount(draft)}줄).
                줄 수를 줄여야 저장할 수 있습니다.
              </Callout>
            </Box>
          ) : null}
          {/* 이름은 바로 위 heading 과 같은 말로 준다. 이 자리에는 화면에 보이는 <label> 이
              없어서, 주지 않으면 스크린리더가 "편집" 이라고만 읽는다 — 티켓 본문인지 문서
              본문인지 알 수 없다. heading 을 따라가므로 문구가 두 벌로 갈리지 않는다. */}
          <BodyEditor id={editorId} value={draft} onChange={setDraft} rows={14}
            label={heading + " 수정"}
            placeholder={placeholder || "본문을 입력하세요. 제목, 글머리, 번호, 구분선을 쓸 수 있습니다."} />
        </Box>
      </Box>
    );
  }

  return (
    <Box>
      <Stack direction="row" gap={1} sx={{ alignItems: "center", mb: 1.5, flexWrap: "wrap" }}>
        <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, flex: 1 }}>{heading}</Typography>
        <Button size="sm" onClick={startEditing} disabled={!canEdit}>{heading} 수정</Button>
      </Stack>
      {!canEdit ? (
        <Box sx={{ mb: 1.5, maxWidth: PROSE_MAX_WIDTH }}>
          <Callout tone="warn">
            본문을 불러오지 못해 수정할 수 없습니다. 지금 저장하면 원본 본문을 지우게 되므로
            수정을 막았습니다. 새로고침하거나 ‘원본 열기’에서 수정하세요.
          </Callout>
        </Box>
      ) : null}
      {bodySyncError ? (
        <Box sx={{ mb: 1.5, maxWidth: PROSE_MAX_WIDTH }}>
          <Callout tone="warn">
            <Box sx={{ display: "grid", gap: 1 }}>
              <span>
                본문은 저장되었지만 원본(Notion)에 반영하지 못했습니다: {bodySyncError}.
                아래 내용이 우리 쪽 정본이며, 원본에는 아직 이전 내용이 남아 있습니다.
              </span>
              <Box>
                {/* 정본이 없으면 재시도가 곧 '빈 본문 밀어넣기'가 된다. 여기서는 논리상
                    일어날 수 없지만(sync 오류는 정본 저장 뒤에만 생긴다) 막아 둔다. */}
                <Button size="sm" disabled={save.isPending || bodyMarkdown == null}
                  onClick={() => save.mutate({ body: bodyMarkdown, baseVersion: bodyVersion })}>
                  {save.isPending ? "동기화 중…" : "원본에 다시 반영"}
                </Button>
              </Box>
            </Box>
          </Callout>
        </Box>
      ) : null}
      {bodySyncError ? (
        /* 원본 블록은 낡았다는 걸 이미 안다 — 우리 정본을 그린다. */
        <BodyPreview text={bodyMarkdown} />
      ) : (
        sourceView
      )}
    </Box>
  );
}
