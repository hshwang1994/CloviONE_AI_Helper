import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/* 프런트(React) 유닛 테스트 러너. jsdom 환경 + globals(describe/it/expect 전역),
 * setupFiles로 @testing-library/jest-dom 매처를 로드한다. JSX 변환은 이미 쓰고 있는
 * @vitejs/plugin-react로 처리한다(vite.config.js와 동일). CSS는 파싱하지 않아 테스트를 가볍게 유지한다. */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.js"],
    include: ["src/**/*.test.{js,jsx}"],
    css: false,
  },
});
