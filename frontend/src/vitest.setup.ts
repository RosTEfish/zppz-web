import "@testing-library/jest-dom/vitest";

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
