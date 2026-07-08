"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const json = (await res.json()) as { ok?: boolean; message?: string; firstLogin?: boolean };
      if (!res.ok || !json.ok) {
        setError(json.message ?? "Unable to sign in");
        return;
      }
      router.push("/upload");
      router.refresh();
    } catch {
      setError("Unable to sign in");
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
            <CardTitle className="text-2xl">Sign in to TAM</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submit}>
              <label className="block text-sm">
                Username
                <input
                  className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="analyst@tam.com"
                />
              </label>
              <label className="block text-sm">
                Password
                <input
                  type="password"
                  className="mt-1 w-full rounded-md border border-white/25 bg-white/10 px-3 py-2 outline-none focus:border-cyan-300"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="********"
                />
              </label>
              {error ? <p className="text-sm text-rose-300">{error}</p> : null}
              <Button type="submit" className="w-full" disabled={loading}>{loading ? "Signing in..." : "Continue"}</Button>
            </form>
            <p className="mt-4 text-xs text-slate-300">
              Demo access is enabled for now. Use the credentials shared by the implementation note.
            </p>
            <p className="mt-2 text-xs text-slate-300">
              New analyst? <button type="button" className="underline" onClick={() => router.push("/signup")}>Sign up with company domain</button>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
