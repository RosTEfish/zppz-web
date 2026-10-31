import { act, render, screen } from "@testing-library/react";
import useSWR, { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DomainEventsProvider } from "./DomainEventsProvider";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  closed = false;
  onopen: ((ev: Event) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  private listeners = new Map<string, Set<EventListener>>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener) {
    const bucket = this.listeners.get(type) ?? new Set<EventListener>();
    bucket.add(listener);
    this.listeners.set(type, bucket);
  }

  removeEventListener(type: string, listener: EventListener) {
    this.listeners.get(type)?.delete(listener);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: unknown) {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }

  fail() {
    this.onerror?.(new Event("error"));
  }
}

describe("DomainEventsProvider", () => {
  const OriginalEventSource = globalThis.EventSource;

  afterEach(() => {
    MockEventSource.instances = [];
    globalThis.EventSource = OriginalEventSource;
    vi.useRealTimers();
  });

  it("revalidates the job list when a submission event arrives and reconnects after an error", async () => {
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
    let calls = 0;

    function Probe() {
      const { data } = useSWR(["submissions", "jobs"], async () => {
        calls += 1;
        return `loaded-${calls}`;
      }, { dedupingInterval: 0 });
      return <div>{data ?? "loading"}</div>;
    }

    render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        <DomainEventsProvider>
          <Probe />
        </DomainEventsProvider>
      </SWRConfig>,
    );

    expect(await screen.findByText("loaded-1")).toBeInTheDocument();
    expect(MockEventSource.instances[0]?.url).toBe("/api/v1/events");
    act(() => {
      MockEventSource.instances[0]?.emit("submission.job", {
        id: 4,
        topic: "submission.job",
        scope: "user",
        subject_user_id: 3,
        resources: ["submissions"],
        payload: { jobs: [{ id: "job-1", status: "completed", stage: "complete" }] },
      });
    });
    expect(await screen.findByText("loaded-2")).toBeInTheDocument();

    vi.useFakeTimers();
    act(() => {
      MockEventSource.instances[0]?.fail();
    });
    expect(MockEventSource.instances[0]?.closed).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1]?.url).toBe("/api/v1/events?after=4");
  });
});
