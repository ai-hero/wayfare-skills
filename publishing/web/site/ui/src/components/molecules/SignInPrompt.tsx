// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { useEffect, useState } from "react";
import { useRouter } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { NoticeAlert } from "@/components/molecules/NoticeAlert";
import { useAuth } from "@/hooks/useAuth";

/**
 * For a page the server rendered locked. A session that arrived after the page
 * loaded gets one refetch, and the server decides again; if the client still
 * believes it is signed in once that settles, the server did not honour the
 * session, and asking the reader to sign in again would loop. True then.
 */
export function useUnconfirmedSession(page: string): boolean {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [rechecked, setRechecked] = useState(false);
  useEffect(() => {
    if (!isAuthenticated) return;
    void router.invalidate().then(() => setRechecked(true));
  }, [isAuthenticated, router]);
  const unconfirmed = isAuthenticated && rechecked;
  useEffect(() => {
    if (unconfirmed) console.warn(`book: ${page} stayed locked for a signed-in reader`);
  }, [unconfirmed, page]);
  return unconfirmed;
}

export function SignInPrompt({ onSignIn, unconfirmed = false }: { onSignIn: () => void; unconfirmed?: boolean }) {
  if (unconfirmed) {
    return (
      <NoticeAlert
        tone="refusal"
        eyebrow="Continue reading"
        badge="Session"
        title="We could not confirm your sign-in."
        actions={
          <Button size="sm" onClick={() => window.location.reload()}>
            Reload the page
          </Button>
        }
      >
        <p>Reload the page. If this chapter stays locked, sign out and sign in again.</p>
      </NoticeAlert>
    );
  }
  return (
    <NoticeAlert
      tone="refusal"
      eyebrow="Continue reading"
      badge="Sign in"
      title="Sign in to continue reading."
      actions={
        <Button size="sm" onClick={onSignIn}>
          Sign in to read more
        </Button>
      }
    >
      <p>The full article is available to signed-in readers.</p>
      <p>
        Sign in with your email to read the rest &mdash; free access, no
        credit card required.
      </p>
    </NoticeAlert>
  );
}
