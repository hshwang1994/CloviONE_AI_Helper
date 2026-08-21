"""제품 정체성이 **코드와 설치 자산에서 갈라지지 않게** 고정한다 (R13 · S4).

## 왜 이 파일이 있나

slug 는 한 단어인데 그 한 단어가 세 곳에서 따로 살아 있다: 파이썬 상수
(`app/core/product.py`), 설치 스크립트의 셸 변수(`deploy/install.sh`), systemd 유닛 파일.
셋 중 하나만 바뀌면 **아무 오류도 안 난다** —

- 헬퍼 소켓 경로가 어긋나면 웹은 조용히 «도우미가 없습니다» 만 보여 준다.
- 관리 콘솔의 서비스 제어 목록이 어긋나면 systemd 에 없는 유닛 이름을 넘긴다.
- 설치 스크립트가 만드는 디렉터리와 앱이 읽는 디렉터리가 어긋나면 설정이 «없는» 것이 된다.

전부 초록인 채로 고장 나는 종류라, 사람이 기억하는 것에 맡기지 않는다.

## 여기서 검사하지 않는 것

「설치 스크립트가 실제로 그 유닛을 띄운다」는 리눅스에서 돌려야 안다. 그걸 이 검사가 하는
척하지 않는다 — 그 몫은 LXD 리허설(`scripts/lxd_rehearsal.sh`)이 진다. 다만 **이름이
갈라진 것**은 여기서 확실히 잡는다.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.core import product

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
INSTALL_SH = ROOT / "deploy" / "install.sh"
UNIT_DIR = ROOT / "deploy" / "systemd"
NGINX_CONF = ROOT / "deploy" / "nginx" / "clovirassist.conf"
ENV_EXAMPLE = ROOT / "deploy" / "clovirassist.env.example"

_ASSIGN = re.compile(r'^([A-Z][A-Z0-9_]*)=(".*?"|\'.*?\'|\S*)\s*(?:#.*)?$')
_REF = re.compile(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?')


def _shell_vars(text: str) -> dict[str, str]:
    """`deploy/install.sh` 머리의 상수 블록을 읽는다.

    첫 함수 정의에서 멈춘다 — 그 아래는 지역 변수라 여기서 볼 것이 아니다.
    `$SLUG` 같은 참조는 이미 읽은 값으로 편다(설치 스크립트가 실제로 하는 일과 같다).
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        if re.match(r'^\s*\w[\w-]*\(\)\s*\{', line):
            break
        m = _ASSIGN.match(line.strip())
        if not m:
            continue
        key, raw = m.group(1), m.group(2)
        if raw[:1] in {'"', "'"}:
            raw = raw[1:-1]
        if "$(" in raw or "`" in raw:
            continue
        out[key] = _REF.sub(lambda mm: out.get(mm.group(1), mm.group(0)), raw)
    return out


@pytest.fixture(scope="module")
def sh() -> dict[str, str]:
    assert INSTALL_SH.is_file(), f"설치 진입점이 없다: {INSTALL_SH}"
    return _shell_vars(INSTALL_SH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("py_value", "sh_key"),
    [
        (product.SLUG, "SLUG"),
        (product.SERVICE_USER, "SVC_USER"),
        (product.APP_DIR, "APP_DIR"),
        (product.ETC_DIR, "ETC_DIR"),
        (product.VAR_DIR, "VAR_DIR"),
        (product.BACKUP_DIR, "BACKUP_ROOT"),
        (product.LOG_DIR, "LOG_ROOT"),
        (product.RUN_DIR, "RUN_DIR"),
        (product.TLS_DIR, "TLS_DIR"),
        (product.SECRETS_DIR, "SECRETS_DIR"),
        (product.ENV_FILE, "ENV_FILE"),
        (product.NGINX_SITE, "NGINX_SITE"),
        (product.SSL_FALLBACK_DIR, "SSL_FALLBACK_DIR"),
        (product.WEB_UNIT, "WEB_UNIT"),
        (product.WORKER_UNIT, "WORKER_UNIT"),
        (product.WORKER_CONVERSATIONAL_UNIT, "WORKER_CONV_UNIT"),
        (product.SCHEDULER_UNIT, "SCHEDULER_UNIT"),
        (product.PRIVHELPER_UNIT, "PRIVHELPER_UNIT"),
        (product.LEGACY_SLUG, "LEGACY_SLUG"),
        (product.LEGACY_SERVICE_USER, "LEGACY_SVC_USER"),
    ],
)
def test_the_installer_and_the_code_agree_on_every_name(sh, py_value, sh_key):
    assert sh_key in sh, f"deploy/install.sh 에 {sh_key} 가 없다 — 이름이 갈라졌다"
    assert sh[sh_key] == py_value, (
        f"{sh_key}: 설치 스크립트는 {sh[sh_key]!r}, app/core/product.py 는 {py_value!r}"
    )


