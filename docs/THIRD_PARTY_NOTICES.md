# 제3자 고지 — 제품에 들어간 바깥 코드의 출처

프런트 번들의 라이브러리(React, MUI 등)는 각 패키지의 `LICENSE` 가 `node_modules` 에 있고 여기 다시 적지 않는다. 이 문서는
**코드나 자료를 옮겨 왔거나, 고지 유지를 조건으로 하는 것**만 적는다.

## 구슬 레이스 — Marble Roulette (lazygyu), MIT

구슬 레이스(`frontend/src/screens/game-room/marble/`)는 https://github.com/lazygyu/roulette 의 물리 규칙, 경주 판 자료, 순위 계산을
바탕으로 했다. 기준 커밋과 라이선스 전문, 상표 고지("Marble Roulette"™ · "마블 룰렛"™ 은 lazygyu 의 상표)는
`frontend/src/screens/game-room/marble/ATTRIBUTION.md` 에 있다. 제품 안 이름은 「구슬 레이스」만 쓴다.

## planck 1.5.0 — Box2D 의 JavaScript 이식, MIT

구슬 레이스의 물리 엔진이다(`frontend/package.json` 의 `planck`). 아래는 설치된 `node_modules/planck/LICENSE.txt` 원문이다.

```
The MIT License
Copyright (c) Erin Catto, Ali Shakiba

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

## fdlibm — 결정적 수학 (`marble/engine/determinism.js`)

sin · cos · atan · atan2 는 Sun Microsystems 의 fdlibm(freely distributable libm) 알고리즘을 JavaScript 로 옮긴 것이다. 원 고지:

```
Copyright (C) 1993 by Sun Microsystems, Inc. All rights reserved.

Developed at SunSoft, a Sun Microsystems, Inc. business.
Permission to use, copy, modify, and distribute this
software is freely granted, provided that this notice
is preserved.
```
