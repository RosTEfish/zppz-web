import { flushSync } from "react-dom";
import type { NavigateFunction, NavigateOptions, To } from "react-router-dom";

export type ViewTransitionKind = "to-app" | "to-auth";

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function viewTransitionKind(to: To): ViewTransitionKind {
  const path = typeof to === "string" ? to.split(/[?#]/)[0] : to.pathname ?? "";
  return path === "/login" ? "to-auth" : "to-app";
}

/** Soft directional crossfade between auth shell and app shell (View Transitions API + fallback). */
export function navigateWithViewTransition(navigate: NavigateFunction, to: To, options?: NavigateOptions) {
  const kind = viewTransitionKind(to);
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

  if (
    typeof document === "undefined"
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
