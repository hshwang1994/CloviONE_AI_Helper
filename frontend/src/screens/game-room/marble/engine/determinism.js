/* 결정적 수학 — 브라우저 · OS 가 달라도 같은 값을 내는 sin · cos · atan2 · hypot (D-564).
 *
 * IEEE-754 의 덧셈 · 곱셈 · 나눗셈 · 제곱근은 어디서나 같은 값으로 반올림되지만, `Math.sin` 같은 초월 함수는 엔진마다 구현이
 * 달라 마지막 자리가 다를 수 있다. 물리 엔진(planck)은 회전 변환에 sin · cos · atan2 를 쓰고, 10ms 스텝 수천 번이 그 차이를
 * 키워 Chromium 과 Firefox 의 경주가 갈라질 수 있다. 그래서 워커 전역의 그 셋을 fdlibm(Sun 의 공개 구현, 모든 엔진의 기준)
 * 을 그대로 옮긴 순수 JS 로 바꾼다 — 사칙연산과 제곱근만 쓰므로 어디서나 같은 비트를 낸다.
 *
 * 🔴 planck 는 모듈을 읽는 순간 `Math.sin` 을 변수에 담아 둔다. 그래서 이 모듈이 **planck 보다 먼저** 평가돼야 한다
 * (`worker.js` · `race.js` 의 import 순서가 그 약속이다). 주 스레드의 Math 는 건드리지 않는다 — 워커와 시험 프로세스 안에서만.
 *
 * 범위: |x| < 2^20 · π/2 (약 1.6e6 rad) 까지 fdlibm 의 중간 경로(Cody-Waite 세 조각 축소)를 그대로 쓴다. 그보다 큰 각은 경주에
 * 나오지 않는다(회전 장애물의 각은 `world.js` 가 2π 로 접는다). 혹시 넘으면 원래 Math 로 물러나되 그 사실을 센다(`stats`). */

const f64 = new Float64Array(1);
const u32 = new Uint32Array(f64.buffer);
const LITTLE = new Uint8Array(new Uint16Array([1]).buffer)[0] === 1;
const HI = LITTLE ? 1 : 0;
const LO = LITTLE ? 0 : 1;

function highWord(x) {
  f64[0] = x;
  return u32[HI] | 0;
}

function lowWord(x) {
  f64[0] = x;
  return u32[LO] >>> 0;
}

const nativeSin = Math.sin;
const nativeCos = Math.cos;
const nativeAtan2 = Math.atan2;

export const stats = { fallbacks: 0 };

/* ── k_sin · k_cos (fdlibm / FreeBSD msun) ─────────────────────────────────── */

const S1 = -1.66666666666666324348e-01;
const S2 = 8.33333333332248946124e-03;
const S3 = -1.98412698298579493134e-04;
const S4 = 2.75573137070700676789e-06;
const S5 = -2.50507602534068634195e-08;
const S6 = 1.58969099521155010221e-10;

function kernelSin(x, y, iy) {
  const z = x * x;
  const w = z * z;
  const r = S2 + z * (S3 + z * S4) + z * w * (S5 + z * S6);
  const v = z * x;
  if (iy === 0) return x + v * (S1 + z * r);
  return x - ((z * (0.5 * y - v * r) - y) - v * S1);
}

const C1 = 4.16666666666666019037e-02;
const C2 = -1.38888888888741095749e-03;
const C3 = 2.48015872894767294178e-05;
const C4 = -2.75573143513906633035e-07;
const C5 = 2.08757232129817482790e-09;
const C6 = -1.13596475577881948265e-11;

function kernelCos(x, y) {
  const z = x * x;
  const w = z * z;
  const r = z * (C1 + z * (C2 + z * C3)) + w * w * (C4 + z * (C5 + z * C6));
  const hz = 0.5 * z;
  const w1 = 1 - hz;
  return w1 + (((1 - w1) - hz) + (z * r - x * y));
}

/* ── 인수 축소 (e_rem_pio2 의 중간 경로) ───────────────────────────────────── */

const invpio2 = 6.36619772367581382433e-01;
const pio2_1 = 1.57079632673412561417e+00;
const pio2_1t = 6.07710050650619224932e-11;
const pio2_2 = 6.07710050630396597660e-11;
const pio2_2t = 2.02226624879595063154e-21;
const pio2_3 = 2.02226624871116645580e-21;
const pio2_3t = 8.47842766036889956997e-32;
const TWO_1_8P52 = 6755399441055744; // 0x1.8p52 — 가장 가까운 정수로 반올림하는 더하기 요령

const Y = [0, 0];
/* 축소 범위 밖 - 사분면 n 은 음수일 수 있으므로(음수 x) 물러남 표지는 따로 둔다. */
const OUT_OF_RANGE = 0x7fffffff;

