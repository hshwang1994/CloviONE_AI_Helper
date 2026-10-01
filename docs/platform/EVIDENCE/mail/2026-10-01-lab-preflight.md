# 랩 메일 사전 점검 (M5 E2E-1) — 2026-10-01

> 대상 랩 운영 설치 `clovirassist.gooddi.lab`(10.100.64.71). **읽기 전용**이고 아무것도 설치하거나 바꾸지 않았다.
> 비밀은 읽지 않았고, 공인 IP 는 끝자리를 가렸다. 계획 정본의 M5 · M7 이 이 결과를 쓴다.

## 메일 구성 요소

| 점검 | 결과 |
|---|---|
| 설치된 MTA | 없음 — postfix · opendkim · exim4 · sendmail · opensmtpd · nullmailer · msmtp-mta 꾸러미가 없고, `mail-transport-agent` 를 제공하는 꾸러미도 없다 |
| 유닛 | `postfix.service` · `postfix@-.service` · `opendkim.service` 모두 not-found |
| 듣는 소켓 | 25 · 2525 · 587 · 465 · 8891 에 없음 |
| apt 후보 | postfix `3.8.6-1ubuntu0.1`, opendkim `2.11.0~beta2-9build4` |
| 도구 경로 | `postconf` · `postfix` · `postqueue` · `postmap` 없음(설치 전), `journalctl` = `/usr/bin/journalctl`, `dpkg-query` = `/usr/bin/dpkg-query` |
| 방화벽 | ufw inactive |
| 저널 | 영속(`/var/log/journal` 있음) — 로컬 릴레이 추적이 지난 기록을 읽을 수 있다 |

→ 기본 설치 · 기본 꺼짐(D-551)을 적용하면 「다른 MTA 가 있어 건너뜀」 갈래가 아니라 새로 설치하는 갈래를 탄다.

## DNS

| 점검 | 결과 |
|---|---|
| 시스템 해석기 | `10.100.64.251` |
| `goodmit.co.kr` MX(시스템 해석기) | 없음 — 「Name 'goodmit.co.kr' does not have any RR of the requested type」 |
| `goodmit.co.kr` A(시스템 해석기) | 없음 |
| `goodmit-co-kr.mail.protection.outlook.com` | 풀린다(IPv6 주소가 먼저 나온다) |
| `smtp.office365.com` | 풀린다 |

→ 내부 해석기가 `goodmit.co.kr` 영역을 따로 들고 MX 를 주지 않는다(분리 DNS). 로컬 릴레이의 인터넷 직접 전달은 MX 를 찾지 못해 DNS 단계에서 멈춘다.
그래서 M7 의 「받는 도메인별 전달 서버」(`goodmit.co.kr → [goodmit-co-kr.mail.protection.outlook.com]:25`)가 실측에 필요하다.

## 바깥 연결

| 점검 | 결과 |
|---|---|
| `goodmit-co-kr.mail.protection.outlook.com:25` | 열림 |
| `smtp.office365.com:587` | 열림 |
| `smtp.gmail.com:587` | 열림 |
| 프록시 환경 변수 | 없음 |
| 바깥 IP | `221.147.80.x`(공인, 끝자리 가림) |
| 바깥 IP 의 PTR | **없음** |
| 서버 이름 | `clovirassist.gooddi.lab` — 공개 DNS 이름이 아니다 |

→ 바깥 25번은 막혀 있지 않다. PTR 이 없고 HELO 로 쓸 공개 이름이 없어서, Exchange Online 이 받더라도 정크 메일이나 격리로 보낼 수 있다.
이것은 P18 E2E-3 에서 실제로 보내 보고 받은 편지함 · 정크 메일 · 격리 중 어디였는지 기록한다.
