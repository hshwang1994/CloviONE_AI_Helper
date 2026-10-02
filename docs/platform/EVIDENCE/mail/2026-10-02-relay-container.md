# ClovirAssist 로컬 릴레이 실측 — 실제 Postfix · systemd · apt (P14, D-551) — 2026-10-02

> 개발 PC 의 Docker 로 Ubuntu 24.04(postfix 3.8.6-1ubuntu0.1, opendkim 2.11.0~beta2-9build4)를 띄워 쟀다. 랩 서버는 건드리지 않았다
> (랩 실측 E2E-2 · E2E-3 은 P18). 비밀 값 · 실제 주소는 없다(도메인은 `example.test`).

## 1. 설정 파일과 보안 계약 넷 — `scripts/ui_qa/relay_container_e2e.py` (17/17)

`app/mail/relay_files.py` · `relay_certs.py` 가 만든 main.cf · master.cf · 인증서 · DKIM 키를 그대로 얹고 실제 연결로 확인했다.

| 확인 | 결과 |
|---|---|
| 설치 직후 main.cf 없음(debconf No configuration) | 통과 |
| `postfix check` 경고 없음 · `postfix start` | 통과 |
| 듣는 소켓 = `127.0.0.1:2525`(+ 서명 `127.0.0.1:8891`)뿐, 25번 없음 | 통과 |
| 앱 클라이언트 인증서로 바깥 도메인 받는 사람 허가(RCPT 250) | 통과 |
| 인증서 없는 보안 연결 → `554 5.7.1 … Access denied` | 통과 |
| 보안 연결 없이 MAIL → `530 5.7.0 Must issue a STARTTLS command first` | 통과 |
| 다른 OS 사용자(인증서 없음) → 554 | 통과 |
| 다른 OS 사용자의 `sendmail` → `sendmail: fatal: User tester(1001) is not allowed to submit mail` | 통과 |
| 인증서로 보낸 메일 접수(`250 2.0.0 Ok: queued as …`) · 받는 도메인별 전달 서버로 전달 · DKIM 서명(`s=ca1`) | 통과 |
| 컨테이너 바깥 주소에서 2525 연결 거절 | 통과 |
| 닫힌 전달 서버로 가는 메일은 큐에 남음(`postqueue -j` 지연 까닭) · 해석 못 하는 도메인은 5.4.4 반송 | 통과 |
| `authorized_submit_users` 빈 목록 | 통과 |

실제 로그 줄과 큐 JSON 은 분류기 시험의 견본이 됐다(`tests/fixtures/mail_relay/`).

## 2. 설치기 · 헬퍼 · 앱 전송기 끝에서 끝까지 — `scripts/ui_qa/relay_systemd_e2e.py` (24/24)

systemd 를 PID 1 로 띄운 컨테이너에서 제품이 실제로 하는 일을 그대로 돌렸다.

| 단계 | 확인 | 결과 |
|---|---|---|
| 설치기 `install_mail_relay` | 꾸러미 셋 설치 · postfix · opendkim disabled · 세 유닛 inactive · 메일 포트를 듣는 것 없음 · main.cf 없음 | 통과 |
| | 원래 있던 policy-rc.d(공식 이미지의 것)는 그대로이고 mask 는 풀림 · 다시 돌려도 무해 | 통과 |
| 헬퍼(실제 실행기, root) | 상태 「준비됨」 · DKIM 키 opendkim 0600 · 켜기 · 켠 뒤 「동작 중」 · 받는 문 2525 와 8891 뿐 | 통과 |
| 앱 전송기 | 로컬 릴레이 방식 설정 + 비밀 칸의 클라이언트 열쇠 + 고정 서버 인증서로 한 통 넘김(큐 id) · 연결 확인(봉투 시험) | 통과 |
| 받는 쪽 | 받는 도메인별 전달 서버로 도착 · DKIM 서명 | 통과 |
| 추적 | `mailrelay.log` 가 그 큐 id 를 「전달함」으로 요약 | 통과 |
| 끄기 | 끈 뒤 「준비됨」 · 릴레이 받는 문 없음 · 다음 부팅에도 안 뜸(disabled) | 통과 |
| 다른 MTA | exim4 가 있는 서버에서 설치기는 postfix 를 깔지 않음 | 통과 |

## 3. 실측이 찾아 고친 것

1. **꾸러미 기본 opendkim.conf 를 기존 서명 설정으로 읽었다.** Ubuntu 꾸러미의 기본 파일은 `#KeyFile …` 같은 예시를 주석으로 든다. 판정이
   주석까지 훑어 DKIM 서명을 켜는 적용이 거절됐다 — 주석이 아닌 지시만 본다(`_opendkim_is_ours_or_default`, 단위 시험).
2. **끄기가 남의 25번을 우리 것으로 셌다.** 받는 쪽(시험용)이 25번을 듣자 「끄지 못했습니다」였다. 우리는 25번을 듣는 적이 없다 — 끄기는
   2525 · 8891 만 본다(단위 시험).
3. **설계 중 찾은 빈틈**: 클라이언트 인증서만으로는 같은 서버의 사용자가 `sendmail` 명령으로 큐에 넣는 길이 남는다 —
   `authorized_submit_users =` 와 `pickup` 제거로 닫았고 1 의 표가 그 거절을 실제로 보였다.
4. 시험 환경의 함정(제품 결함 아님): 받는 도메인별 전달 서버를 `127.0.0.1:25` 로 두면 Postfix 가 「loops back to myself」(5.4.6)로
   반송한다 — 하네스는 `127.0.0.2` 를 쓴다.

## 4. 남은 것(P18 랩)

- E2E-2: 랩 배포 뒤 꾸러미 설치 · 기본 꺼짐 실측.
- E2E-3: 「인터넷으로 직접 전달」 + 받는 도메인별 전달 서버(`goodmit.co.kr` → 공개 MX, 랩은 분리 DNS) → 시험 메일 → 단계 보고 → 사용자의
  받은 편지함 확인. 랩의 바깥 조건(PTR 없음 · 공개 HELO 없음)으로 정크 · 격리가 될 수 있다(`2026-10-01-lab-preflight.md`).
