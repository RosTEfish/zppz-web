import { flushSync } from "react-dom";
import type { NavigateFunction, NavigateOptions, To } from "react-router-dom";

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Soft crossfade between auth shell and app shell (View Transitions API + fallback). */
export function navigateWithViewTransition(navigate: NavigateFunction, to: To, options?: NavigateOptions) {
  const go = () => {
    flushSync(() => {
      navigate(to, options);
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

  document.startViewTransition(go);
}
