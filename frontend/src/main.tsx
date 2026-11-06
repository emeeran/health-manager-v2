import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { SWRConfig } from "swr";
import { ErrorBanner } from "./components/ErrorBanner";
import { apiRequest, ApiError, isServerError } from "./lib/api-client";
import { pushApiError } from "./lib/api-errors";
import { router } from "./router";
import "./globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SWRConfig
      value={{
        fetcher: (key) => apiRequest(String(key)),
        shouldRetryOnError: false,
        onError: (error: unknown) => {
          // Only surface 5xx / network failures globally for now; auth and
          // validation errors are handled locally by the pages that cause them.
          if (isServerError(error)) {
            pushApiError(
              error instanceof ApiError && error.status === 0
                ? "Network error — could not reach the server."
                : "Server error — please try again later.",
            );
          } else {
            console.error(error);
          }
        },
      }}
    >
      <RouterProvider router={router} />
    </SWRConfig>
    <ErrorBanner />
  </StrictMode>,
);
