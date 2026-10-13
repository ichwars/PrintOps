/** Only invoke with a callback returned and validated by the backend. */
export function connectCallbackUrl(callback: string, state: string | null, result: { code: string } | { error: string }): string {
  const url = new URL(callback);
  url.searchParams.delete('code');
  url.searchParams.delete('error');
  url.searchParams.delete('state');
  for (const [key, value] of Object.entries(result)) url.searchParams.set(key, value);
  if (state !== null) url.searchParams.set('state', state);
  return url.toString();
}
