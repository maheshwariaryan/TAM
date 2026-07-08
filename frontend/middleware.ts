import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_ROUTES = ["/login", "/signup", "/welcome"];

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
  "/deal-archive",
  "/onboarding",
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isAuthenticated = request.cookies.has("tam_auth");

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
