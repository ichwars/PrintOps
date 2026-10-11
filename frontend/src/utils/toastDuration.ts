/** Errors and warnings need time to read details; ordinary confirmations stay brief. */
export function toastDuration(message: string, type: string): number {
  return type === 'error' || type === 'warning'
    ? Math.max(10000, Math.min(30000, message.length * 60))
    : 3000;
}
