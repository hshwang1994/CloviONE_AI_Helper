"""SYS-01 회귀: 인증서 교체 액션이 nginx 가 실제로 읽는 경로를 쓰는가.

`app/sysops/actions_service.py` 는 예전에 `/etc/ssl/clovirone/…` 로 하드코딩돼 있었는데,
nginx 는 `deploy/install.sh` 가 만든 `$ETC_DIR/tls/$DNS_NAME.{crt,key}` 만
읽는다 - openssl 쌍 검증·`nginx -t`·reload 까지 전부 성공하고 새 인증서의 subject·만료일을
보여 주면서도 실제로는 아무것도 안 바뀌는 조용한 무동작이었다. 이 파일은 그 배선점
(`_resolve_tls_paths`)이 `settings.tls_cert_path`(env `TLS_CERT_PATH`, `app/health/service.py`
·`app/setup/probes.py` 와 같은 값)를 실제로 따라가는지 고정한다.

`_resolve_tls_paths()`를 **직접** 호출해서 본다(모듈을 reload 하지 않는다) — `actions_service`
의 `cert.install` 액션은 import 시점에 딱 한 번 `register()`되고, 그 레지스트리는 중복 등록을
`RuntimeError`로 막는다(`app/sysops/actions.py::register`). reload 로 두 번째 등록을 시도하면
그 가드에 걸린다.
"""

from __future__ import annotations

import pytest

from app.sysops import actions_service as mod

pytestmark = pytest.mark.unit


def test_uses_tls_cert_path_env_when_set():
    cert, key, cert_stage, key_stage = mod._resolve_tls_paths_for(
        "/etc/clovirone-web-assistant/tls/clovirassist.gooddi.lab.crt"
    )
    assert cert == "/etc/clovirone-web-assistant/tls/clovirassist.gooddi.lab.crt"


def test_derives_key_path_next_to_the_cert_same_basename():
    """nginx 템플릿과 같은 관례(같은 디렉터리·같은 basename, 확장자만 .key)."""
    _, key, _, _ = mod._resolve_tls_paths_for(
        "/etc/clovirone-web-assistant/tls/clovirassist.gooddi.lab.crt"
    )
    assert key == "/etc/clovirone-web-assistant/tls/clovirassist.gooddi.lab.key"


def test_stages_next_to_the_real_cert_not_in_the_old_hardcoded_dir():
    _, _, cert_stage, key_stage = mod._resolve_tls_paths_for(
        "/etc/clovirone-web-assistant/tls/clovirassist.gooddi.lab.crt"
    )
    assert cert_stage == "/etc/clovirone-web-assistant/tls/.staged.crt"
    assert key_stage == "/etc/clovirone-web-assistant/tls/.staged.key"


def test_falls_back_to_the_product_ssl_dir_when_the_env_var_is_unset():
    """dev/test 환경, 또는 앞단 프록시가 TLS 를 끊는 설치에는 이 env 가 없다 - 크래시하지
    않고 제품 기본 경로로 남는다(그 경우 이 액션이 실제로 쓰이는 서버가 없으므로 무해).

    **경로를 여기에 글자로 다시 적지 않는다.** 그러면 slug 를 바꾸는 날 두 곳을 고쳐야 하고,
    한 곳만 고치면 시험은 초록인데 헬퍼는 아무도 안 읽는 자리에 인증서를 쓴다(SYS-01 이
    정확히 그 실패였다). 정본 하나를 보고 «넷이 그 디렉터리 아래에 같은 관례로 놓인다» 를
    확인한다.
    """
    from app.core import product

    cert, key, cert_stage, key_stage = mod._resolve_tls_paths_for("")
    assert cert == f"{product.SSL_FALLBACK_DIR}/server.crt"
    assert key == f"{product.SSL_FALLBACK_DIR}/server.key"
    assert cert_stage == f"{product.SSL_FALLBACK_DIR}/.staged.crt"
    assert key_stage == f"{product.SSL_FALLBACK_DIR}/.staged.key"
    # 옛 정체성이 되살아나지 않는지도 함께 본다 (R13).
    assert "clovirone" not in cert


