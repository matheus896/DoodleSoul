export const ACTIVE_SESSION_ID_STORAGE_KEY = "animism.active_session_id";

export function writeActiveSessionId(sessionId: string): void {
  window.localStorage.setItem(ACTIVE_SESSION_ID_STORAGE_KEY, sessionId);
}

export function readActiveSessionId(): string | null {
  return window.localStorage.getItem(ACTIVE_SESSION_ID_STORAGE_KEY);
}
