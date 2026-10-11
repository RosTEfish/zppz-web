import { forwardRef } from "react";
import { Link, useNavigate, type LinkProps } from "react-router-dom";
import { navigateWithViewTransition } from "./viewTransition";

/** React Router Link that runs the same View Transition as navigateWithViewTransition. */
export const ViewTransitionLink = forwardRef<HTMLAnchorElement, LinkProps>(function ViewTransitionLink(
  { to, onClick, replace, state, preventScrollReset, relative, ...rest },
  ref,
) {
  const navigate = useNavigate();
  return (
    <Link
      ref={ref}
      to={to}
      replace={replace}
      state={state}
      preventScrollReset={preventScrollReset}
      relative={relative}
      onClick={(event) => {
        onClick?.(event);
        if (event.defaultPrevented) return;
        if (event.button !== 0 || event.metaKey || event.altKey || event.ctrlKey || event.shiftKey) return;
        event.preventDefault();
        navigateWithViewTransition(navigate, to, { replace, state, preventScrollReset, relative });
      }}
      {...rest}
    />
  );
});
