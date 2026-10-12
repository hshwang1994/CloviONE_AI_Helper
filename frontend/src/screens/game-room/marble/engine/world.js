/* 구슬 레이스의 물리 세계 — planck(Box2D 의 JS 이식, MIT) 위에 원본(lazygyu/roulette 의 physics-box2d.ts · marble.ts)의 규칙을 옮겼다.
 *
 * - 중력 (0, 10), 10ms 고정 스텝(속도 6 · 위치 2 반복), 구슬은 반지름 0.25 의 동적 원 · 밀도 1 + rand(seed).
 * - 판의 엔티티: 고정 상자 · 원 · 꺾은선(양면 Edge), 회전하는 kinematic 상자(각속도). 반발 · 밀도는 자료 그대로.
 * - 멈춘 구슬(5초 동안 거의 안 움직임)은 seed 난수의 충격으로 흔든다 — 원본의 STUCK_DELAY.
 * - 결승선(goalY) 을 지난 구슬은 50 스텝 뒤에 세계에서 뺀다(원본은 벽시계 500ms — 결정성을 위해 스텝으로 센다).
 * - 회전 장애물의 각은 2π 로 접는다 — 각이 끝없이 커지면 sin · cos 의 인수 축소 범위를 넘어 결정성 보장을 잃는다.
 *
 * 🔴 이 모듈은 `determinism.js` 가 먼저 평가된 뒤에 planck 를 들여와야 한다(`race.js` 의 import 순서). */

import "./determinism.js";
import * as planck from "planck";
import { spawnPosition } from "./layout.js";

export const STEP_SECONDS = 0.01;
export const MARBLE_RADIUS = 0.25;
const VELOCITY_ITERATIONS = 6;
const POSITION_ITERATIONS = 2;
const STUCK_STEPS = 500; // 5초
const STUCK_THRESHOLD_SQ = 0.00001;
const REMOVE_AFTER_STEPS = 50;
const TWO_PI = 6.283185307179586;
const ANGLE_WRAP = TWO_PI * 64;

const { World, Vec2, Box, Circle, Edge } = planck;

function makeEntityBody(world, entity) {
  const body = world.createBody({
    type: entity.type === "kinematic" ? "kinematic" : "static",
    position: new Vec2(entity.position.x, entity.position.y),
    angle: 0,
  });
  const props = entity.props || {};
  const fixtureDef = { density: props.density ?? 1, restitution: props.restitution ?? 0 };
  const shape = entity.shape;
  if (shape.type === "box") {
    body.createFixture(new Box(shape.width, shape.height, new Vec2(0, 0), shape.rotation || 0), fixtureDef);
  } else if (shape.type === "circle") {
    body.createFixture(new Circle(shape.radius), fixtureDef);
  } else if (shape.type === "polyline") {
    const pts = shape.points;
    for (let i = 0; i < pts.length - 1; i += 1) {
      body.createFixture(new Edge(new Vec2(pts[i][0], pts[i][1]), new Vec2(pts[i + 1][0], pts[i + 1][1])), { density: 1 });
    }
  }
  if (entity.type === "kinematic" && props.angularVelocity) body.setAngularVelocity(props.angularVelocity);
  return body;
}

/* 출발 자리는 `layout.js` 에 있다 — 그리기(대기 중 미리 보기)도 같은 격자를 쓰고, 그쪽은 planck 를 받지 않는다. */
export { spawnPosition } from "./layout.js";

export function createWorld(stage, marbles, rng) {
  const world = new World({ gravity: new Vec2(0, 10) });
  const entities = (stage.entities || []).map((entity, index) => ({ index, entity, body: makeEntityBody(world, entity) }));
  const kinematic = entities.filter((e) => e.entity.type === "kinematic");
  const bodies = marbles.map((m) => {
    const body = world.createBody({ type: "dynamic", position: new Vec2(m.x, m.y), bullet: false });
    body.createFixture(new Circle(MARBLE_RADIUS), { density: 1 + rng.next(), friction: 0.2, restitution: 0 });
    return { key: m.key, order: m.order, body, lastX: m.x, lastY: m.y, stuck: 0, finished: false, finishStep: -1, removeAt: -1, finishX: 0, finishY: 0 };
  });
  let step = 0;
  const api = {
    get step() { return step; },
    marbles: bodies,
    entities,
    /* 한 스텝. 결승선을 넘은 구슬의 열쇠를 돌려준다(순서대로). */
    advance(goalY) {
      step += 1;
      world.step(STEP_SECONDS, VELOCITY_ITERATIONS, POSITION_ITERATIONS);
      const crossed = [];
      for (const m of bodies) {
        if (!m.body) continue; // 이미 세계에서 뺀 구슬
        if (m.removeAt >= 0) {
          if (step >= m.removeAt) {
            world.destroyBody(m.body);
            m.removeAt = -1;
            m.body = null;
          }
          continue;
        }
        const p = m.body.getPosition();
        if (!m.finished) {
          const dx = p.x - m.lastX;
          const dy = p.y - m.lastY;
          if (dx * dx + dy * dy < STUCK_THRESHOLD_SQ) {
            m.stuck += 10;
            if (m.stuck > STUCK_STEPS * 10) {
              m.body.applyLinearImpulse(new Vec2(rng.next() * 10 - 5, rng.next() * 10 - 5), m.body.getWorldCenter(), true);
              m.stuck = 0;
            }
          } else {
            m.stuck = 0;
          }
          m.lastX = p.x;
          m.lastY = p.y;
          if (p.y > goalY) {
            m.finished = true;
            m.finishStep = step;
            m.finishX = p.x; // 그리기용 — 결승선을 넘은 자리. 세계에서 뺀 뒤에도 마지막 장면에 이 자리로 남는다.
            m.finishY = p.y;
            m.removeAt = step + REMOVE_AFTER_STEPS;
            crossed.push(m.key);
          }
        }
      }
      for (const k of kinematic) {
        const a = k.body.getAngle();
        if (a > ANGLE_WRAP || a < -ANGLE_WRAP) k.body.setAngle(a % TWO_PI);
      }
      return crossed;
    },
    positions() {
      return bodies.map((m) => {
        if (!m.body) return { key: m.key, x: m.finishX, y: m.finishY, angle: 0, gone: true, finished: m.finished };
        const p = m.body.getPosition();
        return { key: m.key, x: p.x, y: p.y, angle: m.body.getAngle(), gone: false, finished: m.finished };
      });
    },
    entityAngles() {
      return entities.map((e) => e.body.getAngle());
    },
  };
  return api;
}
