# 구슬 레이스 — 출처와 라이선스

구슬 레이스는 lazygyu 의 **Marble Roulette**(https://github.com/lazygyu/roulette)의 물리 규칙, 경주 판(「Wheel of fortune」) 자료,
순위 계산(진행도 지도)을 바탕으로 만들었습니다. 옮긴 기준 커밋은 `3f59495e89b17c80ec133346b75b11c64e3bbe02` 이고,
아래 라이선스 전문은 그 커밋의 `LICENSE` 파일을 변경 없이 옮긴 것입니다.

원본 README 의 상표 고지에 따라 **"Marble Roulette"™ 와 "마블 룰렛"™ 은 lazygyu 의 상표**입니다. 이 제품은 그 이름을 쓰지 않고
「구슬 레이스」라고 부르며, 두 이름은 이 출처 표기("based on Marble Roulette by lazygyu")에만 씁니다.

이 제품에서 바꾼 것: TypeScript + box2d-wasm 구현을 planck(Box2D 의 JS 이식)와 결정적 수학(fdlibm 이식) 위에 다시 썼고,
물리를 Web Worker 로 옮겼으며, 서버가 seed 를 주고 결과를 상호 대조로 확정하는 구조(D-564)를 더했습니다. 그리기(색 · 카메라 ·
라벨)는 제품 디자인 시스템으로 새로 그렸고 원본의 그림 · 소리 · 스킬(impact)은 쓰지 않았습니다.

planck 의 라이선스는 `docs/THIRD_PARTY_NOTICES.md` 에 있습니다.

---

```
MIT License

Copyright (c) 2022 LazyGyu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
