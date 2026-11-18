"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { AuthShell } from "@/components/AuthShell";
import { TextField } from "@/components/TextField";
import { apiFetch, errorMessage } from "@/lib/api";
import { primaryButtonClass } from "@/lib/styles";
import type { AuthResponse } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);

    try {
      await apiFetch<AuthResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      router.replace("/vehicles");
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <AuthShell
      title="Вход"
      subtitle="Войдите, чтобы видеть машины и осмотры своей организации."
      footer={
        <>
          Нет аккаунта?{" "}
          <Link className="font-medium text-indigo-600 hover:text-indigo-700" href="/register">
            Зарегистрировать организацию
          </Link>
        </>
      }
    >
      <form className="space-y-4" onSubmit={onSubmit}>
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <TextField
          label="Пароль"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {error ? (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        ) : null}
        <button type="submit" disabled={pending} className={`${primaryButtonClass} w-full`}>
          {pending ? "Входим…" : "Войти"}
        </button>
      </form>
    </AuthShell>
  );
}
