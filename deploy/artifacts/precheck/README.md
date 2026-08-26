# 사전 점검 산출물 — **이관 전 호스트의 기록이다**

이 디렉터리의 파일은 **역사 기록**이다. 설치기도 앱도 이것을 읽지 않는다.

`clovirone-system-inventory.json` 은 이 제품을 깔기 **전** 그 서버가 어떤 상태였는지를
`deploy/00-precheck.sh` 가 한 번 찍어 둔 것이다. 그래서 그 안에는 지금 제품에 없는 것들이
그대로 적혀 있다 — 옛 호스트명(`ai-n8n-svr`), 옛 유닛 넷(`n8n` · `claude-work-assistant` ·
`claude-ticket-runner` · `claude-request-interpreter`), 옛 서비스 계정.

**그 이름들은 이 제품의 구성요소가 아니다.** S11 이 그 런타임 넷을 걷었고 S14 가 Notion
런타임을 걷었다. 지금 이 서버에서 도는 것은 `clovirassist-*` 유닛 여섯뿐이다
(`deploy/install.sh` 의 `ALL_UNITS`).

이 기록을 남겨 두는 이유는 하나다: **이관이 무엇에서 무엇으로 갔는지**를 나중에 확인할
근거가 여기밖에 없다. 지우면 「그 서버에 원래 무엇이 있었나」에 답할 방법이 사라진다.

새 사전 점검을 돌리면 결과는 여기가 아니라 `/home/cloviradmin/clovirassist-precheck.md` 와
`/home/cloviradmin/clovirassist-system-inventory.json` 에 쌓인다.
