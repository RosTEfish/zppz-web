import "@testing-library/jest-dom/vitest";

class NoopEventSource {
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  constructor(_url: string) {}
  addEventListener() {}
  removeEventListener() {}
  close() {}
  dispatchEvent() {
    return false;
  }
}

if (typeof globalThis.EventSource === "undefined") {
  Object.defineProperty(globalThis, "EventSource", {
    configurable: true,
    writable: true,
    value: NoopEventSource,
  });
}
import { afterAll, afterEach, beforeAll } from "vitest";
import { testServer } from "./testServer";

const nativeFetch = globalThis.fetch;

beforeAll(() => {
  testServer.listen({ onUnhandledRequest: "error" });
  const interceptedFetch = globalThis.fetch;
  globalThis.fetch = (input, init) => {
    const resolvedInput = typeof input === "string" || input instanceof URL
      ? new URL(String(input), window.location.origin).href
      : input;
    return interceptedFetch(resolvedInput, init?.signal ? { ...init, signal: undefined } : init);
  };
});
afterEach(() => testServer.resetHandlers());
afterAll(() => {
  testServer.close();
  globalThis.fetch = nativeFetch;
});

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
});

class TestResizeObserver implements ResizeObserver {
  observe(target: Element) {
    const rect = target.getBoundingClientRect();
    const width = rect.width || 1024;
    const height = rect.height || 768;
    this.callback([{ target, contentRect: { ...rect, width, height } } as ResizeObserverEntry], this);
  }

  unobserve() {}
  disconnect() {}

  constructor(private readonly callback: ResizeObserverCallback) {}
}

Object.defineProperty(globalThis, "ResizeObserver", {
  writable: true,
  value: TestResizeObserver,
});
