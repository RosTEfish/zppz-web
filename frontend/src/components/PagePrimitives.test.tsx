import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SWRConfig } from "swr";
import { useApiResource } from "./PagePrimitives";

describe("useApiResource", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("deduplicates matching keys and ignores stale key results", async () => {
    const requests: Array<{ version: number; resolve: (value: string) => void }> = [];

    function Probe({ version }: { version: number }) {
      const resource = useApiResource(["probe", version], () => new Promise<string>((resolve) => {
        requests.push({ version, resolve });
      }));
      return <div>{resource.loading ? "loading" : resource.data}</div>;
    }

    const view = render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 10_000 }}>
        <Probe version={1} />
        <Probe version={1} />
      </SWRConfig>,
    );
    await waitFor(() => expect(requests).toHaveLength(1));

    view.rerender(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 10_000 }}>
        <Probe version={2} />
        <Probe version={2} />
      </SWRConfig>,
    );
    await waitFor(() => expect(requests).toHaveLength(2));

    await act(async () => requests[1].resolve("new result"));
    expect(screen.getAllByText("new result")).toHaveLength(2);

    await act(async () => requests[0].resolve("stale result"));
    expect(screen.queryByText("stale result")).not.toBeInTheDocument();
  });

  it("does not refetch when the window is focused", async () => {
    let calls = 0;

    function Probe() {
      const resource = useApiResource("focus-probe", async () => {
        calls += 1;
        return "ready";
      });
      return <div>{resource.data ?? "loading"}</div>;
    }

    render(
      <SWRConfig value={{ provider: () => new Map() }}>
        <Probe />
      </SWRConfig>,
    );
    await screen.findByText("ready");
    expect(calls).toBe(1);

    await act(async () => {
      window.dispatchEvent(new Event("focus"));
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await new Promise((resolve) => window.setTimeout(resolve, 40));
    expect(calls).toBe(1);
  });
});
