import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ToasterContainer } from "baseui/toast";
import { useEffect, useRef, useState } from "react";
import { Route, Routes } from "react-router";
import { Header } from "@/components/Header";
import { Home } from "@/components/Home";
import { Project } from "@/components/Project";
import { Empty, Page } from "@/components/ui";
import { VerifyRecord } from "@/components/VerifyRecord";
import { get, send } from "@/lib/client";
import type { Session } from "@/lib/types";
import { Banner, KIND as BANNER } from "baseui/banner";
import { Skeleton } from "baseui/skeleton";

export function App() {
  const qc = useQueryClient();
  const session = useQuery({ queryKey: ["session"], queryFn: () => get<Session>("session") });
  const [signInError, setSignInError] = useState("");
  const signingIn = useRef(false);

  // The demo has one person, so there is nothing to choose: a visitor is signed in as them.
  useEffect(() => {
    const s = session.data;
    if (!s || s.signed_in || !s.health.demo_login || signingIn.current) return;
    signingIn.current = true;
    send("POST", "session")
      .then(() => qc.invalidateQueries())
      .catch((e: Error) => setSignInError(e.message))
      .finally(() => {
        signingIn.current = false;
      });
  }, [session.data, qc]);

  if (session.isError)
    return (
      <Page>
        <Banner kind={BANNER.negative} title="Groundwork isn't reachable">
          Start it with <code>make api</code> (or open it from Claude), then reload.
        </Banner>
      </Page>
    );
  const s = session.data;
  if (!s || (!s.signed_in && s.health.demo_login && !signInError))
    return (
      <Page>
        <Skeleton rows={4} height="200px" width="100%" animation />
      </Page>
    );
  if (!s.signed_in)
    return (
      <Page>
        <Banner kind={BANNER.info} title={s.local ? "Open Groundwork from Claude" : "Not signed in"}>
          {signInError ||
            "Ask Claude for your Groundwork link (the pending tool gives it). The link opens this app signed in as you, on this computer only."}
        </Banner>
      </Page>
    );
  return (
    <>
      <Header session={s} />
      <Routes>
        <Route path="/" element={<Home session={s} />} />
        <Route path="/projects/:key/:tab?" element={<Project session={s} />} />
        <Route path="/verify" element={<VerifyRecord />} />
        <Route
          path="*"
          element={
            <Page>
              <Empty>Nothing here.</Empty>
            </Page>
          }
        />
      </Routes>
      <ToasterContainer autoHideDuration={6000} placement="bottomRight" />
    </>
  );
}
