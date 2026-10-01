"""추천 모델 표 (D-539) — 인증이 끝난 뒤 모델이 비어 있을 때만 쓰는 하나.

못박는 성질:
1. Anthropic 은 `claude-sonnet` → `claude-opus` → `claude-haiku` 앞머리 순서이고, 같은 앞머리 안에서는 서버 순서(최신 먼저)의
   첫 것이다. 옛 이름 순서(`claude-3-7-sonnet-…`)는 앞머리가 맞지 않아 고르지 않는다.
2. OpenAI API 키는 `gpt-5` → `gpt-4.1` → `gpt-4o` 이고, 별칭(앞머리와 똑같은 이름)을 먼저, 없으면 `mini` · `nano` 가 아닌 가장
   짧은 이름이다.
3. ChatGPT 요금제는 서버 순서의 첫 모델이다.
4. 맞는 것이 없거나 목록이 비면 None 이다(지어내지 않는다). 모르는 제공자도 None 이다.
"""

from __future__ import annotations

from app.ai.providers import base


def _models(*ids):
    return tuple({"id": i, "label": i} for i in ids)


def test_anthropic_follows_the_family_order_and_the_server_order_within_a_family():
    models = _models("claude-haiku-9-1", "claude-opus-9-0", "claude-sonnet-9-2", "claude-sonnet-9-1")
    assert base.recommend("anthropic", "api_key", models) == "claude-sonnet-9-2"
    assert base.recommend("anthropic", "api_key", _models("claude-haiku-9-1", "claude-opus-9-0")) == "claude-opus-9-0"
    assert base.recommend("anthropic", "api_key", _models("claude-3-7-sonnet-20250219")) is None


def test_openai_api_key_prefers_the_alias_then_the_shortest_full_size_name():
    assert base.recommend("openai", "api_key", _models("gpt-4o", "gpt-5-mini", "gpt-5", "gpt-5-2025-08-07")) == "gpt-5"
    assert base.recommend("openai", "api_key", _models("gpt-5-mini", "gpt-5-2025-08-07", "gpt-4o")) \
        == "gpt-5-2025-08-07"
    assert base.recommend("openai", "api_key", _models("gpt-5-nano", "gpt-4.1-mini", "gpt-4.1")) == "gpt-4.1"
    assert base.recommend("openai", "api_key", _models("o3", "text-embedding-3-large")) is None


def test_the_chatgpt_plan_uses_the_first_model_the_server_lists():
    assert base.recommend("openai", "chatgpt", _models("gpt-6.1-sol", "gpt-6-mini")) == "gpt-6.1-sol"


def test_nothing_is_invented():
    assert base.recommend("anthropic", "api_key", ()) is None
    assert base.recommend("openai", "chatgpt", ()) is None
    assert base.recommend("nobody", "api_key", _models("x")) is None
    assert base.recommend("openai", "api_key", ({"label": "id 없음"}, {"id": ""})) is None