def test_the_registered_action_touches_whatever_this_call_resolved(monkeypatch):
    """엔진의 백업/롤백 대상(`touches`)과 `_perform_cert` 가 쓰는 파일이 **같은 값**이어야 한다 — 그렇지 않으면 실패 시 엉뚱한
    파일이 되돌아가고 진짜 대상은 그대로 깨진 채 남는다. 둘 다 `_normalize_cert` 가 한 번 푼 `paths` 를 받는다(M3, D-573)."""
    from app.sysops.actions import get_action

    monkeypatch.setattr(mod, "_read_env_file", lambda: "TLS_CERT_PATH=/etc/clovirassist/tls/a.example.com.crt\n")
    action = get_action("cert.install")
    params = action.normalize({"certificate": PEM_CERT, "private_key": PEM_KEY})
    assert action.touches(params) == ("/etc/clovirassist/tls/a.example.com.crt", "/etc/clovirassist/tls/a.example.com.key")


PEM_CERT = "-----BEGIN CERTIFICATE-----\nAAA\n-----END CERTIFICATE-----"
PEM_KEY = "-----BEGIN PRIVATE KEY-----\nBBB\n-----END PRIVATE KEY-----"


def test_paths_follow_the_env_file_on_every_call_not_the_import_time_value(monkeypatch):
    """대표 주소를 바꾸면(`domain.apply`) env 의 `TLS_CERT_PATH` 가 새 이름의 파일로 바뀐다. 헬퍼를 다시 띄우지 않아도 다음
    `cert.install` 이 그 파일에 써야 한다 — import 시점 상수만 보면 옛 이름의 파일을 갈아 끼우고 「교체했다」고 말한다."""
    from app.sysops.actions import get_action

    action = get_action("cert.install")
    env = {"text": "TLS_CERT_PATH=/etc/clovirassist/tls/old.example.internal.crt\n"}
    monkeypatch.setattr(mod, "_read_env_file", lambda: env["text"])
    first = action.normalize({"certificate": PEM_CERT, "private_key": PEM_KEY})["paths"][0]
    env["text"] = "APP_BASE_URL=https://new.example.com\nTLS_CERT_PATH=/etc/clovirassist/tls/new.example.com.crt\n"
    second = action.normalize({"certificate": PEM_CERT, "private_key": PEM_KEY})["paths"][0]
    assert first.endswith("old.example.internal.crt") and second.endswith("new.example.com.crt")


def test_without_an_env_file_the_process_environment_is_the_fallback(monkeypatch):
    monkeypatch.setattr(mod, "_read_env_file", lambda: None)
    monkeypatch.setenv("TLS_CERT_PATH", "/etc/clovirassist/tls/from-unit.example.com.crt")
    assert mod.tls_paths(None)[0] == "/etc/clovirassist/tls/from-unit.example.com.crt"
    monkeypatch.delenv("TLS_CERT_PATH")
    from app.core import product

    assert mod.tls_paths(None)[0] == f"{product.SSL_FALLBACK_DIR}/server.crt"


def test_cert_install_writes_where_the_env_file_points(monkeypatch):
    """끝에서 끝까지 — 가짜 시스템에서 `cert.install` 이 env 가 가리키는 새 경로에 쓰고 그 경로만 되돌릴 대상으로 잡는다."""
    from datetime import datetime, timezone

    from app.sysops import actions as engine
    from tests.fakes.sysops import FakeRunner

    crt, key = "/etc/clovirassist/tls/new.example.com.crt", "/etc/clovirassist/tls/new.example.com.key"
    stage_crt, stage_key = "/etc/clovirassist/tls/.staged.crt", "/etc/clovirassist/tls/.staged.key"
    monkeypatch.setattr(mod, "_read_env_file", lambda: f"TLS_CERT_PATH={crt}\n")
    runner = FakeRunner({crt: "old cert", key: "old key"})
    runner.reply(["/usr/bin/openssl", "x509", "-noout", "-in", stage_crt])
    runner.reply(["/usr/bin/openssl", "pkey", "-noout", "-in", stage_key])
    runner.reply(["/usr/bin/openssl", "x509", "-noout", "-pubkey", "-in", stage_crt], out="PUB")
    runner.reply(["/usr/bin/openssl", "pkey", "-pubout", "-in", stage_key], out="PUB")
    runner.reply(["/usr/sbin/nginx", "-t"])
    runner.reply(["/usr/bin/systemctl", "reload", "nginx.service"])
    result = engine.execute(runner, "cert.install", {"certificate": PEM_CERT, "private_key": PEM_KEY},
                            backup_root="/var/backups/x", now=datetime(2026, 10, 15, tzinfo=timezone.utc))
    assert result.ok, result.detail
    assert runner.files[crt].startswith("-----BEGIN CERTIFICATE-----") and runner.modes[key] == 0o600
    assert stage_crt not in runner.files and stage_key not in runner.files
