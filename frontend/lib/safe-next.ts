/** Only same-site absolute paths are allowed as a post-login destination. */
export function safeNext(value: string | string[] | undefined): string | null {
  const v = Array.isArray(value) ? value[0] : value;
  if (!v || !v.startsWith("/") || v.startsWith("//") || v.startsWith("/\\")) return null;
  if (v.startsWith("/login") || v.startsWith("/signup")) return null;
  return v;
}
