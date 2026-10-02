# ClovirAssist 로컬 릴레이 랩 실측 — 배포 · 기본 꺼짐 · 보안 계약 · 실제 발송 (P18, D-552) — 2026-10-02

> 랩 서버(`clovirassist.gooddi.lab`)에 이번 회차를 올리고 메일 구성 요소를 실제로 켜서 사용자의 회사 주소로 시험 메일 한 통을 보냈다.
> 주소는 가렸다(`h****g@goodmit.co.kr`). 비밀 값은 없다. 측정 도구는 `scripts/ui_qa/lab_mail_e2e.py`(시험 메일 한 통 · `--track` 은 이미 보낸
> 한 통의 단계만 다시 읽는다)이고 결과 원본은 `dist/ui-qa/lab-mail-e2e/result*.json`(gitignore, 주소는 가린 채 저장)이다.

## 1. 배포와 기본 꺼짐(E2E-2)

`c7777553` 을 `git archive` → `install.sh upgrade --source local --yes` 로 올렸다. `UPGRADE_OK` · `VERIFY_OK` · `DEPLOY_VERIFY_OK`(정적 자산
57/57), alembic `0048`.

| 확인 | 결과 |
|---|---|
| 꾸러미 | postfix 3.8.6 · opendkim 2.11 설치됨, 다른 MTA 없음 |
| 유닛 | postfix · opendkim disabled · inactive. `postfix@-` 는 생성기가 만든 enabled-runtime(postfix.service 의 WantedBy)이고 inactive |
| 듣는 소켓 | 25 · 2525 · 8891 없음 |
| 설정 파일 | main.cf 없음(debconf 「No configuration」) |
| 화면 | 메일 › 설정의 로컬 릴레이 「구성 요소 준비됨」 |

## 2. 보안 계약 넷 — 랩의 실제 Postfix 로 켠 뒤

| 계약 | 확인 | 결과 |
|---|---|---|
| 외부에서 접근할 수 없다 | 개발 PC 에서 랩의 25 · 2525 · 8891 연결 | 모두 닫힘 |
| ClovirAssist 만 쓸 수 있다 | 앱 → 릴레이 연결 확인(클라이언트 인증서 · 봉투 시험) | 정상 |
| 열린 중계가 될 수 없다 | 인증서 없는 보안 연결로 바깥 주소 중계 | `554 5.7.1 … Access denied` |
| | 보안 연결 없이 MAIL | `530 … Must issue a STARTTLS command first` |
| 일반 로컬 프로세스가 임의로 발송할 수 없다 | 다른 OS 사용자의 `sendmail` | `User cloviradmin(1000) is not allowed to submit mail` |

## 3. 준비 점검 — 「인터넷으로 직접 전달(고급)」 + 받는 도메인별 전달 서버(goodmit.co.kr → 공개 MX)

| 점검 | 상태 | 문장 |
|---|---|---|
| 메일 발송 구성 요소 · 로컬 릴레이 동작 · 받는 문 · 앱에서 릴레이로 | 정상 | 받는 문은 127.0.0.1:2525 하나이고 25번은 닫혀 있습니다. |
| 바깥 IP | 정상 | 받는 쪽은 이 서버를 221.147.80.201 로 봅니다. |
| 바깥 25번 연결 | 정상 | goodmit-co-kr.mail.protection.outlook.com 의 25번에 연결할 수 있습니다. |
| 받는 쪽 메일 서버(MX) | 정상 | 받는 도메인별 전달 서버로 보냅니다(랩 내부 DNS 에는 MX 가 없다 — 분리 DNS). |
| 보내는 도메인 · SPF · DMARC | 주의 | 이 서버의 DNS 에서 찾지 못했습니다 · SPF 레코드가 없습니다 · DMARC 레코드가 없습니다. |
| DKIM | 주의 | DKIM 서명을 쓰지 않습니다. |
| 역방향 이름(PTR) | 실패 | 공인 IP 의 역방향 이름(PTR)이 없습니다. |
| 서버 이름(HELO) | 주의 | clovirassist.gooddi.lab 이 다른 IP 로 풀립니다. |

SPF · DMARC · HELO 세 줄은 이 서버의 내부 해석기로 본 값이라 받는 쪽이 보는 사실과 달랐다. 공개 DNS 의 goodmit.co.kr 에는 SPF(이 IP 를
허가하지 않고, 셋째 include 가 도메인이 아니다)와 DMARC(`p=none`)가 있고, 받는 쪽에게 `.lab` 이름은 아예 없는 이름이다. 그 말대로 새 SPF 를
넣으면 공개 DNS 에 SPF 가 둘이 되어 레코드 오류가 된다. 이 결함은 이번에 고쳤다(5절).

## 4. 실제 발송 — 시험 메일 한 통(받는 주소 h****g@goodmit.co.kr)

| 단계(D-555) | 결과 |
|---|---|
| ① 보낼 차례 → ② 보내는 중 | 큐 등록 · 잡 실행 |
| ③ 로컬 릴레이가 접수함 | `250 2.0.0 Ok: queued as C6C5E4219A8` · Message-ID `<179093248580.760548.…@goodmit.co.kr>` |
| ④ 수신측 메일 서버로 전달함 | Exchange Online `250 2.6.0 … Queued mail for delivery`(2026-10-02 18:15 KST) · 발송 기록 · 상태 면 낱말 「수신측 메일 서버로 전달함」 |
| ⑤ 반송 | 제품이 추적하지 않는다(반송은 보내는 주소의 메일함으로 간다) |
| ⑥ 받은 편지함 | **사용자가 받은 편지함 · 정크에서 찾지 못했다 — 격리로 본다**(사용자 답 「격리 · 못 찾음」) |