/* y[0] · y[1] 에 축소된 값을 쓰고 사분면 n 을 돌려준다(음수 x 면 음수). |x| < 2^20·π/2 에서 fdlibm 과 비트까지 같다. 그 밖은 OUT_OF_RANGE. */
function remPio2(x, ix) {
  if (ix <= 0x3fe921fb) {
    Y[0] = x;
    Y[1] = 0;
    return 0;
  }
  if (ix >= 0x413921fb) return OUT_OF_RANGE;
  const fn = (x * invpio2 + TWO_1_8P52) - TWO_1_8P52;
  const n = fn | 0;
  let r = x - fn * pio2_1;
  let w = fn * pio2_1t;
  const j = ix >> 20;
  let y0 = r - w;
  let high = highWord(y0);
  let i = j - ((high >> 20) & 0x7ff);
  if (i > 16) {
    let t = r;
    w = fn * pio2_2;
    r = t - w;
    w = fn * pio2_2t - ((t - r) - w);
    y0 = r - w;
    high = highWord(y0);
    i = j - ((high >> 20) & 0x7ff);
    if (i > 49) {
      t = r;
      w = fn * pio2_3;
      r = t - w;
      w = fn * pio2_3t - ((t - r) - w);
      y0 = r - w;
    }
  }
  Y[0] = y0;
  Y[1] = (r - y0) - w;
  return n;
}

export function sin(x) {
  const hx = highWord(x);
  const ix = hx & 0x7fffffff;
  if (ix <= 0x3fe921fb) {
    if (ix < 0x3e500000) return x; // |x| < 2^-26 — x 그대로
    return kernelSin(x, 0, 0);
  }
  if (ix >= 0x7ff00000) return x - x; // NaN · Inf
  const n = remPio2(x, ix);
  if (n === OUT_OF_RANGE) {
    stats.fallbacks += 1;
    return nativeSin(x);
  }
  switch (n & 3) {
    case 0: return kernelSin(Y[0], Y[1], 1);
    case 1: return kernelCos(Y[0], Y[1]);
    case 2: return -kernelSin(Y[0], Y[1], 1);
    default: return -kernelCos(Y[0], Y[1]);
  }
}

export function cos(x) {
  const hx = highWord(x);
  const ix = hx & 0x7fffffff;
  if (ix <= 0x3fe921fb) {
    if (ix < 0x3e46a09e) return 1; // |x| < 2^-27 · √2
    return kernelCos(x, 0);
  }
  if (ix >= 0x7ff00000) return x - x;
  const n = remPio2(x, ix);
  if (n === OUT_OF_RANGE) {
    stats.fallbacks += 1;
    return nativeCos(x);
  }
  switch (n & 3) {
    case 0: return kernelCos(Y[0], Y[1]);
    case 1: return -kernelSin(Y[0], Y[1], 1);
    case 2: return -kernelCos(Y[0], Y[1]);
    default: return kernelSin(Y[0], Y[1], 1);
  }
}

/* ── atan · atan2 (s_atan.c · e_atan2.c) ───────────────────────────────────── */

const atanhi = [4.63647609000806093515e-01, 7.85398163397448278999e-01, 9.82793723247329054082e-01, 1.57079632679489655800e+00];
const atanlo = [2.26987774529616870924e-17, 3.06161699786838301793e-17, 1.39033110312309984516e-17, 6.12323399573676603587e-17];
const aT = [
  3.33333333333329318027e-01, -1.99999999998764832476e-01, 1.42857142725034663711e-01, -1.11111104054623557880e-01,
  9.09088713343650656196e-02, -7.69187620504482999495e-02, 6.66107313738753120669e-02, -5.83357013379057348645e-02,
  4.97687799461593236017e-02, -3.65315727442169155270e-02, 1.62858201153657823623e-02,
];

export function atan(x) {
  const hx = highWord(x);
  const ix = hx & 0x7fffffff;
  if (ix >= 0x44100000) {
    if (ix > 0x7ff00000 || (ix === 0x7ff00000 && lowWord(x) !== 0)) return x + x; // NaN
    return hx > 0 ? atanhi[3] + atanlo[3] : -atanhi[3] - atanlo[3];
  }
  let id;
  let v = x;
  if (ix < 0x3fdc0000) {
    if (ix < 0x3e400000) return x; // |x| < 2^-27
    id = -1;
  } else {
    v = Math.abs(x);
    if (ix < 0x3ff30000) {
      if (ix < 0x3fe60000) {
        id = 0;
        v = (2 * v - 1) / (2 + v);
      } else {
        id = 1;
        v = (v - 1) / (v + 1);
      }
    } else if (ix < 0x40038000) {
      id = 2;
      v = (v - 1) / (v + 1);
    } else {
      id = 3;
      v = -1 / v;
    }
  }
  const z = v * v;
  const w = z * z;
  const s1 = z * (aT[0] + w * (aT[2] + w * (aT[4] + w * (aT[6] + w * (aT[8] + w * aT[10])))));
  const s2 = w * (aT[1] + w * (aT[3] + w * (aT[5] + w * (aT[7] + w * aT[9]))));
  if (id < 0) return v - v * (s1 + s2);
  const r = atanhi[id] - ((v * (s1 + s2) - atanlo[id]) - v);
  return hx < 0 ? -r : r;
}

