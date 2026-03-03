/**
 * debugSink — in-memory ring buffer + console logger for Epic 3 observability.
 *
 * Toggle: set ``VITE_DEBUG_MEDIA=true`` in the environment.
 * Off by default; normal runs are not polluted.
 *
 * Debug contract fields (aligned with backend ``debug_tracer.py``):
 *   session_id, scene_id, event_type, source, timestamp_ms
 *
 * Ring buffer holds the last {@link RING_CAPACITY} entries; older entries
 * are evicted automatically.  Expose to the browser console with:
 *   ``window.__animismDebugRing()``   (wired in App.tsx)
 *
 * Logging policy: only metadata and event envelopes are logged.
 * Raw audio bytes and PII must never appear in log entries.
 */

// ---------------------------------------------------------------------------
// Toggle (read once at module load)
// ---------------------------------------------------------------------------

const DEBUG_ENABLED: boolean =
  typeof import.meta !== "undefined" &&
  (import.meta as { env?: Record<string, string> }).env?.VITE_DEBUG_MEDIA === "true";

// ---------------------------------------------------------------------------
// Debug contract
// ---------------------------------------------------------------------------

export interface DebugEntry {
  readonly event_type: string;
  readonly source: string;
  readonly scene_id?: string;
  readonly session_id?: string;
  readonly timestamp_ms: number;
  readonly [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Ring buffer (module-level singleton)
// ---------------------------------------------------------------------------

const RING_CAPACITY = 200;
const _ring: DebugEntry[] = [];

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Log a debug entry to the ring buffer and browser console.
 * No-op when the debug toggle is off.
 */
export function debugLog(
  entry: Omit<DebugEntry, "timestamp_ms">,
): void {
  if (!DEBUG_ENABLED) {
    return;
  }
  const full: DebugEntry = { ...entry, timestamp_ms: Date.now() };
  if (_ring.length >= RING_CAPACITY) {
    _ring.shift();
  }
  _ring.push(full);
  // eslint-disable-next-line no-console
  console.debug("[ANIMISM_DEBUG]", full);
}

/**
 * Return a snapshot of the current ring buffer contents.
 * Useful for programmatic inspection in tests or browser console.
 */
export function getDebugRing(): readonly DebugEntry[] {
  return _ring as readonly DebugEntry[];
}

/**
 * Clear the ring buffer.  Used in tests to isolate state between cases.
 * @internal
 */
export function _clearRing(): void {
  _ring.length = 0;
}

/**
 * Return whether the debug toggle is enabled.
 * Useful for conditional debug paths in callers.
 */
export function isDebugEnabled(): boolean {
  return DEBUG_ENABLED;
}
