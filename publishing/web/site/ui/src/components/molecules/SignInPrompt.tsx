// Copyright (c) 2026 A.I. Hero, Inc.
// All Rights Reserved.

import { Button } from "@/components/ui/button";
import { NoticeAlert } from "@/components/molecules/NoticeAlert";

// The one "sign in to continue reading" prompt: AuthGate shows it in gated
// posts and the book shows it on locked chapters, so the two never drift.
export function SignInPrompt({ onSignIn }: { onSignIn: () => void }) {
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
