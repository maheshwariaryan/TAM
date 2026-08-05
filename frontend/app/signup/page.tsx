"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertTriangle } from "lucide-react";
import { signup } from "@/lib/api/fdd-client";

// ─── Debug helpers (visible in browser console) ────────────────────────────
const dbg = (step: string, msg: string, data?: unknown) => {
  const prefix = `[signup:${step}]`;
  if (data !== undefined) {
    console.log(prefix, msg, data);
  } else {
    console.log(prefix, msg);
  }
};
const dbgErr = (step: string, msg: string, data?: unknown) => {
  const prefix = `[signup:${step}] ❌`;
  console.error(prefix, msg, data ?? "");
};

// ─── Client-side field validation ──────────────────────────────────────────
function validateFields(fields: {
  fullName: string;
  companyName: string;
  email: string;
  password: string;
  confirmPassword: string;
}): string | null {
  if (fields.fullName.trim().length < 2) return "Full name must be at least 2 characters.";
  if (fields.companyName.trim().length < 1) return "Company name is required.";

  const emailRx = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRx.test(fields.email.trim())) return "Please enter a valid email address.";

  // Warn about personal email providers before the server rejects them
  const personalDomains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com", "icloud.com", "protonmail.com"];
  const domain = fields.email.split("@")[1]?.toLowerCase() ?? "";
  if (personalDomains.includes(domain)) {
    return `"${domain}" is a personal email. Please use your company email address.`;
  }

  if (fields.password.length < 8) return "Password must be at least 8 characters.";
  if (fields.password !== fields.confirmPassword) return "Passwords do not match.";

  return null; // all good
}

export default function SignupPage() {
  const router = useRouter();

  const [fullName, setFullName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [contactNumber, setContactNumber] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    dbg("submit", "Validating fields", { fullName, email, companyName });

    const validationError = validateFields({ fullName, companyName, email, password, confirmPassword });
    if (validationError) {
      dbgErr("submit", "Client-side validation failed", validationError);
      setError(validationError);
      return;
    }

    // companyName/contactNumber are collected for the workspace-setup UX but
    // the backend user model only has email/password/full_name today —
    // there's no field to persist them to yet, so only those three are sent.
    dbg("api", "Sending signup payload", {
      email: email.trim().toLowerCase(),
      fullName: fullName.trim(),
      password: "***", // never log the real password
    });

    setLoading(true);

    try {
      const result = await signup(email.trim().toLowerCase(), password, fullName.trim());

      if (!result.ok) {
        dbgErr("api", "Signup failed", result.message);
        setError(result.message);
        return;
      }

      dbg("api", "Signup successful — redirecting to /upload");
      router.push("/upload");
      router.refresh();

    } catch (networkErr) {
      dbgErr("api", "Network error during signup fetch", networkErr);
      setError("A network error occurred. Make sure the server is running and try again.");
    } finally {
      setLoading(false);
    }
  };

  const inputClass =
    "mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300 placeholder:text-slate-400 text-white";

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 px-6 py-14 text-slate-100">
      <div className="absolute inset-0 tam-grid opacity-40" />
      <div className="absolute left-1/2 top-20 h-72 w-72 -translate-x-1/2 rounded-full bg-emerald-400/20 blur-3xl" />

      <div className="relative mx-auto max-w-lg">
        {/* Header */}
        <div className="mb-8 text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-cyan-400">
            TAM — Financial Due Diligence
          </p>
          <h1 className="mt-2 text-3xl font-bold">Create your analyst account</h1>
          <p className="mt-1 text-sm text-slate-400">Set up your workspace in under a minute.</p>
        </div>

        <Card className="border-white/20 bg-white/10 text-white backdrop-blur-xl">
          <CardHeader>
            <CardTitle className="text-lg">Your details</CardTitle>
          </CardHeader>

          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit}>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-sm">
                  Full Name
                  <input
                    required
                    className={inputClass}
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Alex Analyst"
                  />
                </label>
                <label className="block text-sm">
                  Company Name
                  <input
                    required
                    className={inputClass}
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="Acme Capital"
                  />
                </label>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-sm">
                  Work Email
                  <input
                    required
                    type="email"
                    className={inputClass}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="alex@acmecorp.com"
                  />
                </label>
                <label className="block text-sm">
                  Contact Number
                  <input
                    type="tel"
                    className={inputClass}
                    value={contactNumber}
                    onChange={(e) => setContactNumber(e.target.value)}
                    placeholder="+1 555 000 0000"
                  />
                </label>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block text-sm">
                  Password
                  <input
                    required
                    type="password"
                    className={inputClass}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Minimum 8 characters"
                  />
                </label>
                <label className="block text-sm">
                  Confirm Password
                  <input
                    required
                    type="password"
                    className={inputClass}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat your password"
                  />
                </label>
              </div>

              {error && (
                <div className="flex items-start gap-2 rounded-md border border-rose-400/30 bg-rose-500/10 px-3 py-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
                  <p className="text-sm text-rose-300">{error}</p>
                </div>
              )}

              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Creating account…" : "Create account"}
              </Button>

              <p className="text-center text-xs text-slate-400">
                Already registered?{" "}
                <button
                  type="button"
                  className="underline hover:text-white"
                  onClick={() => router.push("/login")}
                >
                  Sign in
                </button>
              </p>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
