import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BaseProvider, DarkTheme, LightTheme } from "baseui";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { Client as Styletron } from "styletron-engine-monolithic";
import { Provider as StyletronProvider } from "styletron-react";
import { ApiError } from "@/lib/client";
import { App } from "./App";

const engine = new Styletron();

// A signed-out answer anywhere (an expired session) sends the app back to sign in.
const client: QueryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (e) => {
      if (e instanceof ApiError && e.status === 401) void client.invalidateQueries({ queryKey: ["session"] });
    },
  }),
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 1, staleTime: 5_000 } },
});

function useDark(): boolean {
  const query = "(prefers-color-scheme: dark)";
  const [dark, setDark] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setDark(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return dark;
}

function Root() {
  const theme = useDark() ? DarkTheme : LightTheme;
  useEffect(() => {
    document.body.style.background = theme.colors.backgroundPrimary;
    document.body.style.color = theme.colors.contentPrimary;
    document.body.style.fontFamily = String(theme.typography.ParagraphMedium.fontFamily);
    document.body.style.margin = "0";
    document.documentElement.style.colorScheme = theme === DarkTheme ? "dark" : "light";
  }, [theme]);
  return (
    <StyletronProvider value={engine}>
      <BaseProvider theme={theme} zIndex={10}>
        <QueryClientProvider client={client}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </BaseProvider>
    </StyletronProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
