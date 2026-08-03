"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { resetPassword } from "@/lib/api/fdd-client";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!token) {
      setError("Reset link is missing its token — request a new one.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      const res = await resetPassword(token, newPassword);
      if (!res.ok) {
        setError(res.message);
        return;
      }
      setDone(true);
    } catch {
      setError("Unable to reset password");
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
            <CardTitle className="text-2xl">Set a new password</CardTitle>
          </CardHeader>
          <CardContent>
            {done ? (
              <div className="space-y-4">
                <p className="text-sm text-emerald-300">
                  Your password has been reset. You can now sign in with your new password.
                </p>
                <Button type="button" className="w-full" onClick={() => router.push("/login")}>
                  Go to sign in
                </Button>
              </div>
            ) : (
              <form className="space-y-4" onSubmit={submit}>
                {!token ? (
                  <p className="text-sm text-rose-300">
                    This link is missing a reset token — request a new one from the{" "}
                    <button
                      type="button"
                      className="underline"
                      onClick={() => router.push("/forgot-password")}
                    >
                      forgot password
                    </button>{" "}
                    page.
                  </p>
                ) : null}
                <label className="block text-sm">
                  New password
                  <input
                    type="password"
                    required
                    className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Minimum 8 characters"
                  />
                </label>
                <label className="block text-sm">
                  Confirm new password
                  <input
                    type="password"
                    required
                    className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat your new password"
                  />
                </label>
                {error ? <p className="text-sm text-rose-300">{error}</p> : null}
                <Button type="submit" className="w-full" disabled={loading || !token}>
                  {loading ? "Resetting..." : "Reset password"}
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

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
