"""CORE-12 회귀: 「토큰이 아직 없다」가 일반 실패에 섞이지 않는다.

## 무엇이 있었나

`app/core/secret_refs.py::require` 는 예전에 없는 secret 파일의 **이름을 예외 메시지에
실었다.** 그 메시지는 응답 본문으로 그대로 나갔고, 그 예외를 일으키는 요청은 관리자만
부르는 것이 아니었다. 그래서 이름을 뺐다.

그러자 반대편이 조용히 깨졌다. 호출부 넷이 「토큰 미설정」을 **메시지에 그 이름이 들어
있는가**로 판별하고 있었다 — 이름이 사라진 순간 그 검사는 아무것도 못 맞히게 됐고,
"아직 설정 안 됨"이 "질의가 실패했다"로 바뀌어 화면이 엉뚱한 말을 했다.

## 지금 그 자리는 어디인가 (S14)

그때의 호출부 넷은 전부 사라졌다 — 제품이 Notion 을 부르지 않는다. 남은 소비자는 **이관
도구**(`app/migration/source_notion.py`) 하나이고, 조건은 하나도 달라지지 않았다: 이관을
처음 돌리는 사람은 토큰을 아직 안 놓은 상태이고, 그때 "Notion 호출 실패" 라고만 하면
무엇을 해야 하는지 알 수 없다.

그래서 두 가지를 못박는다. 예외가 **이름을 안 싣는다**(원래 고친 방향), 그리고 그 예외가
이관 클라이언트를 **그대로 통과한다**(뒤늦게 일반 오류로 뭉개지지 않는다).

"""

from __future__ import annotations

import pytest

from app.core.allowlist import AllowlistRegistry
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider, SecretMissingError

pytestmark = pytest.mark.unit

TOKEN_REF = "notion_migration_token"


@pytest.fixture()
def outbound(settings, fake_http):
    return OutboundClient(
        AllowlistRegistry(settings.config_dir),
        FileSecretReferenceProvider(settings.secrets_dir),
        transport=fake_http.transport(),
    )


def test_the_missing_secret_error_never_names_the_file(settings):
    """이름은 운영자가 로그에서 볼 정보지 응답을 받는 사람 모두에게 줄 정보가 아니다."""
    provider = FileSecretReferenceProvider(settings.secrets_dir)
    with pytest.raises(SecretMissingError) as caught:
        provider.require(TOKEN_REF)
    assert TOKEN_REF not in caught.value.message
    # 화면은 이름이 아니라 **코드**로 판별한다 — 그것이 이 고침의 대체 수단이었다.
    assert caught.value.code == "secret_missing"


def test_the_migration_client_lets_the_missing_token_through(settings, tmp_path, outbound):
    """토큰이 없으면 「설정 안 됨」이 그대로 올라온다 — 일반 호출 실패로 뭉개지지 않는다.

    이관 클라이언트는 전송 오류를 `NotionSourceError` 로 바꾼다. 그 변환이 `AppError`
    까지 삼키면 첫 실행에서 나오는 메시지가 "Notion 호출 실패" 가 되고, 사용자는 토큰을
    안 놓았다는 사실을 끝내 못 듣는다.
    """
    from app.migration.source_notion import NotionSource

    source = NotionSource(
        outbound, secret_ref=TOKEN_REF, cache_dir=tmp_path / "cache", throttle_seconds=0,
    )
    with pytest.raises(SecretMissingError):
        source._call("GET", "/v1/databases/whatever")


def test_a_present_token_gets_past_that_gate(settings, tmp_path, outbound, fake_http):
    """**반례** — 토큰만 놓으면 같은 호출이 그 문을 지난다.

    이것이 없으면 위 시험은 「무슨 이유로든 실패한다」만 증명하고, 토큰 유무와 아무 상관이
    없어도 초록으로 남는다.
    """
    from app.migration.source_notion import NotionSource

    (settings.secrets_dir / TOKEN_REF).write_text("fake-token", encoding="utf-8")
    fake_http.on("https://api.notion.com/v1/databases/whatever",
                 json_body={"object": "database", "id": "whatever"})
    source = NotionSource(
        outbound, secret_ref=TOKEN_REF, cache_dir=tmp_path / "cache", throttle_seconds=0,
    )
    assert source._call("GET", "/v1/databases/whatever")["id"] == "whatever"