def test_every_unit_the_installer_installs_exists_in_the_repo():
    """설치 스크립트가 없는 파일을 설치하려 하면 Stage 13 에서 죽는다 — 그 전에 잡는다."""
    for unit in product.ALL_UNITS:
        assert (UNIT_DIR / unit).is_file(), f"유닛 파일이 없다: deploy/systemd/{unit}"


def test_the_installer_installs_exactly_the_units_the_code_knows_about(sh):
    """`ALL_UNITS` 가 두 곳에 있으면 한쪽만 늘어나는 날이 온다."""
    line = next(
        (ln for ln in INSTALL_SH.read_text(encoding="utf-8").splitlines()
         if ln.startswith("ALL_UNITS=(")),
        "",
    )
    assert line, "deploy/install.sh 에 ALL_UNITS 배열이 없다"
    names = [sh.get(m.group(1), m.group(0)) for m in _REF.finditer(line)]
    assert tuple(names) == product.ALL_UNITS, (
        f"설치 순서/목록이 다르다: 설치 스크립트 {names} vs product.ALL_UNITS {list(product.ALL_UNITS)}"
    )


def test_units_that_must_come_back_after_reboot_are_a_subset_of_all_units():
    """재부팅 복구 판정 대상은 설치되는 유닛 중에서만 고를 수 있다."""
    assert set(product.ALWAYS_ACTIVE_UNITS) <= set(product.ALL_UNITS)
    # 대화형 레인은 설정이 꺼져 있으면 exit(0) 해 inactive(dead) 로 쉰다 — 그것이 정상
    # 대기 상태라 «떠 있어야 하는» 목록에 넣으면 매번 거짓 실패가 난다 (D-118).
    assert product.WORKER_CONVERSATIONAL_UNIT not in product.ALWAYS_ACTIVE_UNITS
    # 반대로 스케줄러는 반드시 떠 있어야 한다 (D-225).
    assert product.SCHEDULER_UNIT in product.ALWAYS_ACTIVE_UNITS


@pytest.mark.parametrize("unit", sorted(product.ALL_UNITS))
def test_each_unit_points_at_the_product_paths(unit):
    text = (UNIT_DIR / unit).read_text(encoding="utf-8")
    assert f"WorkingDirectory={product.APP_DIR}" in text, f"{unit}: WorkingDirectory 가 제품 경로가 아니다"
    assert f"ExecStart={product.APP_DIR}/venv/bin/" in text, f"{unit}: ExecStart 가 제품 venv 가 아니다"
    assert product.ENV_FILE in text, f"{unit}: 설정 파일 경로가 다르다"
    assert "clovirone" not in text, f"{unit}: 옛 정체성이 남아 있다"


