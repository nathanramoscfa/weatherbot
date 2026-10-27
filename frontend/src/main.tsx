// frontend/src/main.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { initCspNonce, readCspNonce } from "./app/nonce.ts";
import { createAppBrowserRouter } from "./app/routes.tsx";
import "./index.css";

const initialNonce =
  typeof document !== "undefined"
    ? document.querySelector<HTMLMetaElement>('meta[property="csp-nonce"]')
        ?.nonce || readCspNonce(document)
    : undefined;
globalThis.__webpack_nonce__ = initialNonce;

export const cspNonce: string | undefined = initialNonce;
export { initCspNonce, readCspNonce };

export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: Infinity,
        refetchInterval: false,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        retry: 1,
      },
    },
  });
}

const rootElement =
  typeof document !== "undefined" ? document.getElementById("root") : null;

if (rootElement) {
  const queryClient = createAppQueryClient();
  const router = createAppBrowserRouter();
  createRoot(rootElement).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
}
