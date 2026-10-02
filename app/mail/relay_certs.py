"""로컬 릴레이의 인증서와 DKIM 키 (계획 M7, D-551).

특권 헬퍼가 `mailrelay.apply` · `mailrelay.dkim_generate` 에서 부른다. 순수 함수이고 파일을 만지지 않는다.

- **서버 인증서**(릴레이의 받는 문): 자체 서명, 주소 `127.0.0.1` · 이름 `localhost`. 앱은 이 인증서 하나만 믿는다(고정) - 다른 로컬
  프로세스가 2525 를 먼저 차지해도 앱은 그쪽에 메일을 넘기지 않는다.
- **클라이언트 인증서**(앱만 가진 열쇠): 자체 서명, 용도는 클라이언트 인증. 릴레이는 이 인증서의 SHA-256 지문 하나만 중계를
  허가한다(`relay_clientcerts`). 키와 인증서는 한 PEM 으로 비밀 칸(`smtp.relay_client`)에 산다 - 웹 · 워커만 그룹 권한으로 읽는다.
- **DKIM 키**: RSA-2048. 개인키는 opendkim 만 읽고, 화면에는 공개키(DNS TXT 의 `p=`)만 나간다.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

SERVER_NAME = "clovirassist-relay"
CLIENT_NAME = "clovirassist-app"
VALID_DAYS = 3650
DKIM_BITS = 2048


def _now(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _key_pem(key) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ).decode("ascii")


def _cert_pem(cert: x509.Certificate) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _builder(name: str, key, now: datetime) -> x509.CertificateBuilder:
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    start = _now(now) - timedelta(minutes=5)
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(start + timedelta(days=VALID_DAYS))
    )


def make_server_cert(now: datetime | None = None) -> tuple[str, str]:
    """`(인증서 PEM, 키 PEM)`. 앱이 이 인증서 자체를 믿는 뿌리로 쓰므로(고정) CA 표시를 단다 - 자체 서명 잎을 신뢰 뿌리로 둘 때
    OpenSSL 이 요구하는 모양이다."""
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        _builder(SERVER_NAME, key, now)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_cert_sign=True, crl_sign=False, content_commitment=False,
            key_encipherment=False, data_encipherment=False, key_agreement=False, encipher_only=False,
            decipher_only=False,
        ), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return _cert_pem(cert), _key_pem(key)


def make_client_bundle(now: datetime | None = None) -> str:
    """앱의 클라이언트 열쇠 — 키 다음에 인증서가 오는 PEM 하나(`ssl.SSLContext.load_cert_chain` 이 파일 하나로 읽는다)."""
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (
        _builder(CLIENT_NAME, key, now)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return _key_pem(key) + _cert_pem(cert)


def _first_cert(pem: str) -> x509.Certificate:
    start = pem.find("-----BEGIN CERTIFICATE-----")
    if start < 0:
        raise ValueError("인증서가 없습니다.")
    return x509.load_pem_x509_certificate(pem[start:].encode("ascii"))


def fingerprint(pem: str) -> str:
    """Postfix 의 `smtpd_tls_fingerprint_digest = sha256` 지문 — DER 의 SHA-256 을 대문자 16진수 두 자리씩 콜론으로."""
    der = _first_cert(pem).public_bytes(serialization.Encoding.DER)
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def cert_usable(pem: str | None, now: datetime | None = None, *, margin_days: int = 30) -> bool:
    """읽을 수 있고, 만료까지 `margin_days` 일 넘게 남았는가. 아니면 헬퍼가 새로 만든다."""
    if not pem:
        return False
    try:
        cert = _first_cert(pem)
    except ValueError:
        return False
    return cert.not_valid_after_utc - _now(now) > timedelta(days=margin_days)


def make_dkim_key() -> str:
    """DKIM 개인키(PKCS#1 PEM — `opendkim-genkey` 와 같은 모양)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=DKIM_BITS)
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption(),
    ).decode("ascii")


def dkim_public(private_pem: str) -> str:
    """DNS TXT 의 `p=` 값 — SubjectPublicKeyInfo DER 의 base64."""
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode("ascii")


def dkim_txt(public_b64: str) -> str:
    return f"v=DKIM1; k=rsa; p={public_b64}"


def txt_chunks(value: str, size: int = 255) -> list[str]:
    """DNS TXT 의 문자열 한 조각은 255자까지다 - 긴 DKIM 값은 조각으로 나눠 넣는다."""
    return [value[i:i + size] for i in range(0, len(value), size)] or [""]
