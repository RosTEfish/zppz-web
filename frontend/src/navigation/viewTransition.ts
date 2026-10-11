import { flushSync } from "react-dom";
import type { NavigateFunction, NavigateOptions, To } from "react-router-dom";

export type ViewTransitionKind = "to-app" | "to-auth" | "to-page";

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function pathFromTo(to: To): string {
  if (typeof to === "string") return to.split(/[?#]/)[0] || "/";
  return to.pathname ?? "/";
}

export function viewTransitionKind(to: To, fromPath = typeof window !== "undefined" ? window.location.pathname : ""): ViewTransitionKind {
  const toPath = pathFromTo(to);
  const toAuth = toPath === "/login";
  const fromAuth = fromPath === "/login";
  if (toAuth && !fromAuth) return "to-auth";
  if (!toAuth && fromAuth) return "to-app";
  return "to-page";
}

/** View Transitions between shells (auth ↔ app) and in-app pages. */
export function navigateWithViewTransition(navigate: NavigateFunction, to: To, options?: NavigateOptions) {
  const kind = viewTransitionKind(to);
  const toPath = pathFromTo(to);
  const samePath = typeof window !== "undefined" && toPath === window.location.pathname;

  const nextOptions: NavigateOptions = {
    ...options,
    state: {
      ...(options?.state && typeof options.state === "object" ? options.state as Record<string, unknown> : null),
      zppzVt: kind,
    },
  };

  const go = () => {
    flushSync(() => {
      navigate(to, nextOptions);
    });
  };

  // Query/hash-only changes, reduced motion, or missing API → plain navigate.
  if (
    samePath
    || typeof document === "undefined"
    || typeof document.startViewTransition !== "function"
    || prefersReducedMotion()
  ) {
    go();
    return;
  }

  const root = document.documentElement;
  root.dataset.vt = kind;

  try {
    const transition = document.startViewTransition(go);
    void transition.finished.finally(() => {
      if (root.dataset.vt === kind) delete root.dataset.vt;
    });
  } catch {
    delete root.dataset.vt;
    go();
  }
}
