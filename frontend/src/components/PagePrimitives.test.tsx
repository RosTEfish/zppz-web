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
});
