"""결과 블록의 다음 쪽 — 「10건 더 보기」 · 정렬 바꾸기 (AI 채팅 개선 회차).

답 아래 블록(`blocks.py`)은 그 차례의 한 쪽이다. 이어 보기는 모델을 부르지 않는다 — 블록에 저장된 **서버가 검증한 인자**를
다시 검증하고 `offset` · `sort` 만 바꿔 같은 도구를 READ ONLY 로 다시 돈다(`catalog.run`). 사용 기록 · 한도 소비가 없다.

지키는 것:
- 메시지 → 대화 주인을 먼저 본다(남의 메시지는 403, 없거나 지운 답 · 블록이 없는 id 는 404).
- 그 도구를 **지금도** 쓸 수 있어야 한다(권한 · 기능 플래그 — 블록을 만든 때가 아니라 지금). 읽기는 지금 권한으로 한다 —
  그 사이 볼 수 없게 된 자료는 다음 쪽에 나오지 않는다.
- 바꿀 수 있는 것은 `offset`(도구 상한 안)과 `sort`(그 도구가 받는 값)뿐이다. 저장된 인자가 고쳐졌으면 검증에서 422 다.
"""

from __future__ import annotations

import json
from dataclasses import replace

from pydantic import ValidationError

from app.ai.assistant import blocks, catalog
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError


def _stored_block(message, rid: str) -> dict:
    try:
        payload = json.loads(message.structured_payload_json) if message.structured_payload_json else {}
    except (TypeError, ValueError):
        payload = {}
    for block in (payload.get("results") or []) if isinstance(payload, dict) else []:
        if isinstance(block, dict) and block.get("id") == rid:
            return block
    raise NotFoundError("이 목록을 찾을 수 없습니다.")


def next_page(db, user, message, rid: str, *, offset: int, sort: str | None, env: catalog.ToolEnv,
              allowed: dict) -> dict:
    """저장된 블록 `rid` 의 한 쪽을 다시 읽어 블록 모양으로 돌려준다(같은 `id`). ``allowed`` 는 이 사람이 지금 쓸 수 있는 도구다."""
    block = _stored_block(message, rid)
    tool = allowed.get(str(block.get("tool") or ""))
    if tool is None or tool.name not in blocks.SHOWABLE:
        raise ForbiddenError("이 목록을 다시 볼 권한이 없습니다.")
    args = dict(block.get("args") or {})
    args["offset"] = offset
    if sort is not None:
        if sort not in blocks.SORT_OPTIONS.get(tool.name, ()):
            raise ValidationAppError("이 목록은 그 순서로 정렬할 수 없습니다.")
        args["sort"] = sort
    try:
        validated = tool.args.model_validate(args)
    except ValidationError as exc:
        raise ValidationAppError("이 목록을 이어서 볼 수 없습니다. 쪽이나 정렬 값을 확인해 주세요.") from exc
    execution = catalog.run(tool, validated, env)
    if not execution.ok:
        raise NotFoundError("이 목록을 다시 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
    stored = validated.model_dump(exclude_none=True)
    stored["show"] = True
    [page] = blocks.build([replace(execution, args=stored)], owner_id=getattr(user, "id", None)) or [None]
    if page is None:
        raise NotFoundError("이 목록을 다시 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
    page["id"] = rid
    return page
