import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_ROUTES = ["/login", "/signup", "/welcome", "/forgot-password", "/reset-password"];

const PROTECTED_ROUTES = [
  "/dashboard",
  "/upload",
  "/financial-analysis",
  "/risk-assessment",
  "/customer-analytics",
  "/documents",
  "/inquiry",
  "/notes",
  "/reports",
  "/settings",
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  // Presence-only check — the cookie is httpOnly (readable server-side here,
  // just not from browser JS) and its actual validity is verified by FastAPI
  // on every API call via app/api/v1/deps.py::get_current_user. This is only
  // a routing convenience so an obviously logged-out visitor is redirected
  // before the page even renders.
  const isAuthenticated = request.cookies.has("tam_session");

  if (pathname === "/") {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Authenticated users visiting public routes go straight to upload
  if (PUBLIC_ROUTES.includes(pathname) && isAuthenticated) {
    return NextResponse.redirect(new URL("/upload", request.url));
  }

  // Unauthenticated users visiting protected routes go to login
  const isProtected = PROTECTED_ROUTES.some(
    (r) => pathname === r || pathname.startsWith(`${r}/`)
  );
  if (isProtected && !isAuthenticated) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!.*\\..*|_next).*)"],
};
