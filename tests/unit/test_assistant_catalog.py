"""AI 도우미 도구 등록의 계약 (D-535).

  * 바깥 스키마는 두 제공자의 공용 모양만 쓴다 - OpenAI `strict:true` 와 Anthropic `input_schema` 가 함께 받는다
  * 바깥 스키마와 서버 인자 모델의 칸이 같다(한쪽에만 있는 칸은 모델이 보내도 거절되거나, 보낼 수 없다)
  * 화면 이름은 명사구, 진행 문구는 완전한 문장이다(CLAUDE.md 의 한국어 규칙)
  * 권한 문과 플래그 문이 맞게 걸린다
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.ai.assistant import catalog
from app.ai.providers import base

ALLOWED_KEYS = {"type", "enum", "description", "properties", "required", "additionalProperties", "items"}


def _walk(schema: dict):
    yield schema
    for value in (schema.get("properties") or {}).values():
        yield from _walk(value)
    if isinstance(schema.get("items"), dict):
        yield from _walk(schema["items"])


@pytest.mark.parametrize("tool", catalog.REGISTRY, ids=lambda t: t.name)
def test_the_outer_schema_uses_only_the_shared_shape(tool):
    spec = tool.spec()
    assert isinstance(spec, base.ToolSpec)
    params = spec.parameters
    assert params["type"] == "object" and params["additionalProperties"] is False
    assert params["required"] == list(params["properties"]), "모든 속성이 required 여야 한다(선택은 null 로)"
    for node in _walk(params):
        assert set(node) <= ALLOWED_KEYS, (tool.name, set(node) - ALLOWED_KEYS)
    for name, prop in params["properties"].items():
        assert prop.get("description"), (tool.name, name)
        types = prop["type"] if isinstance(prop["type"], list) else [prop["type"]]
        if "null" in types and "enum" in prop:
            assert None in prop["enum"], "null 을 받는 선택지는 enum 에도 null 이 있어야 strict 가 받는다"


@pytest.mark.parametrize("tool", catalog.REGISTRY, ids=lambda t: t.name)
def test_the_outer_schema_and_the_server_model_have_the_same_fields(tool):
    assert set(tool.spec().parameters["properties"]) == set(tool.args.model_fields)
    with pytest.raises(ValidationError):
        tool.args.model_validate({"unknown_field": 1})


@pytest.mark.parametrize("tool", catalog.REGISTRY, ids=lambda t: t.name)
def test_screen_words_are_complete_korean(tool):
    assert re.fullmatch(r"[a-z_]+", tool.name)
    assert not tool.label.endswith(".") and tool.label.strip() == tool.label
    assert tool.progress.endswith("니다."), tool.progress
    assert tool.description.endswith("."), tool.description
    for text in (tool.label, tool.progress, tool.description):
        assert "·" not in text and "—" not in text and "해당" not in text


def test_names_are_unique_and_there_are_twelve():
    names = [tool.name for tool in catalog.REGISTRY]
    assert len(names) == len(set(names)) == 12


def test_document_tools_need_document_read_and_people_need_team_chat():
    gates = {tool.name: (tool.permission, tool.flag) for tool in catalog.REGISTRY}
    assert gates["search_documents"] == ("DOCUMENT_READ", None)
    assert gates["get_document"] == ("DOCUMENT_READ", None)
    assert gates["find_people"] == (None, "team_chat_enabled")


def test_available_tools_filter_by_permission_and_flag():
    everything = catalog.available_tools(can=lambda key: True, flag=lambda key: True)
    assert len(everything) == 12
    no_docs = {t.name for t in catalog.available_tools(can=lambda key: key != "DOCUMENT_READ", flag=lambda key: True)}
    assert {"search_documents", "get_document"}.isdisjoint(no_docs)
    no_chat = {t.name for t in catalog.available_tools(can=lambda key: True, flag=lambda key: False)}
    assert "find_people" not in no_chat and "my_work" in no_chat


def test_execute_refuses_a_tool_outside_the_allowed_set_without_running_it():
    called = []
    allowed = {"my_work": catalog.TOOLS["my_work"]}
    call = base.ToolCall(id="c1", name="search_documents", arguments={"query": "연차"})
    result = catalog.execute(call, allowed=allowed, env=None, progress=called.append)
    assert (result.ok, '"unavailable"' in result.content) == (False, True)
    assert called == [], "실행하지 않을 도구의 진행 문구를 적었다"


@pytest.mark.parametrize("arguments", [None, {"view": "everything"}, {"view": "assigned", "user_id": "x"}])
def test_execute_refuses_bad_arguments_before_opening_a_session(arguments):
    allowed = {"my_work": catalog.TOOLS["my_work"]}
    call = base.ToolCall(id="c1", name="my_work", arguments=arguments)
    result = catalog.execute(call, allowed=allowed, env=None)
    assert '"invalid_arguments"' in result.content