def test_the_helper_socket_is_the_one_the_web_dials():
    """헬퍼 유닛의 `RuntimeDirectory` 가 만드는 자리와 웹이 거는 소켓이 같아야 한다.

    systemd 는 `RuntimeDirectory=X` 를 `/run/X` 로 만든다. 이 둘이 어긋나면 웹은 오류
    없이 «도우미가 없습니다» 만 보여 주고, 관리 콘솔의 시스템 설정이 통째로 죽는다.
    """
    text = (UNIT_DIR / product.PRIVHELPER_UNIT).read_text(encoding="utf-8")
    assert f"RuntimeDirectory={product.SLUG}\n" in text
    assert product.PRIVHELPER_SOCKET.startswith(product.RUN_DIR + "/")
    assert f"Environment=CLOVIRASSIST_PRIVHELPER_SOCKET={product.PRIVHELPER_SOCKET}" in text
    assert f"Environment=CLOVIRASSIST_SERVICE_USER={product.SERVICE_USER}" in text


def test_the_helper_can_write_the_places_its_actions_touch():
    """액션 표가 건드리는 경로가 `ReadWritePaths` 에 없으면 **런타임에** 조용히 실패한다."""
    text = (UNIT_DIR / product.PRIVHELPER_UNIT).read_text(encoding="utf-8")
    rw = next((ln for ln in text.splitlines() if ln.startswith("ReadWritePaths=")), "")
    assert rw, "헬퍼에 ReadWritePaths 가 없다"
    for needed in ("/etc/hosts", "/etc/systemd", product.SSL_FALLBACK_DIR,
                   product.TLS_DIR, product.LOG_DIR, product.BACKUP_DIR, product.RUN_DIR):
        assert needed in rw, f"액션이 쓰는 경로가 빠졌다: {needed} / 실제: {rw}"


def test_the_console_can_only_control_units_that_exist():
    """관리 콘솔의 서비스 제어 목록에 없는 유닛 이름이 있으면 그 버튼은 조용히 실패한다."""
    from app.sysops.actions_service import MANAGED_UNITS, SELF_UNIT

    ours = {u for u in MANAGED_UNITS if u.startswith(product.SLUG)}
    assert ours <= set(product.ALL_UNITS), f"제품 유닛이 아닌 이름이 있다: {ours - set(product.ALL_UNITS)}"
    assert SELF_UNIT == product.WEB_UNIT


def test_the_deploy_assets_carry_no_legacy_identity():
    """CLAUDE.md §0 — Product-owned Deployment 자산에 옛 정체성을 남기지 않는다."""
    for path in [INSTALL_SH, NGINX_CONF, ENV_EXAMPLE, ROOT / "deploy" / "nginx" / "logrotate-clovirassist"]:
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            if "clovirone" not in line:
                continue
            # 셋만 예외다: ① 이전 경로가 옛 이름을 알아야 옮길 수 있다(LEGACY_*),
            # ② n8n 웹훅 경로는 **n8n 이 정한 이름**이라 제품 slug 를 안 따른다(S11 이 걷어낸다),
            # ③ 그 사실을 적어 둔 주석.
            assert ("LEGACY" in line or "clovirone-work-assistant" in line
                    or "clovirone-notion" in line or line.lstrip().startswith("#")), (
                f"{path.name}:{line_no} 에 옛 정체성이 있다: {line.strip()}"
            )


def test_the_env_example_matches_the_paths_the_installer_creates():
    """설치 스크립트가 만드는 디렉터리와 앱이 읽는 디렉터리가 같은 값이어야 한다."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for key, expected in (("CONFIG_DIR", product.ETC_DIR),
                          ("SECRETS_DIR", product.SECRETS_DIR),
                          ("DATA_DIR", product.VAR_DIR)):
        assert f"{key}={expected}\n" in text, f"{key} 가 {expected} 가 아니다"


def test_the_nginx_template_serves_the_certificate_the_installer_writes():
    """S3 이 찾은 조용한 무동작: nginx 가 읽는 인증서 경로와 설치 스크립트가 쓰는 자리가
    다르면 인증서 교체가 «성공» 을 보고하면서 아무것도 안 바꾼다."""
    text = NGINX_CONF.read_text(encoding="utf-8")
    assert f"ssl_certificate     {product.TLS_DIR}/__DNS_NAME__.crt" in text
    assert f"ssl_certificate_key {product.TLS_DIR}/__DNS_NAME__.key" in text
