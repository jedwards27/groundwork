// A visitor's own Anthropic API key, for this browser tab only. It lives in this module's memory:
// never in localStorage, sessionStorage, a cookie or the URL, so reloading or closing the tab forgets
// it. It goes to the server with each Play, which uses it for that run and never stores it.
import { useSyncExternalStore } from "react";

let key: string | null = null;
const listeners = new Set<() => void>();

export function setKey(next: string | null): void {
  key = next && next.trim() ? next.trim() : null;
  listeners.forEach((l) => l());
}

export function getKey(): string | null {
  return key;
}

export function useKey(): string | null {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => key,
  );
}
