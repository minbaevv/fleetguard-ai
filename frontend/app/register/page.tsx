"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { AuthShell } from "@/components/AuthShell";
import { TextField } from "@/components/TextField";
import { apiFetch, errorMessage } from "@/lib/api";
import { primaryButtonClass } from "@/lib/styles";
import type { AuthResponse } from "@/lib/types";

export default function RegisterPage() {
  const router = useRouter();
  const [organizationName, setOrganizationName] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);

    try {
      await apiFetch<AuthResponse>("/api/v1/auth/register-org", {
        method: "POST",
        body: JSON.stringify({
          organization_name: organizationName,
          name,
          email,
          password,
        }),
      });
      router.replace("/vehicles");
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <AuthShell
      title="Регистрация организации"
      subtitle="Создайте парк и первого администратора. Менеджеров и водителей добавите позже."
      footer={
        <>
          Уже есть аккаунт?{" "}
          <Link className="auth-link" href="/login">
            Войти
          </Link>
        </>
      }
    >
      <form className="space-y-4" onSubmit={onSubmit}>
        <TextField
          label="Название организации"
          required
          minLength={2}
          maxLength={200}
          placeholder="Таксопарк «Бишкек»"
          value={organizationName}
          onChange={(event) => setOrganizationName(event.target.value)}
        />
        <TextField
          label="Ваше имя"
          required
          minLength={2}
          maxLength={200}
          autoComplete="name"
          placeholder="Айбек Осмонов"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <TextField
          label="Email"
          type="email"
          required
          autoComplete="email"
          placeholder="manager@fleet.kz"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <TextField
          label="Пароль"
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          placeholder="Минимум 8 символов"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {error ? (
          <p role="alert" className="callout callout-danger">
            {error}
          </p>
        ) : null}
        <button type="submit" disabled={pending} className={`${primaryButtonClass} w-full`}>
          {pending ? (
            <>
              <span
                aria-hidden="true"
                className="h-4 w-4 animate-spin rounded-full border-2 border-white/35 border-t-white"
              />
              Создаём…
            </>
          ) : (
            "Создать организацию"
          )}
        </button>
      </form>
    </AuthShell>
  );
}
