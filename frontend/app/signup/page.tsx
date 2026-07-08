"use client";

import { FormEvent, useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronDown, Check, AlertTriangle } from "lucide-react";

// ─── Manager list ───────────────────────────────────────────────────────────
// TODO: Replace with a real GET /api/managers?company={companyName} call
// once the backend endpoint exists. The list is intentionally broad for now.
const MOCK_MANAGERS = [
  "Aaron Mitchell", "Aisha Patel", "Alexandra Kim", "Benjamin Foster",
  "Caroline Hughes", "David Okafor", "Diana Reeves", "Edward Thornton",
  "Elena Vasquez", "Felix Hartmann", "Grace Liu", "Henry Blackwood",
  "Isabella Romano", "James Whitfield", "Jennifer Nakamura", "Jonathan Reed",
  "Julia Schreiber", "Kevin Osei", "Laura Sinclair", "Marcus Bell",
  "Maya Johansson", "Michael Adeyemi", "Natasha Kowalski", "Oliver Grant",
  "Priya Sharma", "Rachel Donovan", "Robert Castillo", "Sandra Müller",
  "Sophia Andersen", "Thomas Beaumont",
];

const COULD_NOT_FIND = "Could not find my manager";

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
function validateStepOne(fields: {
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

  // ── Step 1 state ──────────────────────────────────────────────────────
  const [fullName, setFullName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [contactNumber, setContactNumber] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // ── Step 2 state ──────────────────────────────────────────────────────
  const [managerQuery, setManagerQuery] = useState("");
  const [selectedManager, setSelectedManager] = useState<string | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // ── Shared state ──────────────────────────────────────────────────────
  const [step, setStep] = useState<1 | 2>(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debug field — shows raw server response in development
  const [debugDetail, setDebugDetail] = useState<string | null>(null);

  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Manager filtering ──────────────────────────────────────────────────
  const filteredManagers = managerQuery.trim()
    ? MOCK_MANAGERS.filter((m) => m.toLowerCase().includes(managerQuery.toLowerCase()))
    : MOCK_MANAGERS;

  // ── Step 1 submit ──────────────────────────────────────────────────────
  const handleStepOne = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setDebugDetail(null);

    dbg("step1", "Validating fields", { fullName, email, companyName });

    const validationError = validateStepOne({ fullName, companyName, email, password, confirmPassword });
    if (validationError) {
      dbgErr("step1", "Client-side validation failed", validationError);
      setError(validationError);
      return;
    }

    dbg("step1", "Validation passed — advancing to step 2");
    setStep(2);
  };

  // ── Manager selection ──────────────────────────────────────────────────
  const handleSelectManager = (name: string) => {
    dbg("step2", "Manager selected", name);
    setSelectedManager(name);
    setManagerQuery(name === COULD_NOT_FIND ? COULD_NOT_FIND : name);
    setDropdownOpen(false);
  };

  // ── Step 2 submit (API call) ───────────────────────────────────────────
  const handleStepTwo = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setDebugDetail(null);

    if (!selectedManager) {
      dbgErr("step2", "No manager selected");
      setError("Please select your manager to continue.");
      return;
    }

    const payload = {
      fullName: fullName.trim(),
      companyName: companyName.trim(),
      email: email.trim().toLowerCase(),
      contactNumber: contactNumber.trim(),
      password,
      manager: selectedManager,
    };

    dbg("api", "Sending signup payload", {
      ...payload,
      password: "***", // never log the real password
    });

    setLoading(true);

    try {
      const res = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      dbg("api", `Response status: ${res.status} ${res.statusText}`);

      // Always parse the body — even on error the server sends JSON
      let json: { ok?: boolean; message?: string; debug?: unknown } = {};
      try {
        json = await res.json();
        dbg("api", "Response body", json);
      } catch (parseErr) {
        dbgErr("api", "Could not parse response as JSON", parseErr);
        setError("Server returned an unexpected response. Check the console for details.");
        return;
      }

      if (!res.ok || !json.ok) {
        dbgErr("api", `Signup failed (HTTP ${res.status})`, json);

        // Show field-level debug info in development
        if (process.env.NODE_ENV !== "production" && json.debug) {
          setDebugDetail(JSON.stringify(json.debug, null, 2));
        }

        setError(json.message ?? `Signup failed (HTTP ${res.status}). Check the console for details.`);
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

        {/* Step indicator */}
        <div className="mb-6 flex items-center justify-center gap-3">
          {([1, 2] as const).map((s) => (
            <div key={s} className="flex items-center gap-2">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                  step === s
                    ? "bg-cyan-500 text-white"
                    : step > s
                      ? "bg-emerald-500 text-white"
                      : "border border-white/25 text-slate-400"
                }`}
              >
                {step > s ? <Check className="h-3.5 w-3.5" /> : s}
              </div>
              <span className={`text-xs ${step === s ? "text-white" : "text-slate-500"}`}>
                {s === 1 ? "Account details" : "Confirm manager"}
              </span>
              {s < 2 && <div className="h-px w-8 bg-white/20" />}
            </div>
          ))}
        </div>

        <Card className="border-white/20 bg-white/10 text-white backdrop-blur-xl">
          <CardHeader>
            <CardTitle className="text-lg">
              {step === 1 ? "Your details" : "Who is your manager?"}
            </CardTitle>
            {step === 2 && (
              <p className="text-sm text-slate-400">
                Start typing to filter the list. Select your manager to complete sign-up.
              </p>
            )}
          </CardHeader>

          <CardContent>
            {/* ── STEP 1 ─────────────────────────────────────────────── */}
            {step === 1 && (
              <form className="space-y-4" onSubmit={handleStepOne}>
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

                <Button type="submit" className="w-full">
                  Next →
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
            )}

            {/* ── STEP 2 ─────────────────────────────────────────────── */}
            {step === 2 && (
              <form className="space-y-4" onSubmit={handleStepTwo}>
                <div ref={dropdownRef} className="relative">
                  <label className="block text-sm">
                    Manager&apos;s Name
                    <div className="relative mt-1">
                      <input
                        autoFocus
                        className={`${inputClass} pr-9`}
                        value={managerQuery}
                        onChange={(e) => {
                          setManagerQuery(e.target.value);
                          setSelectedManager(null);
                          setDropdownOpen(true);
                        }}
                        onFocus={() => setDropdownOpen(true)}
                        placeholder="Start typing a name…"
                      />
                      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    </div>
                  </label>

                  {dropdownOpen && (
                    <div className="absolute z-50 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-white/20 bg-slate-900 shadow-xl">
                      {filteredManagers.length === 0 ? (
                        <p className="px-3 py-2 text-sm text-slate-400">No matches found.</p>
                      ) : (
                        filteredManagers.map((name) => (
                          <button
                            key={name}
                            type="button"
                            onMouseDown={() => handleSelectManager(name)}
                            className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-white/10 ${
                              selectedManager === name ? "bg-cyan-500/20 text-cyan-300" : "text-slate-200"
                            }`}
                          >
                            {selectedManager === name
                              ? <Check className="h-3.5 w-3.5 shrink-0 text-cyan-400" />
                              : <span className="w-3.5 shrink-0" />
                            }
                            {name}
                          </button>
                        ))
                      )}

                      {/* Always-visible fallback */}
                      <button
                        type="button"
                        onMouseDown={() => handleSelectManager(COULD_NOT_FIND)}
                        className={`flex w-full items-center gap-2 border-t border-white/10 px-3 py-2 text-left text-sm italic hover:bg-white/10 ${
                          selectedManager === COULD_NOT_FIND ? "bg-amber-500/20 text-amber-300" : "text-slate-400"
                        }`}
                      >
                        {selectedManager === COULD_NOT_FIND
                          ? <Check className="h-3.5 w-3.5 shrink-0 text-amber-400" />
                          : <span className="w-3.5 shrink-0" />
                        }
                        {COULD_NOT_FIND}
                      </button>
                    </div>
                  )}
                </div>

                {/* Confirmation pill */}
                {selectedManager && (
                  <p className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm">
                    {selectedManager === COULD_NOT_FIND ? (
                      <span className="text-amber-300">
                        No manager linked — your account will be flagged for admin review.
                      </span>
                    ) : (
                      <span className="text-emerald-300">
                        Manager selected: <strong>{selectedManager}</strong>
                      </span>
                    )}
                  </p>
                )}

                {/* Error */}
                {error && (
                  <div className="flex items-start gap-2 rounded-md border border-rose-400/30 bg-rose-500/10 px-3 py-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
                    <div>
                      <p className="text-sm text-rose-300">{error}</p>
                      {/* Dev-only detail box */}
                      {debugDetail && (
                        <pre className="mt-2 max-h-32 overflow-auto rounded bg-black/40 p-2 text-[10px] text-rose-200">
                          {debugDetail}
                        </pre>
                      )}
                    </div>
                  </div>
                )}

                <div className="flex gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1 border-white/25 text-white hover:bg-white/10"
                    onClick={() => { setStep(1); setError(null); setDebugDetail(null); }}
                  >
                    ← Back
                  </Button>
                  <Button
                    type="submit"
                    className="flex-1"
                    disabled={loading || !selectedManager}
                  >
                    {loading ? "Creating account…" : "Complete sign-up"}
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