까닭은 바깥 조건이다(제품 결함이 아니다). 보내는 주소가 받는 쪽과 같은 도메인인데 그 도메인의 공개 SPF 가 이 서버 IP 를 허가하지 않고,
DKIM 서명이 없으며, 공인 IP 에 역방향 이름이 없고, HELO 가 공개 이름이 아니다. Exchange Online 은 이런 같은 도메인 발신을 사칭으로 보고 격리할
수 있다. 받은 편지함까지 닫으려면 넷 중 하나가 필요하다: 외부 SMTP(회사 M365 계정 — E2E-4) · 상위 SMTP 이용 · 직접 전달을 계속한다면 PTR 등록과
SPF 에 이 IP 합치기와 DKIM 공개키 등록과 공개 HELO 이름. 격리 메일은 M365 관리자가 위 Message-ID 로 찾아 판정 까닭을 볼 수 있다.

## 5. 이번에 고친 준비 점검(D-551 보정)

보내는 도메인 · SPF · DKIM · DMARC · 역방향 이름 · 서버 이름을 **받는 쪽이 보는 DNS** 로 판정한다. 비교할 공개 DNS 서버가 그 도메인을 알면 그것으로
보고, 이 서버의 DNS 만 그 도메인을 알면 그것으로 본다. 어느 조회기도 모르면 SPF · DKIM · DMARC 는 「모름」이고 비교할 공개 DNS 서버를 넣으라고
말하며, 기존 레코드를 모르는 채 새 SPF · DMARC 를 제안하지 않는다. 합친 SPF 제안은 대상이 도메인이 아닌 include · redirect 를 빼고 그 사실을
레코드 아래 한 줄(`note`)로 말한다. 시험: `tests/unit/test_mail_relay_parts.py`(랩 모양의 분리 DNS · 반례 · 옛 판정 유지 · 도메인이 아닌 항목 빼기),
`frontend/src/screens/mail/relay-section.test.jsx`.

## 6. 고쳐 다시 올린 뒤의 점검(`1dc64099`, 같은 설정 · 메일은 보내지 않음)

| 점검 | 상태 | 문장 |
|---|---|---|
| 보내는 도메인 | 정상 | 보내는 도메인(goodmit.co.kr)을 공개 DNS 에서 찾았습니다. 이 서버의 DNS 는 이 도메인을 모릅니다(분리 DNS). |
| SPF | 실패 | 보내는 도메인의 SPF 레코드에 오류가 있습니다. |
| DKIM | 주의 | DKIM 서명을 쓰지 않습니다. |
| DMARC | 정상 | DMARC 레코드가 있습니다(정책 none). |
| 역방향 이름(PTR) | 실패 | 공인 IP 의 역방향 이름(PTR)이 없습니다. |
| 서버 이름(HELO) | 실패 | 서버 이름(clovirassist.gooddi.lab)이 DNS 에 없습니다. |

받는 쪽이 보는 사실과 같다. 공개 SPF 는 `include:spf.protection.outlook.com include:mail.stibee.com include:google-site-verification=…` 이고 셋째 항목이
도메인이 아니라 레코드 전체가 오류다(계획 단계의 관찰과 같다). 이 점검의 합친 SPF 제안은 그 항목을 그대로 옮겨 제안도 오류였다 — 위 5절의 마지막
보정이 그것을 고쳤다.

`9a555d8d` 를 올린 뒤 같은 점검의 SPF 줄은 할 일 「도메인이 아닌 항목을 빼세요. 아래 레코드는 그 항목을 뺀 제안입니다.」이고, 제안은
`v=spf1 ip4:221.147.80.201 include:spf.protection.outlook.com include:mail.stibee.com -all` 이다(도메인이 아닌 항목을 뺐다는 한 줄이 레코드 아래에
선다). 이 제안을 넣어도 받은 편지함까지 가려면 PTR · DKIM · 공개 HELO 이름이 함께 필요하다(P-126).

## 7. 시험 뒤 랩 상태

랩의 사용자는 실제 동료 주소라 알림 메일이 나가지 않게 처음 상태(메일을 설정한 적 없음 = 외부 SMTP · 발송 꺼짐)에 가깝게 되돌렸다.

| 확인 | 결과 |
|---|---|
| 메일 설정 | 보내는 방법 「외부 SMTP 사용」, 메일 발송 꺼짐, 건강 「사용 안 함」. 로컬 릴레이 값(전달 방식 · 전달 서버 · 비교할 공개 DNS)은 남아 있어 메일 화면에서 다시 고르면 그대로 쓴다 |
| 로컬 릴레이 | 「구성 요소 준비됨」(설치됨 · 꺼짐) — postfix · opendkim disabled · inactive, 25 · 2525 · 8891 을 듣는 것 없음 |
| QA 계정 | `ui-qa@goodmit.co.kr` 보관, 서버의 계정 도우미 파일 삭제 |
| 배포 | `c7777553` → `1dc64099`(랩 결함 수정) → `9a555d8d`(SPF 제안 · 프로브), 세 번 모두 `UPGRADE_OK` · `VERIFY_OK` · `DEPLOY_VERIFY_OK`(정적 자산 57/57) |
