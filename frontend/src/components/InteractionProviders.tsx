import type { ReactNode } from "react";
import { ConfirmProvider } from "material-ui-confirm";
import { SnackbarProvider } from "notistack";

export default function InteractionProviders({ children }: { children: ReactNode }) {
  return (
    <SnackbarProvider maxSnack={4} autoHideDuration={3000} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
      <ConfirmProvider defaultOptions={{ confirmationText: "确认", cancellationText: "取消", dialogProps: { maxWidth: "xs", fullWidth: true } }}>
        {children}
      </ConfirmProvider>
    </SnackbarProvider>
  );
}