const pi_o_4 = 7.8539816339744827900e-01;
const pi_o_2 = 1.5707963267948965580e+00;
const PI = 3.1415926535897931160e+00;
const pi_lo = 1.2246467991473531772e-16;

export function atan2(y, x) {
  const hx = highWord(x);
  const lx = lowWord(x);
  const ix = hx & 0x7fffffff;
  const hy = highWord(y);
  const ly = lowWord(y);
  const iy = hy & 0x7fffffff;
  if (((ix | ((lx | -lx) >>> 31)) > 0x7ff00000) || ((iy | ((ly | -ly) >>> 31)) > 0x7ff00000)) return x + y; // NaN
  if (((hx - 0x3ff00000) | lx) === 0) return atan(y); // x == 1
  const m = ((hy >> 31) & 1) | ((hx >> 30) & 2);
  if ((iy | ly) === 0) {
    switch (m) {
      case 0: case 1: return y;
      case 2: return PI;
      default: return -PI;
    }
  }
  if ((ix | lx) === 0) return hy < 0 ? -pi_o_2 : pi_o_2;
  if (ix === 0x7ff00000) {
    if (iy === 0x7ff00000) {
      switch (m) {
        case 0: return pi_o_4;
        case 1: return -pi_o_4;
        case 2: return 3 * pi_o_4;
        default: return -3 * pi_o_4;
      }
    }
    switch (m) {
      case 0: return 0;
      case 1: return -0;
      case 2: return PI;
      default: return -PI;
    }
  }
  if (iy === 0x7ff00000) return hy < 0 ? -pi_o_2 : pi_o_2;
  const k = (iy - ix) >> 20;
  let z;
  let mm = m;
  if (k > 60) {
    z = pi_o_2 + 0.5 * pi_lo;
    mm &= 1;
  } else if (hx < 0 && k < -60) {
    z = 0;
  } else {
    z = atan(Math.abs(y / x));
  }
  switch (mm) {
    case 0: return z;
    case 1: return -z;
    case 2: return PI - (z - pi_lo);
    default: return (z - pi_lo) - PI;
  }
}

/* `Math.hypot` 은 정확히 반올림되지 않아도 되는 함수라 엔진마다 다를 수 있다 - 제곱근은 어디서나 같다. 두 인자만 쓴다. */
export function hypot(a, b) {
  return Math.sqrt(a * a + b * b);
}

let installed = false;

/* 워커 · 시험 프로세스의 전역 Math 를 바꾼다. 한 번만. 주 스레드(화면)에서는 부르지 않는다. */
export function installDeterministicMath(target = globalThis.Math) {
  if (installed) return target;
  target.sin = sin;
  target.cos = cos;
  target.atan2 = atan2;
  target.hypot = hypot;
  installed = true;
  return target;
}

export function isInstalled() {
  return installed;
}

/* 자기 시험 — 알려진 값과 두 번 실행의 일치. 결과를 돌려주고 틀리면 그 항목을 적는다(워커가 시작할 때 한 번 돈다). */
export function selfTest() {
  const cases = [
    ["sin(1)", sin(1), 0.8414709848078965],
    ["cos(1)", cos(1), 0.5403023058681398],
    ["sin(π)", sin(3.141592653589793), 1.2246467991473532e-16],
    ["cos(π/3)", cos(1.0471975511965976), 0.5000000000000001],
    ["sin(100)", sin(100), -0.5063656411097588],
    ["cos(1e5)", cos(1e5), -0.9993608074382124],
    ["atan2(1,1)", atan2(1, 1), 0.7853981633974483],
    ["atan2(-1,-1)", atan2(-1, -1), -2.356194490192345],
    ["atan2(1,0)", atan2(1, 0), 1.5707963267948966],
    ["hypot(3,4)", hypot(3, 4), 5],
  ];
  const failures = cases.filter(([, got, want]) => !(Math.abs(got - want) <= 4e-16 * Math.max(1, Math.abs(want))));
  const again = cases.map(([name]) => name);
  return { ok: failures.length === 0, failures: failures.map(([name, got, want]) => ({ name, got, want })), checked: again.length };
}

/* 모듈을 읽는 것만으로 설치된다(import 순서가 planck 보다 앞이면 된다). 화면 코드는 이 모듈을 import 하지 않는다. */
installDeterministicMath();
