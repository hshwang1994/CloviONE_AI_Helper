"""SYS-01 회귀: 인증서 교체 액션이 nginx 가 실제로 읽는 경로를 쓰는가.

`app/sysops/actions_service.py` 는 예전에 `/etc/ssl/clovirone/…` 로 하드코딩돼 있었는데,
nginx 는 `install-clovirone-web-assistant.sh` 가 만든 `$ETC_DIR/tls/$DNS_NAME.{crt,key}` 만
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
        "/etc/clovirone-web-assistant/tls/clovirone-ai.gooddi.lab.crt"
    )
    assert cert == "/etc/clovirone-web-assistant/tls/clovirone-ai.gooddi.lab.crt"


def test_derives_key_path_next_to_the_cert_same_basename():
    """nginx 템플릿과 같은 관례(같은 디렉터리·같은 basename, 확장자만 .key)."""
    _, key, _, _ = mod._resolve_tls_paths_for(
        "/etc/clovirone-web-assistant/tls/clovirone-ai.gooddi.lab.crt"
    )
    assert key == "/etc/clovirone-web-assistant/tls/clovirone-ai.gooddi.lab.key"


def test_stages_next_to_the_real_cert_not_in_the_old_hardcoded_dir():
    _, _, cert_stage, key_stage = mod._resolve_tls_paths_for(
        "/etc/clovirone-web-assistant/tls/clovirone-ai.gooddi.lab.crt"
    )
    assert cert_stage == "/etc/clovirone-web-assistant/tls/.staged.crt"
    assert key_stage == "/etc/clovirone-web-assistant/tls/.staged.key"


def test_falls_back_to_the_old_default_when_the_env_var_is_unset():
    """dev/test 환경, 또는 앞단 프록시가 TLS 를 끊는 설치에는 이 env 가 없다 - 크래시하지
    않고 예전 기본 경로로 남는다(그 경우 이 액션이 실제로 쓰이는 서버가 없으므로 무해)."""
    cert, key, cert_stage, key_stage = mod._resolve_tls_paths_for("")
    assert cert == "/etc/ssl/clovirone/server.crt"
    assert key == "/etc/ssl/clovirone/server.key"
    assert cert_stage == "/etc/ssl/clovirone/.staged.crt"
    assert key_stage == "/etc/ssl/clovirone/.staged.key"


def test_the_registered_action_touches_whatever_this_process_resolved_at_import():
    """`touches=` 는 등록 시점에 평가된다 - 엔진의 백업/롤백이 실제로 쓰는 파일과
    `_perform_cert` 가 쓰는 파일이 같은 상수를 봐야 한다(그렇지 않으면 실패 시 엉뚱한
    파일이 되돌아가고 진짜 대상은 그대로 깨진 채 남는다). 이 프로세스가 어떤 `TLS_CERT_PATH`
    로 시작됐든(보통은 비어 있다, 테스트 환경) `touches()`는 그 시점의 모듈 상수와 항상
    같아야 한다."""
    from app.sysops.actions import get_action

    action = get_action("cert.install")
    assert action.touches({}) == (mod.CERT_PATH, mod.KEY_PATH)
