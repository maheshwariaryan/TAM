"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { forgotPassword } from "@/lib/api/fdd-client";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ message: string; resetUrl: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await forgotPassword(email.trim().toLowerCase());
      if (!res.ok) {
        setError(res.message);
        return;
      }
      setResult({ message: res.message, resetUrl: res.reset_url });
    } catch {
      setError("Unable to request a password reset");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 px-6 py-14 text-slate-100">
      <div className="absolute inset-0 tam-grid opacity-40" />
      <div className="absolute left-1/2 top-20 h-72 w-72 -translate-x-1/2 rounded-full bg-cyan-400/20 blur-3xl" />

      <div className="relative mx-auto max-w-md">
        <Card className="border-white/20 bg-white/10 text-white backdrop-blur-xl">
          <CardHeader>
            <CardTitle className="text-2xl">Reset your password</CardTitle>
          </CardHeader>
          <CardContent>
            {result ? (
              <div className="space-y-4">
                <p className="text-sm text-slate-200">{result.message}</p>
                {result.resetUrl ? (
                  <div className="rounded-md border border-amber-400/30 bg-amber-500/10 px-3 py-2">
                    <p className="text-xs text-amber-200">
                      No email service is configured for this POC, so here is your reset link
                      directly:
                    </p>
                    <button
                      type="button"
                      className="mt-2 break-all text-left text-xs text-cyan-300 underline"
                      onClick={() => router.push(result.resetUrl)}
                    >
                      {result.resetUrl}
                    </button>
                  </div>
                ) : null}
                <Button type="button" className="w-full" onClick={() => router.push("/login")}>
                  Back to sign in
                </Button>
              </div>
            ) : (
              <form className="space-y-4" onSubmit={submit}>
                <label className="block text-sm">
                  Work email
                  <input
                    type="email"
                    required
                    className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="alex@acmecorp.com"
                  />
                </label>
                {error ? <p className="text-sm text-rose-300">{error}</p> : null}
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? "Sending..." : "Send reset link"}
                </Button>
              </form>
            )}
            <p className="mt-4 text-xs text-slate-300">
              <button type="button" className="underline" onClick={() => router.push("/login")}>
                Back to sign in
              </button>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
