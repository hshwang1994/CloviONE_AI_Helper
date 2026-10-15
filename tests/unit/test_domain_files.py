"""대표 도메인 전환의 순수 함수 (계획 M3, D-573) — `app/sysops/domain_files.py`.

못박는 것:
1. env 파일은 설치기 `env_set` 과 같은 규칙으로 바뀐다(있으면 그 줄, 없으면 끝). 다른 줄은 그대로다.
2. 매니페스트는 **너그럽게 읽고 엄격하게 쓴다** — 랩의 매니페스트는 `"version": "0.1.0-dev\r"` 처럼 문자열 안에 날 CR 이 있어
   `json.loads` 가 「Invalid control character」 로 못 읽었다. 읽으면 CR 을 걷고, 다시 쓰면 `json.loads(strict=True)` 가 읽는다.
3. 다시 쓴 매니페스트도 설치기 `jq_get`(한 줄 sed)이 읽는 모양이다.
4. vhost 는 저장소 템플릿에서 만들고, server_name 에는 대표 이름 뒤에 별칭이, 인증서 경로에는 대표 이름 하나가 선다. 옛 틀(별칭 자리
   없음)은 거절한다.
5. `nginx -T` 출력에서 우리 vhost 의 이름과 **다른 설정 파일의 같은 이름**(충돌)을 가른다.
6. 자체 서명 openssl 호출은 설치기 Stage 15 와 같은 모양이고 SAN 은 이름 전부 + 주소다.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from app.sysops import domain_files as df

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "deploy" / "nginx" / "clovirassist.conf").read_text(encoding="utf-8")
INSTALL = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")


def test_env_set_replaces_in_place_and_appends_missing_keys():
    text = "SECRET_KEY=abc\nAPP_BASE_URL=https://old.example.internal\nDATA_DIR=/var/lib/x\n"
    out = df.env_set(text, "APP_BASE_URL", "https://new.example.com")
    assert out.splitlines() == ["SECRET_KEY=abc", "APP_BASE_URL=https://new.example.com", "DATA_DIR=/var/lib/x"]
    out = df.env_set(out, "TLS_CERT_PATH", "/etc/clovirassist/tls/new.example.com.crt")
    assert out.endswith("TLS_CERT_PATH=/etc/clovirassist/tls/new.example.com.crt\n")
    assert df.env_get(out, "APP_BASE_URL") == "https://new.example.com"


def test_env_get_takes_the_last_line_and_strips_quotes():
    text = 'APP_BASE_URL=https://a.example\nAPP_BASE_URL="https://b.example"\n'
    assert df.env_get(text, "APP_BASE_URL") == "https://b.example"
    assert df.env_get(text, "MISSING") is None
    assert df.env_get(None, "APP_BASE_URL") is None


def test_env_set_collapses_duplicate_lines_of_the_same_key():
    text = "A=1\nAPP_BASE_URL=x\nB=2\nAPP_BASE_URL=y\n"
    out = df.env_set(text, "APP_BASE_URL", "z")
    assert out == "A=1\nAPP_BASE_URL=z\nB=2\n"


def test_a_manifest_with_a_raw_carriage_return_inside_a_value_still_parses():
    """랩 실측: Windows 체크아웃 → `git archive` 로 보낸 VERSION 이 CRLF 였고 설치기의 `json_str` 이 CR 을 이스케이프하지 않았다."""
    raw = '{\n  "product": "ClovirAssist",\n  "version": "0.1.0-dev\r",\n  "dns_name": "old.example.internal",\n  "bind_ip": "10.0.0.5"\n}\n'
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)  # 엄격한 파서는 실제로 못 읽는다 — 이 시험의 전제
    data = df.parse_manifest(raw)
    assert data["version"] == "0.1.0-dev", "읽은 값에 CR 이 남았다"
    assert data["dns_name"] == "old.example.internal"
    rewritten = df.dump_manifest(data)
    assert json.loads(rewritten)["version"] == "0.1.0-dev", "다시 쓴 매니페스트가 엄격한 JSON 이 아니다"
    assert "\r" not in rewritten


def test_dump_manifest_stays_strict_json_even_with_control_characters():
    out = df.dump_manifest({"version": "1\r2\x01", "stages": [{"stage": 1, "reason": "a\tb"}]})
    assert json.loads(out)["version"] == "1\r2\x01", "제어 문자를 이스케이프하지 않았다"


def test_the_rewritten_manifest_is_readable_by_the_installers_jq_get():
    """설치기의 `jq_get` 은 `"key": "value"` 가 한 줄에 있어야 읽는다 — 목록 · 객체는 한 줄로 접는다."""
    data = {"product": "ClovirAssist", "dns_name": "new.example.com", "alias_names": "old.example.internal",
            "bind_ip": "10.0.0.5", "stages": [{"stage": 0, "name": "PREFLIGHT", "verdict": "OK"}]}
    text = df.dump_manifest(data)
    jq_get = re.search(r'jq_get\(\) \{\n.*?sed -n "s/(.*?)/\\1/p"', INSTALL, re.S)
    assert jq_get, "설치기의 jq_get 을 찾지 못했다"
    for key, value in (("dns_name", "new.example.com"), ("alias_names", "old.example.internal"), ("bind_ip", "10.0.0.5")):
        line = next(ln for ln in text.splitlines() if f'"{key}"' in ln)
        m = re.match(rf'^\s*"{key}":\s*"([^"]*)"', line)
        assert m and m.group(1) == value, f"{key} 줄을 jq_get 모양으로 못 읽는다: {line!r}"
    assert all(ln.count("{") <= 1 or "[" in ln for ln in text.splitlines()[1:-1]), "목록이 여러 줄로 퍼졌다"


def test_a_missing_or_broken_manifest_is_an_empty_dict():
    assert df.parse_manifest(None) == {}
    assert df.parse_manifest("") == {}
    assert df.parse_manifest("{not json") == {}
    assert df.parse_manifest("[1, 2]") == {}


def test_aliases_are_lowercased_deduplicated_and_never_the_canonical_name():
    assert df.normalize_aliases("new.example.com", ["Old.Example.Internal", "old.example.internal", "new.example.com", ""]) == [
        "old.example.internal"]
    assert df.split_names("a.example, B.example  a.example") == ["a.example", "b.example"]
    assert df.split_names(["x.example", "X.example"]) == ["x.example"]


def test_more_than_five_aliases_are_refused():
    names = [f"n{i}.example.com" for i in range(6)]
    with pytest.raises(ValueError, match="최대 5개"):
        df.normalize_aliases("main.example.com", names)
    assert len(df.normalize_aliases("main.example.com", names[:5])) == 5


def test_render_vhost_puts_aliases_after_the_canonical_name_and_keeps_the_cert_on_the_canonical_name():
    out = df.render_vhost(TEMPLATE, "10.0.0.5", "new.example.com", ["old.example.internal"])
    names = re.findall(r"^\s*server_name\s+([^;]+);", out, re.M)
    assert names == ["new.example.com old.example.internal"] * 2, "server_name 블록 둘(:80 · :443)이 아니다"
    assert "ssl_certificate     /etc/clovirassist/tls/new.example.com.crt;" in out
    assert "ssl_certificate_key /etc/clovirassist/tls/new.example.com.key;" in out
    assert "listen 10.0.0.5:443 ssl;" in out
    assert not any(p in out for p in df.PLACEHOLDERS)


def test_render_vhost_refuses_an_old_template_without_the_alias_slot():
    old = TEMPLATE.replace("server_name __SERVER_NAMES__;", "server_name __DNS_NAME__;")
    assert not df.template_supports_aliases(old)
    with pytest.raises(ValueError, match="옛 버전"):
        df.render_vhost(old, "10.0.0.5", "new.example.com", [])
    with pytest.raises(ValueError):
        df.render_vhost(TEMPLATE, "", "new.example.com", [])


def test_the_repository_template_has_the_alias_slot_in_both_blocks():
    assert df.template_supports_aliases(TEMPLATE)
    assert len(re.findall(r"^\s*server_name\s+__SERVER_NAMES__;", TEMPLATE, re.M)) == 2


NGINX_DUMP = """nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
# configuration file /etc/nginx/nginx.conf:
http {
    include /etc/nginx/sites-enabled/*;
}

# configuration file /etc/nginx/sites-enabled/clovirassist:
server {
    listen 10.0.0.5:80;
    server_name old.example.internal;
}
server {
    listen 10.0.0.5:443 ssl;
    server_name old.example.internal;
    # server_name commented.example.com;
}

# configuration file /etc/nginx/sites-enabled/other-app:
server {
    listen 10.0.0.9:443 ssl;
    server_name intranet.example.com new.example.com;
}
"""


def test_nginx_dump_is_split_by_file_and_our_server_names_are_found():
    sections = df.nginx_sections(NGINX_DUMP)
    assert set(sections) == {"/etc/nginx/nginx.conf", "/etc/nginx/sites-enabled/clovirassist",
                             "/etc/nginx/sites-enabled/other-app"}
    assert df.site_server_names(NGINX_DUMP) == ["old.example.internal"], "주석 줄이나 남의 vhost 이름이 섞였다"


def test_a_name_used_by_another_vhost_is_a_conflict():
    """같은 이름을 두 블록이 들면 nginx 는 먼저 읽은 쪽을 조용히 쓴다 — 적용이 성공한 듯 보이고 요청은 다른 서비스가 받는다."""
    assert df.name_conflicts(NGINX_DUMP, ["new.example.com", "old.example.internal"]) == [
        ("/etc/nginx/sites-enabled/other-app", "new.example.com")]
    assert df.name_conflicts(NGINX_DUMP, ["clean.example.com"]) == []


X509 = """subject=CN = old.example.internal
issuer=CN = old.example.internal
notAfter=Oct 15 00:00:00 2027 GMT
X509v3 Subject Alternative Name:
    DNS:old.example.internal, DNS:new.example.com, IP Address:10.0.0.5
"""


def test_parse_x509_reads_san_expiry_and_self_signed():
    info = df.parse_x509(X509)
    assert info["san"] == {"dns": ["old.example.internal", "new.example.com"], "ip": ["10.0.0.5"]}
    assert info["self_signed"] is True
    assert info["not_after"].startswith("2027-10-15T00:00:00")
    assert df.missing_names(info["san"], ["new.example.com", "third.example.com"]) == ["third.example.com"]
    issued = df.parse_x509(X509.replace("issuer=CN = old.example.internal", "issuer=C = US, O = Let's Encrypt, CN = R11"))
    assert issued["self_signed"] is False


def test_self_signed_argv_matches_the_installer_stage_15_shape():
    argv = df.self_signed_argv("/usr/bin/openssl", crt="/t/new.crt", key="/t/new.key", host="new.example.com",
                               names=["old.example.internal", "new.example.com"], bind_ip="10.0.0.5")
    assert argv[:7] == ["/usr/bin/openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256"]
    assert argv[argv.index("-subj") + 1] == "/CN=new.example.com"
    assert argv[argv.index("-addext") + 1] == "subjectAltName=DNS:new.example.com,DNS:old.example.internal,IP:10.0.0.5"
    assert argv[argv.index("-days") + 1] == "365"
    # 설치기 Stage 15 도 같은 곡선 · 기간 · 주체 모양이다.
    stage = INSTALL.split("stage_15_tls() {", 1)[1].split("\n}\n", 1)[0]
    for piece in ("-newkey ec -pkeyopt ec_paramgen_curve:P-256", "-days 365 -nodes", '-subj "/CN=$DNS_NAME"',
                  '-addext "subjectAltName=$san"'):
        assert piece in stage, f"설치기 Stage 15 와 모양이 다르다: {piece}"


def test_key_path_sits_next_to_the_certificate():
    assert df.key_path_for("/etc/clovirassist/tls/a.example.com.crt") == "/etc/clovirassist/tls/a.example.com.key"
    assert df.cert_paths("/etc/clovirassist/tls", "a.example.com") == (
        "/etc/clovirassist/tls/a.example.com.crt", "/etc/clovirassist/tls/a.example.com.key")
