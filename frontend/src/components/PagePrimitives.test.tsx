import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useResource } from "./PagePrimitives";


describe("useResource", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("aborts superseded requests and ignores their late results", async () => {
    const requests: Array<{
      version: number;
      signal: AbortSignal;
      resolve: (value: string) => void;
    }> = [];

    function Probe({ version }: { version: number }) {
      const resource = useResource(
        (signal) => new Promise<string>((resolve) => {
          requests.push({ version, signal, resolve });
        }),
        [version],
      );
      return <div>{resource.loading ? "loading" : resource.data}</div>;
    }

    const view = render(<Probe version={1} />);
    await waitFor(() => expect(requests).toHaveLength(1));

    view.rerender(<Probe version={2} />);
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[0].signal.aborted).toBe(true);

    await act(async () => requests[1].resolve("new result"));
    expect(screen.getByText("new result")).toBeInTheDocument();

    await act(async () => requests[0].resolve("stale result"));
    expect(screen.getByText("new result")).toBeInTheDocument();
    expect(screen.queryByText("stale result")).not.toBeInTheDocument();

    view.unmount();
    expect(requests[1].signal.aborted).toBe(true);
  });
});
