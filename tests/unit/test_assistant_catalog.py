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


def test_names_are_unique_and_there_are_seventeen():
    names = [tool.name for tool in catalog.REGISTRY]
    assert len(names) == len(set(names)) == 17
    assert {"my_documents", "project_activity", "my_notifications", "my_activity", "sprint_meetings"} <= set(names)


def test_document_tools_need_document_read_and_people_need_team_chat():
    gates = {tool.name: (tool.permission, tool.flag) for tool in catalog.REGISTRY}
    assert gates["search_documents"] == ("DOCUMENT_READ", None)
    assert gates["get_document"] == ("DOCUMENT_READ", None)
    assert gates["my_documents"] == ("DOCUMENT_READ", None)
    assert gates["find_people"] == (None, "team_chat_enabled")
    for name in ("project_activity", "my_notifications", "my_activity", "sprint_meetings"):
        assert gates[name] == (None, None), name


def test_available_tools_filter_by_permission_and_flag():
    everything = catalog.available_tools(can=lambda key: True, flag=lambda key: True)
    assert len(everything) == 17
    no_docs = {t.name for t in catalog.available_tools(can=lambda key: key != "DOCUMENT_READ", flag=lambda key: True)}
    assert {"search_documents", "get_document", "my_documents"}.isdisjoint(no_docs)
    assert "project_activity" in no_docs, "문서 권한이 없어도 프로젝트 진행 현황은 쓴다(문서 칸만 빠진다)"
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


def test_every_description_is_complete_korean_sentences():
    """설명은 마침표로 끝나는 완전한 문장들이다 — 조각 문장 · 번역투 · 서류 말투를 쓰지 않는다(CLAUDE.md §10)."""
    for tool in catalog.REGISTRY:
        for sentence in [s for s in tool.description.split(". ") if s]:
            assert sentence.rstrip(".").strip(), tool.name
        for word in ("이를 통해", "수행한다", "한눈에"):
            assert word not in tool.description, (tool.name, word)
        for name, prop in tool.spec().parameters["properties"].items():
            assert prop["description"].endswith("."), (tool.name, name)
            assert "·" not in prop["description"] and "해당" not in prop["description"], (tool.name, name)


def test_the_routing_sentences_point_identity_questions_at_the_identity_tools():
    """「내가 작성한 문서」를 이름 문자열로 검색하던 결함(계획 4절) — 설명이 신원 도구로 보낸다."""
    tools = catalog.TOOLS
    assert "my_documents" in tools["search_documents"].description
    assert "내가 작성한 문서" in tools["my_documents"].description
    assert "total" in tools["my_documents"].description and "total" in tools["my_work"].description
    assert "search_documents" in tools["search_workspace"].description
    assert "project_activity" in tools["search_projects"].description
    assert "후보" in tools["project_activity"].description and "후보" in tools["get_project_summary"].description


@pytest.mark.parametrize("name,arguments", [
    ("search_documents", {"query": "연차", "project": None, "offset": 41}),
    ("my_documents", {"view": "everything"}),
    ("search_tickets", {"scope": "team", "statuses": ["끝남"]}),
    ("my_activity", {"days": 91}),
    ("my_notifications", {"days": 61}),
    ("project_activity", {"project": "a", "days": 181}),
    ("my_documents", {"view": "authored", "user_id": "someone"}),
])
def test_out_of_range_or_foreign_arguments_are_refused(name, arguments):
    with pytest.raises(ValidationError):
        catalog.TOOLS[name].args.model_validate(arguments)


def test_show_only_on_list_and_summary_tools():
    """`show` 는 결과 블록이 있는 도구(목록 · 현황)에만 있다 — 문서 읽기 · 티켓 보기 · 요약 같은 단건 도구에 두면 모델이 그리지 못할
    목록을 보여 주겠다고 고른다. 스키마는 OpenAI strict 규칙대로 필수 + null 허용이다."""
    from app.ai.assistant import blocks

    required = {"search_documents": {"query": "연차"}, "my_work": {"view": "assigned"}, "search_tickets": {"scope": "team"},
                "search_projects": {"scope": "mine"}, "get_project_summary": {"project": "a"},
                "project_activity": {"project": "a"}, "my_approvals": {"box": "todo"}}
    for tool in catalog.REGISTRY:
        props = tool.spec().parameters["properties"]
        assert ("show" in props) == (tool.name in blocks.SHOWABLE), tool.name
        if "show" in props:
            assert props["show"]["type"] == ["boolean", "null"]
            assert "show" in tool.spec().parameters["required"]
            assert tool.args.model_validate({**required.get(tool.name, {}), "show": True}).show is True
