# NGINX 요청 제한과 용량 — 근거 문서

> `deploy/nginx/clovirassist.conf` 가 두 번 참조하는 문서다(L34·L283 — 이 파일이
> 없던 동안 그 참조는 깨져 있었다). 존 값을 조이거나 풀기 전에 여기를 읽고, 바꾼
> 값과 근거를 여기에 함께 적는다. conf 의 주석 산정표는 프런트 폴링이 바뀔 때마다
> 낡는다 — 표의 정본은 이 문서다.

## 층이 둘이다 — 진단의 첫 갈래

429 를 내는 층은 둘이고 사용자 경험이 다르다.

| 층 | 응답 | 화면 문구 | 구분법 |
|---|---|---|---|
| nginx `limit_req` | **HTML** (봉투 없음) | fallback 「요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.」(`api.js`) | `Retry-After` 헤더 없음 · `error.log` 에 `limiting requests … zone "clv_api"` |
| 앱 토큰 버킷 (`app/core/ratelimit.py`) | JSON 봉투 + `retry_after_seconds` + `Retry-After` 헤더 | 리미터별 구체 문구(「로그인 시도가 너무 많습니다」 등) | `rate_limit_buckets` 표에서 `key` 접두로 확인 |

ErrorState 는 429 에서 대기 시간을 말하고 그동안 재시도를 잠근다(D-409). AI 사용
상한(`app/quotas/service.py`)도 코드는 같은 429 다 — retry_after 가 길다(시간~월).

## nginx 존 (2026-09-02 기준)

| 존 | 정의 | 적용 | 키 |
|---|---|---|---|
| `clv_api` | `rate=20r/s` | `location /` — `burst=40 nodelay` | 클라이언트 IP |
| `clv_login` | `rate=30r/m` | `/login` · `/change-password` — `burst=10 nodelay` | 클라이언트 IP |

`limit_req_status 429` · `/static/` 은 일부러 안 건다 · 첨부 업로드 location 들은
별도 location 이라 상속하지 않는다(의도된 제외).

## 🔴 per-IP 존은 앞단 프록시 · NAT 뒤에서 사무실 전체가 한 예산이다

키가 클라이언트 IP 라, NAT·VPN 게이트웨이 · 앞단 역방향 프록시 뒤에서는 전원이 20r/s 하나를 나눈다.
`trusted_proxy`(기본 127.0.0.1) 설정이 틀리면 `X-Real-IP` 가 프록시 주소로 굳어
같은 일이 앱 리미터(로그인 분당 10회)에서도 난다. 앱 쪽 완화는 D-409(성공 로그인
리셋)가 맡는다 — nginx 쪽은 값 조정 전에 `error.log` 의 `limiting` 빈도와 그 IP
분포를 먼저 잰다.

**실측(2026-09-21, 랩 서버 14일치 로그).** 제품 요청의 대부분이 앞단 프록시 한 주소(`10.100.64.96`)로
들어왔고, `clv_api` 로 걸린 429 약 15.8만 건이 전부 그 주소였다 — 같은 프록시를 지나는 취약점
스캐너가 하루 약 1만 건을 만들었다. 그 예산을 나눠 쓰던 실제 사용자 API 요청도 14일간 22건이
429 를 맞았고, 화면은 그 실패를 「500」 그림으로 그렸다(오류 그림을 정리하기 전이다).

**해법 — 키를 실제 사용자로 되돌린다. 제한값은 그대로다.** 설치 옵션
`--upstream-proxy <ip[,cidr…]>` 로 앞단 프록시를 알려 주면 Stage 16 이
`/etc/clovirassist/nginx/realip.conf` 에 `set_real_ip_from` · `real_ip_header X-Forwarded-For` ·
`real_ip_recursive on` 을 쓰고, vhost 의 443 블록이 `include /etc/clovirassist/nginx/realip*.conf`
로 그것을 읽는다. 목록은 manifest 가 기억하고(`upstream_proxies`) `none` 을 주면 지운다. 목록이
비면 주석만 든 파일이라 지금과 같다. `0.0.0.0/0` 처럼 모든 주소를 믿는 값은 설치기가 거절한다 —
그 값이면 누구나 `X-Forwarded-For` 로 자기 주소를 꾸며 속도 제한과 로그인 제한을 피한다.
앱의 `TRUSTED_PROXY` 는 그대로 127.0.0.1 이다: nginx 가 꺼낸 주소를 `X-Real-IP` 로 넘기므로 앱
리미터와 감사 로그의 IP 도 함께 실제 사용자로 돌아온다.

랩 서버에서 같은 존(`20r/s burst=40 nodelay`)으로 잰 결과(한 사용자당 동시 70건): 목록이 없으면 첫
사용자가 41건 통과한 직후 **둘째 사용자는 70건 중 1건만** 통과했다. 프록시를 믿게 하자 두 사용자가
**각자 41건씩** 통과했다. 설치처 적용은 다음 업그레이드 때 `--upstream-proxy 10.100.64.96` 을 주는 것이다.

## 앱 리미터 값 (정본: `app/main.py` — 하드코딩이다)

| 리미터 | capacity / 분당 회복 | 키 |
|---|---|---|
| login (+change_password·reset 공유) | 10 / 10 | IP (변경·재설정은 사용자/IP 별 키) |
| chat · team-chat(별도 버킷) | 20 / 30 | 사용자 |
| game_ai | 5 / 5 | 사용자 |
| assistant narrate | 6 / 12 | 사용자 |

값을 바꾸려면 코드 수정 + 재기동이다. 성공 로그인·비밀번호 변경은 자기 키를
리셋한다(D-409) — 실패 스프레이 예산은 그대로다.

## 폴링 산정 (프런트 상시 부하 — 값이 바뀌면 이 표를 갱신한다)

앱 셸(모든 화면): team-chat rooms 60s · 알림 배지(user/admin) 60s×2 · 내 결재함
60s · 임퍼소네이션 60s · 시스템 상태 120s · 공지 300s ≈ **분당 5.7회/탭**.
화면별 최고치: 게임방 1.2s · 놀이 목록 3s · 채팅방 2s(유휴 후퇴) · 회의 30s(신설,
D-410) · 홈/대시보드 30s. 홈은 `home-request-budget.test.jsx` 가 분당 ≤10 을
못박고, `polling-visibility.test.js` 가 배경 폴링 금지를 저장소 전체에서 지킨다.

## 값 조정 절차

1. `error.log` 의 `limiting` 줄로 층·IP 분포를 확인한다.
2. `rate_limit_buckets` 를 접두(`login:` 등)로 조회해 어느 버킷이 바닥인지 본다.
3. 값을 바꾸면 이 문서의 표와 근거를 같은 변경에서 갱신한다 — conf 주석이 아니라
   여기가 정본이다.
