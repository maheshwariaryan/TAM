import { NextResponse } from "next/server";
import { z } from "zod";
import { cookies } from "next/headers";
import {
  isCorporateDomain,
  normalizeUsername,
  parseUserStoreCookie,
  serializeUserStoreCookie,
} from "@/lib/auth/cookie-utils";

// ─── Schema ────────────────────────────────────────────────────────────────
// companyDomain is now derived from the email — no longer a separate field.
// companyName, contactNumber, and manager are accepted but not required
// so the API is forward-compatible as the form evolves.
const bodySchema = z.object({
  email: z.string().email("Must be a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
  fullName: z.string().min(2, "Full name must be at least 2 characters."),
  companyName: z.string().min(1).optional(),
  contactNumber: z.string().optional(),
  manager: z.string().optional(),
});

export async function POST(request: Request) {
  // ── 1. Parse body ──────────────────────────────────────────────────────
  let rawBody: unknown;
  try {
    rawBody = await request.json();
    console.log("[signup] Received body:", JSON.stringify(rawBody));
  } catch (err) {
    console.error("[signup] Failed to parse request body as JSON:", err);
    return NextResponse.json(
      { ok: false, message: "Request body is not valid JSON." },
      { status: 400 }
    );
  }

  // ── 2. Validate with Zod ───────────────────────────────────────────────
  const parsed = bodySchema.safeParse(rawBody);
  if (!parsed.success) {
    // Log every field-level error so it shows up in the Next.js server console
    const fieldErrors = parsed.error.flatten().fieldErrors;
    console.error("[signup] Zod validation failed:", JSON.stringify(fieldErrors));

    // Surface the first human-readable message to the client
    const firstMessage =
      Object.values(fieldErrors).flat()[0] ?? "Invalid signup payload.";
    return NextResponse.json(
      { ok: false, message: firstMessage, debug: fieldErrors },
      { status: 400 }
    );
  }

  const { email: rawEmail, password, fullName, companyName, contactNumber, manager } =
    parsed.data;

  // ── 3. Normalise email ─────────────────────────────────────────────────
  const email = normalizeUsername(rawEmail);
  const emailDomain = email.split("@")[1] ?? "";
  console.log(`[signup] Normalised email: ${email} | domain: ${emailDomain}`);

  // ── 4. Corporate-domain check ──────────────────────────────────────────
  // Blocks known personal providers (gmail, hotmail, yahoo, etc.).
  // If you need to allow personal emails in dev/testing, set
  //   NEXT_PUBLIC_ALLOW_PERSONAL_EMAIL=true  in .env.local
  const allowPersonal = process.env.NEXT_PUBLIC_ALLOW_PERSONAL_EMAIL === "true";
  if (!allowPersonal && !isCorporateDomain(email)) {
    console.warn(`[signup] Blocked personal email domain: ${emailDomain}`);
    return NextResponse.json(
      {
        ok: false,
        message: `"${emailDomain}" is a personal email provider. Please use your company email address.`,
      },
      { status: 400 }
    );
  }

  // ── 5. Duplicate-account check ─────────────────────────────────────────
  const cookieStore = await cookies();
  const users = parseUserStoreCookie(cookieStore.get("tam_user_store")?.value);
  console.log(`[signup] Existing user count in cookie store: ${users.length}`);

  const exists = users.some((u) => normalizeUsername(u.username) === email);
  if (exists) {
    console.warn(`[signup] Account already exists for: ${email}`);
    return NextResponse.json(
      { ok: false, message: "An account with this email already exists. Please sign in." },
      { status: 409 }
    );
  }

  // ── 6. Persist new user ────────────────────────────────────────────────
  // companyDomain is derived from the email so it's always consistent.
  const updatedUsers = [
    ...users,
    {
      username: email,
      password,
      companyDomain: emailDomain,
      companyName: companyName ?? "",
      contactNumber: contactNumber ?? "",
      manager: manager ?? "",
    },
  ];
  console.log(`[signup] Creating account for: ${email} | company: ${companyName ?? "—"} | manager: ${manager ?? "—"}`);

  const response = NextResponse.json({
    ok: true,
    user: { name: fullName, username: email },
    firstLogin: true,
  });

  // Auth session cookie — expires in 8 hours
  const cookieOpts = {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
  };

  response.cookies.set("tam_user_store", serializeUserStoreCookie(updatedUsers), {
    ...cookieOpts,
    maxAge: 60 * 60 * 24 * 180, // 180 days
  });
  response.cookies.set("tam_auth", "1", { ...cookieOpts, maxAge: 60 * 60 * 8 });
  response.cookies.set("tam_user", email, { ...cookieOpts, maxAge: 60 * 60 * 8 });

  console.log(`[signup] Account created successfully for: ${email}`);
  return response;
}
