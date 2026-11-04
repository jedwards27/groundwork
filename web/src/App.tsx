import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ToasterContainer } from "baseui/toast";
import { useEffect, useRef, useState } from "react";
import { Route, Routes } from "react-router";
import { Header } from "@/components/Header";
import { Home } from "@/components/Home";
import { NewProject } from "@/components/NewProject";
import { Project } from "@/components/Project";
import { TutorialProvider } from "@/components/Tutorial";
import { Empty, Page, Rich } from "@/components/ui";
import { app } from "@/copy/app";
import { Navigate, useSearchParams } from "react-router";
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
        <Banner kind={BANNER.negative} title={app.shell.unreachableTitle}>
          <Rich text={app.shell.unreachableBody} />
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
        <Banner kind={BANNER.info} title={s.local ? app.shell.openFromClaudeTitle : app.shell.notSignedInTitle}>
          {signInError || app.shell.notSignedInBody}
        </Banner>
      </Page>
    );
  return (
    <TutorialProvider session={s}>
      <Header session={s} />
      <Routes>
        <Route path="/" element={<Home session={s} />} />
        <Route path="/projects/new" element={<NewProject session={s} />} />
        <Route path="/projects/:key/:tab?" element={<Project session={s} />} />
        <Route path="/verify" element={<VerifyRedirect />} />
        <Route
          path="*"
          element={
            <Page>
              <Empty>{app.shell.notFound}</Empty>
            </Page>
          }
        />
      </Routes>
      <ToasterContainer autoHideDuration={6000} placement="bottomRight" />
    </TutorialProvider>
  );
}

// Old links to the Verify page land on the project's Settings, under Receipts.
function VerifyRedirect() {
  const [params] = useSearchParams();
  const project = params.get("project");
  const record = params.get("record");
  return <Navigate replace to={project ? `/projects/${project}/settings${record ? `?record=${record}` : ""}` : "/"} />;
}
