/** Archive materials are comma-separated. Product names may contain spaces. */
export function splitFilamentTypes(value: string | null | undefined): string[] {
  return [...new Set((value ?? '').split(',').map((part) => part.trim()).filter(Boolean))];
}
