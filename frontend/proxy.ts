import { NextResponse, type NextRequest } from "next/server";

/**
 * Optimistic auth gate (Next 16 `proxy`, formerly `middleware`).
 *
 * Only checks that the `js_session` cookie is present on app paths. The real
 * check is `verifySession()` in the `(app)` layout, which asks the backend.
 */
const SESSION_COOKIE = "js_session";

export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();

  const { pathname, search } = request.nextUrl;
  const login = new URL("/login", request.url);
  login.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(login);
}

export const config = {
  // Positive list of app paths only. Everything else (the marketing page,
  // `/api`, `/_next`, `/p/*`, auth pages and static files) never runs proxy,
  // so uploads through the `/api` rewrite are not buffered.
  matcher: [
    "/trips/:path*",
    "/operators/:path*",
    "/analytics/:path*",
    "/settings/:path*",
    "/audit/:path*",
  ],
};
