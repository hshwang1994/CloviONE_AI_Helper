"""CORE-12 regression: SecretMissingError no longer carries the secret_ref
NAME in its message (app/core/secret_refs.py::require). Four call sites used
to detect "token not configured" by checking whether that name appeared as a
substring of str(exc) — a check that silently stopped matching anything the
moment the name left the message, turning the common "not configured yet"
state into a generic query-failure error instead. app/reports/notion_source.py
already had test coverage that caught this (tests/unit/test_fake_notion.py);
notion_docs.py and notion_write.py did not, so their equivalent breakage went
unnoticed until now. This file pins all three (probe_notion.py's mapping is
covered by tests/integration/test_notion_console.py's RESULT_TOKEN_MISSING
assertion already).
"""

from __future__ import annotations

import pytest

from app.core.allowlist import AllowlistRegistry
from app.core.http_client import OutboundClient
from app.core.secret_refs import FileSecretReferenceProvider

pytestmark = pytest.mark.unit


@pytest.fixture()
def outbound(settings, fake_http):
    return OutboundClient(
        AllowlistRegistry(settings.config_dir),
        FileSecretReferenceProvider(settings.secrets_dir),
        transport=fake_http.transport(),
    )


def test_notion_docs_missing_token_maps_to_not_configured(settings, outbound):
    from app.team_docs import notion_docs

    with pytest.raises(notion_docs.NotionDocsNotConfiguredError):
        notion_docs._request(outbound, settings, "GET", "/v1/pages/some-page")


def test_notion_write_missing_token_maps_to_not_configured(settings, outbound):
    from app.tickets import notion_write

    with pytest.raises(notion_write.NotionNotConfiguredError):
        notion_write._request(outbound, settings, "GET", "/v1/pages/some-page")
