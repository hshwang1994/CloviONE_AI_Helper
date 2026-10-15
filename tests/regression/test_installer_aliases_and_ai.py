"""설치기 — 함께 쓰는 이름(별칭, D-573) · 엄격한 매니페스트 · AI 상태 이어 가기(D-570).

셸 함수는 설치 스크립트에서 떼어 bash 로 실제로 돌린다(`test_installer_contract.py` 와 같은 방식). 나머지는 스크립트의 구조를 읽는다.

못박는 성질:
1. `--alias-name` 을 받고 도움말에 있다. 주지 않으면 manifest 의 `alias_names` 를 되살리고, `none` 은 지운다. 대표 이름 · 중복은 버린다.
2. 별칭은 도메인 이름만 받는다(IP · 밑줄 · 빈 라벨은 거절). 안 풀리는 별칭은 실패가 아니라 알림이다.
3. Stage 15 의 SAN 은 이름 전부 + 주소이고, 이름이 빠진 인증서는 자체 서명일 때만 새로 만든다(남이 발급한 것은 멈춘다).
4. Stage 16 은 `__SERVER_NAMES__` 를 채우고 이름마다 「우리 블록 둘」을 정확한 이름으로 센다. verify 는 별칭마다 TLS 검증까지 한다.
5. `json_str` 은 CR · 제어 문자를 걷어 매니페스트가 언제나 엄격한 JSON 이다. VERSION 은 CR 없이 읽는다.
6. upgrade 는 AI 옵션이 없으면 지금 AI 상태를 이어 간다(env `AI_ENABLED=true` 또는 manifest `with_ai`). 끄는 것은 `--without-ai`
   로만 한다. install 은 예전 뜻 그대로다. `ai` 명령은 떠 있는 web · 배치 · 대화형 유닛도 다시 시작한다.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.regression

ROOT = pathlib.Path(__file__).resolve().parents[2]
INSTALL = ROOT / "deploy" / "install.sh"
TEMPLATE = ROOT / "deploy" / "nginx" / "clovirassist.conf"
GIT_BASH = pathlib.Path(r"C:\Program Files\Git\bin\bash.exe")
BASH = shutil.which("bash") if not GIT_BASH.exists() else str(GIT_BASH)

needs_bash = pytest.mark.skipif(not BASH, reason="bash 없음 — 셸 함수를 실행할 수 없다")


def _text() -> str:
    return INSTALL.read_text(encoding="utf-8")


def _function(name: str) -> str:
    text = _text()
    head = f"{name}() {{"
    assert head in text, f"설치 스크립트에 {name} 가 없다"
    return head + text.split(head, 1)[1].split("\n}\n", 1)[0] + "\n}\n"


def _dispatch(sub: str) -> str:
    """맨 끝 `case "$SUBCOMMAND" in` 의 한 갈래."""
    tail = _text().split('case "$SUBCOMMAND" in\n  preflight)', 1)[1]
    return tail.split(f"\n  {sub})", 1)[1].split(";;", 1)[0]


def _ansi_c(value: str) -> str:
    """bash 의 `$'…'` 글자 — 백슬래시 · 따옴표 · 제어 문자를 그대로 나른다."""
    out = []
    for ch in value:
        code = ord(ch)
        if ch in "\\'":
            out.append("\\" + ch)
        elif 32 <= code < 127:
            out.append(ch)
        else:
            out.append(f"\\x{code:02x}" if code < 256 else f"\\u{code:04x}")
    return "$'" + "".join(out) + "'"


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    """스크립트는 표준 입력으로, 인자는 `set --` 의 `$'…'` 로 넘긴다. Windows 명령줄을 지나면 백슬래시가 든 함수 본문
    (`json_str`)과 인자가 바뀌어 bash 에 닿는다 — 이 파일의 첫 실행이 그것을 함수의 결함으로 잘못 읽었다."""
    head = ("set -- " + " ".join(_ansi_c(a) for a in args) + "\n") if args else ""
    done = subprocess.run([BASH, "-s"], input=(head + script).encode("utf-8"), capture_output=True)
    return subprocess.CompletedProcess(done.args, done.returncode, done.stdout.decode("utf-8", "replace"),
                                       done.stderr.decode("utf-8", "replace"))


# ── 1 · 2 별칭 옵션 ──────────────────────────────────────────────────────────


def test_the_alias_and_without_ai_options_are_parsed_and_documented():
    text = _text()
    loop = text.split("while [ $# -gt 0 ]; do", 1)[1].split("\ndone\n", 1)[0]
    assert "--alias-name) ALIAS_NAMES=" in loop
    assert "--without-ai) WITHOUT_AI=1" in loop
    usage = _function("usage")
    assert "--alias-name <name[,name…]>" in usage and "--without-ai" in usage


@needs_bash
@pytest.mark.parametrize(("given", "remembered", "expected"), [
    ("", "Old.Example.Internal,new.example.com,old.example.internal.", "old.example.internal"),
    ("none", "old.example.internal", ""),
    ("a.example.com, B.example.com", "old.example.internal", "a.example.com,b.example.com"),
    ("", "", ""),
])
def test_alias_names_come_back_from_the_manifest_and_none_clears_them(given, remembered, expected):
    script = (f'jq_get() {{ [ "$1" = alias_names ] && echo "{remembered}"; }}\n'
              + _function("resolve_alias_names")
              + 'DNS_NAME="New.Example.com"; ALIAS_NAMES="$1"; resolve_alias_names; printf "%s" "$ALIAS_NAMES"')
    result = _run(script, given)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


@needs_bash
@pytest.mark.parametrize(("name", "ok"), [
    ("old.example.internal", True), ("clovirassist.goodmit.co.kr", True), ("a-b.example.com", True),
    ("localhost", False), ("10.100.64.71", False), ("bad_name.example.com", False), ("a..example.com", False),
    ("-a.example.com", False), ("a.example.com;evil", False), ("", False),
])
def test_alias_names_must_be_domain_names(name, ok):
    result = _run(_function("alias_name_ok") + 'alias_name_ok "$1"', name)
    assert (result.returncode == 0) is ok, name


def test_the_preflight_refuses_bad_aliases_but_only_warns_about_unresolvable_ones():
    stage = _function("stage_0_preflight")
    assert 'alias_name_ok "$_alias" || fail' in stage
    assert 'getent hosts "$_alias" >/dev/null 2>&1 || note' in stage, "안 풀리는 별칭을 실패로 막는다"
    assert '-le 5' in stage, "별칭 상한(다섯)이 없다"


def test_install_upgrade_and_preflight_all_resolve_the_alias_list():
    for sub in ("install", "upgrade"):
        assert "resolve_alias_names" in _dispatch(sub), f"{sub} 가 별칭 목록을 정하지 않는다 — 재실행이 옛 이름을 지운다"
    upgrade = _dispatch("upgrade")
    assert upgrade.index('DNS_NAME="$(jq_get dns_name)"') < upgrade.index("resolve_alias_names"), \
        "대표 이름을 되살리기 전에 별칭을 정리한다 — 대표 이름이 별칭에 남는다"


# ── 3 · 4 인증서 · vhost · verify ─────────────────────────────────────────────


def test_stage_15_puts_every_name_in_the_san_and_only_regenerates_its_own_certificate():
    stage = _function("stage_15_tls")
    assert "for n in $(tls_names); do san=" in stage
    assert 'san="$san,IP:$BIND_IP"' in stage
    assert '-addext "subjectAltName=$san"' in stage
    assert "cert_has_name" in stage and "cert_self_signed" in stage
    regen = stage.index("if cert_self_signed")
    assert stage.index("regen=1", regen) < stage.index("fail ", regen), "자체 서명일 때 새로 만드는 갈래가 실패보다 먼저가 아니다"
    assert re.search(r'fail "기존 인증서의 SAN 에 \$missing 이 없습니다.*?36', stage, re.S), "남이 발급한 인증서를 바꿔 버린다"


def test_stage_16_fills_the_server_names_slot_and_checks_every_name():
    stage = _function("stage_16_nginx")
    assert 's/__SERVER_NAMES__/$server_names/g' in stage
    assert "__SERVER_NAMES__" in stage.split("if grep -q", 1)[1].split("\n", 1)[0], "치환이 남은 vhost 를 잡지 못한다"
    assert 'for n in $server_names; do' in stage and 'server_name_blocks "$n"' in stage
    template = TEMPLATE.read_text(encoding="utf-8")
    assert len(re.findall(r"^\s*server_name __SERVER_NAMES__;", template, re.M)) == 2, "템플릿의 server_name 블록이 둘이 아니다"
    assert "ssl_certificate     /etc/clovirassist/tls/__DNS_NAME__.crt;" in template, "인증서는 대표 이름 하나여야 한다"


DUMP = """# configuration file /etc/nginx/sites-enabled/clovirassist:
server {
    server_name new.example.com old.example.internal;
}
server {
    server_name new.example.com old.example.internal;
    # server_name new.example.com;
}
# configuration file /etc/nginx/sites-enabled/other:
server {
    server_name www.new.example.com example.com;
}
"""


@needs_bash
@pytest.mark.parametrize(("name", "count"), [
    ("new.example.com", "2"), ("old.example.internal", "2"), ("example.com", "1"), ("missing.example.com", "0"),
])
def test_server_name_blocks_counts_exact_names_only(name, count):
    """`grep \\bname\\b` 는 점을 아무 글자로 읽고 www.new.example.com 도 new.example.com 으로 셌다."""
    script = _function("server_name_blocks") + 'printf "%s" "$2" | server_name_blocks "$1"'
    result = _run(script, name, DUMP)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == count


def test_verify_checks_every_alias_with_a_pinned_address_and_the_served_san():
    verify = _function("do_verify")
    assert 'aliases="${ALIAS_NAMES:-$(jq_get alias_names)}"' in verify, "단독 verify 가 manifest 의 별칭을 안 본다"
    assert "--resolve $a:443:$BIND_IP https://$a/healthz" in verify
    assert "--cacert '$crt'" in verify.split("for a in ${aliases//,/ }; do", 1)[1], "별칭 확인이 TLS 검증을 하지 않는다"
    assert "-servername \"$a\"" in verify and "DNS:$a" in verify
    assert 'server_name_blocks "$a"' in verify


# ── 5 엄격한 매니페스트 ───────────────────────────────────────────────────────


@needs_bash
@pytest.mark.parametrize(("raw", "expected"), [
    ("0.1.0-dev\r", "0.1.0-dev"),
    ("line1\nline2\tend", "line1 line2 end"),
    ('quote " and back \\ slash', 'quote " and back \\ slash'),
    ("bell\x07 escape\x1b end", "bell escape end"),
])
def test_json_str_always_yields_strict_json(raw, expected):
    result = _run(_function("json_str") + 'json_str "$1"', raw)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected, result.stdout


def test_the_manifest_records_the_alias_list_and_the_ai_state_and_reads_version_without_cr():
    manifest = _function("write_manifest")
    assert '"alias_names": %s' in manifest and '"$(json_str "$ALIAS_NAMES")"' in manifest
    assert '"with_ai": %s' in manifest and '"$(json_str "$WITH_AI")"' in manifest
    assert "tr -d '\\r' <\"$APP_DIR/VERSION\"" in manifest, "VERSION 을 CR 째로 읽는다"
    assert 'cat "$APP_DIR/VERSION"' not in _text(), "CR 을 걷지 않고 VERSION 을 읽는 자리가 남았다"


# ── 6 AI 상태 (D-570) ─────────────────────────────────────────────────────────


@needs_bash
@pytest.mark.parametrize(("env_line", "remembered", "with_ai", "without_ai", "expected"), [
    ("AI_ENABLED=true", "", "0", "0", "1"),      # 지금 켜져 있으면 옵션 없는 upgrade 가 그대로 둔다(랩 결함)
    ('AI_ENABLED="true"', "", "0", "0", "1"),
    ("AI_ENABLED=false", "1", "0", "0", "1"),    # manifest 가 기억한다
    ("AI_ENABLED=false", "", "0", "0", "0"),     # 꺼져 있던 것은 켜지 않는다
    ("AI_ENABLED=false", "0", "1", "0", "1"),    # --with-ai 는 언제나 켠다
    ("AI_ENABLED=true", "1", "0", "1", "0"),     # 끄는 것은 --without-ai 로만
])
def test_an_upgrade_without_ai_options_keeps_the_current_ai_state(tmp_path, env_line, remembered, with_ai, without_ai,
                                                                    expected):
    env_file = tmp_path / "clovirassist.env"
    env_file.write_text(f"SECRET_KEY=x\n{env_line}\n", encoding="utf-8", newline="\n")
    script = (f'jq_get() {{ [ "$1" = with_ai ] && echo "{remembered}"; }}\n'
              + _function("resolve_with_ai")
              + f'ENV_FILE="$1"; WITH_AI={with_ai}; WITHOUT_AI={without_ai}; resolve_with_ai; printf "%s" "$WITH_AI"')
    result = _run(script, env_file.as_posix())
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


def test_upgrade_and_ai_resolve_the_ai_state_but_install_keeps_its_meaning():
    upgrade = _dispatch("upgrade")
    assert "resolve_with_ai" in upgrade and upgrade.index("resolve_with_ai") < upgrade.index("run_all_stages")
    assert "resolve_with_ai" not in _dispatch("install"), "install 의 뜻(옵션이 곧 상태)이 바뀌었다"
    ai = _dispatch("ai")
    assert ai.index("resolve_with_ai") < ai.index("ai_env_apply"), "`ai` 를 옵션 없이 돌리면 AI 를 끈다"


def test_the_ai_command_restarts_the_running_web_batch_and_conversational_units():
    ai = _dispatch("ai")
    assert 'systemctl restart "$INDEX_UNIT"' in ai
    loop = ai.split('for u in "$WEB_UNIT" "$WORKER_UNIT" "$WORKER_CONV_UNIT"; do', 1)
    assert len(loop) == 2, "web · 배치 · 대화형을 다시 시작하지 않는다 — web 이 「모델 없음」을 계속 말한다"
    body = loop[1].split("done", 1)[0]
    assert 'unit_active "$u" || continue' in body, "꺼져 있던 유닛을 켠다(대화형 레인은 꺼져 있는 것이 정상일 수 있다)"
    assert 'systemctl restart "$u"' in body


@needs_bash
def test_with_ai_and_without_ai_together_are_refused():
    result = subprocess.run([BASH, INSTALL.as_posix(), "upgrade", "--with-ai", "--without-ai"], capture_output=True,
                            text=True, encoding="utf-8")
    assert result.returncode == 64, (result.returncode, result.stdout, result.stderr)
    assert "함께 줄 수 없습니다" in result.stdout


def test_the_ai_command_records_the_ai_state_in_the_manifest():
    assert 'manifest_set with_ai "$WITH_AI"' in _dispatch("ai"), "ai 부명령이 매니페스트의 with_ai 를 안 고친다 — 매니페스트가 옛 상태를 말한다"


@needs_bash
@pytest.mark.parametrize("value", ["1", "0", 'a"b&c|d\\e'])
def test_manifest_set_replaces_one_string_value_and_keeps_the_file_strict_json(tmp_path, value):
    manifest = tmp_path / "m.json"
    manifest.write_text('{\n  "dns_name": "a.example.com",\n  "with_ai": "0",\n  "installed_at": "x"\n}\n', encoding="utf-8")
    script = ("MANIFEST=" + _ansi_c(manifest.as_posix()) + "\n" + _function("json_str") + _function("manifest_set")
              + 'manifest_set with_ai "$1"\nmanifest_set missing_key "$1"\n')
    done = _run(script, value)
    assert done.returncode == 0, done.stderr
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data == {"dns_name": "a.example.com", "with_ai": value, "installed_at": "x"}
