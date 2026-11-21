// One session id per browser tab, shared by chat and voice so both see the same history.
// Exposed as a tiny external store so components read it with useSyncExternalStore.
const KEY = "support-session-id";
const ID_PATTERN = /^[A-Za-z0-9_-]{8,64}$/; // matches ChatRequest.session_id in backend/app/main.py

let current: string | null = null;
const listeners = new Set<() => void>();

export function newSessionId(): string {
  return `s-${crypto.randomUUID().replace(/-/g, "").slice(0, 24)}`;
}

function persist(id: string): void {
  try {
    sessionStorage.setItem(KEY, id);
  } catch {
    // Storage can be blocked (private mode). The in-memory id still works for this page view.
  }
}

function restore(): string | null {
  try {
    const saved = sessionStorage.getItem(KEY);
    return saved && ID_PATTERN.test(saved) ? saved : null;
  } catch {
    return null;
  }
}

/** Snapshot for useSyncExternalStore: stable until resetSessionId is called. */
export function getSessionId(): string {
  if (current === null) {
    current = restore() ?? newSessionId();
    persist(current);
  }
  return current;
}

export function getServerSessionId(): string {
  return "";
}

export function resetSessionId(): string {
  current = newSessionId();
  persist(current);
  listeners.forEach((notify) => notify());
  return current;
}

export function subscribeSessionId(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
