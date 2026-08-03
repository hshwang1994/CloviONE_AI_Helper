# ClovirAssist assets

로그인 화면의 클로비는 아래 고정 자산만 사용합니다.

- `login/clovi-canonical-hero.png`: 승인된 원본 로그인 Hero 장면
- `login/clovi-canonical-eye-base.png`: 원본에서 눈 픽셀만 제거한 베이스
- `login/clovi-canonical-eyes-layer.png`: 원본 눈 픽셀 레이어
- `login/clovi-canonical-avatar.png`: 같은 원본에서 잘라낸 작은 프로필 이미지
- `login/mascot-lock.json`: 해시, 크기, 가시 영역과 허용 동작 기준

마우스 이동 시 원본 눈 픽셀만 움직입니다. 로그인 성공 시에도 마스코트 이미지를 교체하지 않으며, 같은 장면 위에 눈 강조와 성공 배지만 표시합니다.

`mascot/frames/`, `mascot/layers/`, 개별 포즈 PNG는 제공된 참고 자산을 보존하기 위해 포함되어 있습니다. 로그인 런타임에서는 사용하지 않습니다. 상세 매핑은 `usage-map.json`을 확인합니다.
