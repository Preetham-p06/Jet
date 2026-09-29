import { ApiError } from "@/lib/api/client";

/** Human copy for auth failures; falls back to the backend's `detail`. */
export function authErrorMessage(e: unknown, context: "login" | "signup"): string {
  if (e instanceof DOMException && e.name === "AbortError") return "Request cancelled.";
  if (!(e instanceof ApiError)) {
    return "Can't reach JetStream right now. Check your connection and try again.";
  }
  if (context === "login" && (e.status === 401 || e.status === 400)) {
    return "That email and password don't match an account.";
  }
  if (e.status === 403) return e.message || "This account is disabled. Ask a workspace admin for access.";
  if (e.status === 409) return e.message || "An account with that email already exists.";
  if (e.status === 422) return e.message || "Please check the highlighted fields.";
  if (e.status === 429) return "Too many attempts. Wait a minute and try again.";
  if (e.status >= 500) return "Something went wrong on our side. Try again in a moment.";
  return e.message;
}
