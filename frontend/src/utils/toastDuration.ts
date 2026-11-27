/**
 * Errors and warnings need time to read details; ordinary confirmations stay
 * brief. Longer informational messages (e.g. the iOS install instructions)
 * get reading time proportional to their length, capped at 10s.
 */
export function toastDuration(message: string, type: string): number {
  if (type === 'error' || type === 'warning') {
    return Math.max(10000, Math.min(30000, message.length * 60));
  }
  return Math.max(3000, Math.min(10000, message.length * 60));
}
