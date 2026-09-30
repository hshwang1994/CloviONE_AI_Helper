# ClovirAssist

ClovirAssist 는 팀의 티켓, 프로젝트, 문서, 대화를 한곳에서 다루는 사내 업무 포털입니다. 문서를 근거로 답하는 AI 도우미
클로비가 함께 일하고, 관리자는 조직, 권한, 메일, AI 연결을 웹 화면에서 설정합니다.

## 요구 사항

- Ubuntu Server 24.04 (다른 배포판과 버전은 설치 첫 단계에서 멈춥니다)
- x86_64, RAM 4GB 이상, 여유 디스크 5GB 이상
- 사용자가 접속할 호스트 이름과 그 이름이 가리키는 서버 주소
- 80, 443 포트

PostgreSQL, nginx, 파이썬 런타임, systemd 서비스, 자체 서명 TLS 인증서는 설치 명령이 모두 만듭니다. 미리 깔아 둘 것은
없습니다.

## 설치

Release 페이지에서 `install.sh` 를 받아 실행합니다. 스크립트는 같은 Release 의 제품 묶음과 `SHA256SUMS` 를 받아 체크섬이
맞을 때만 풀고, 나머지 단계를 차례로 진행합니다. 실행하기 전에 스크립트를 열어 읽어 볼 수 있고, 스크립트의 체크섬도
Release 페이지의 `SHA256SUMS` 에 있습니다.

```bash
curl -fsSLO https://github.com/hshwang1994/clovirassist/releases/download/v<버전>/install.sh
sudo bash install.sh install --dns-name <호스트 이름> --bind-ip <서버 주소>
```

설치가 끝나면 콘솔에 첫 관리자 설정 코드가 한 번 나옵니다. 브라우저에서 `https://<호스트 이름>/setup/first-admin` 을 열고
그 코드와 함께 관리자 이메일, 이름, 비밀번호를 넣으면 시스템 관리자 계정이 만들어집니다. 코드는 설치 로그에 남지 않습니다.
코드를 잃어버렸으면 서버에서 `sudo clovirassist first-admin-code` 로 새로 만듭니다.

개발자는 저장소를 받아 같은 스크립트를 실행해도 됩니다.

```bash
sudo git clone --branch v<버전> https://github.com/hshwang1994/clovirassist.git /opt/clovirassist
sudo /opt/clovirassist/deploy/install.sh install --dns-name <호스트 이름> --bind-ip <서버 주소>
```

인터넷에 닿지 않는 서버는 오프라인 번들로 설치합니다. 절차는 [설치 상세 문서](docs/platform/INSTALLATION.md)에 있습니다.

## 설치 뒤 설정

필수 설정은 설치가 끝냅니다. 관리자로 로그인하면 **설정 > 초기 설정** 화면이 남은 항목을 보여 줍니다.

| 항목 | 구분 | 설정하는 곳 |
|---|---|---|
| 관리자 계정 | 필수 | 첫 관리자 화면(`/setup/first-admin`)에서 만듭니다 |
| 조직과 부서 | 필수 | 사용자와 권한 > 조직 관리 |
| TLS 인증서 | 필수 | 설치가 자체 서명 인증서를 만들어 둡니다. 설정 > 설정의 OS와 서비스 동작 탭에서 신뢰된 인증서로 바꾸기를 권합니다 |
| 메일(SMTP) | 선택 | 설정 > 설정에서 메일 서버와 비밀번호를 넣고, 운영 > 메일 발송에서 연결을 확인합니다 |
| AI | 선택 | 설정 > 설정의 AI 탭. Anthropic 은 API 키로, OpenAI 는 API 키나 ChatGPT 계정으로 연결합니다 |

메일과 AI 를 쓰지 않는 설치도 정상 설치입니다. 초기 설정 화면에서 "사용하지 않음"으로 표시하면 남은 항목으로 세지 않습니다.
API 키나 비밀번호 같은 비밀 값은 설치 명령에 넣지 않고, 설치 뒤 웹 화면에서 넣습니다.

문서 검색에 쓰는 임베딩 모델은 기본으로 설치하지 않습니다. 설치할 때 `--with-ai --download-model` 을 주면 제품이 고정한
체크섬과 맞는 모델 파일을 받아 함께 설치합니다.

## 운영 명령

설치가 `/usr/local/bin/clovirassist` 명령을 만듭니다.

```bash
sudo clovirassist version                      # 설치된 버전과 서비스 상태
sudo clovirassist verify                       # 설치가 실제로 동작하는지 확인
sudo clovirassist upgrade --release v<다음 버전> # 스냅샷을 뜬 뒤 새 Release 로 올립니다
sudo clovirassist rollback                     # 가장 최근 스냅샷으로 되돌립니다
sudo clovirassist uninstall                    # 서비스를 지웁니다. 데이터는 남깁니다
sudo clovirassist user list                    # 사용자 관리 도구
```

git 으로 설치한 서버는 `sudo clovirassist upgrade --ref v<다음 버전>` 으로 올립니다. 명령 전체는 `sudo clovirassist --help`
와 [설치 상세 문서](docs/platform/INSTALLATION.md)에 있습니다.
