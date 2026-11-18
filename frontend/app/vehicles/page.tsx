"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { AppHeader } from "@/components/AppHeader";
import { TextField } from "@/components/TextField";
import { ApiError, apiFetch, errorMessage } from "@/lib/api";
import {
  cardClass,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "@/lib/styles";
import type { AuthResponse, Vehicle } from "@/lib/types";

export default function VehiclesPage() {
  const router = useRouter();
  const [auth, setAuth] = useState<AuthResponse | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [plate, setPlate] = useState("");
  const [model, setModel] = useState("");
  const [year, setYear] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const redirectIfUnauthorized = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.status === 401) {
        router.replace("/login");
        return true;
      }
      return false;
    },
    [router],
  );

  const loadVehicles = useCallback(async (query: string) => {
    const trimmed = query.trim();
    const suffix = trimmed ? `?search=${encodeURIComponent(trimmed)}` : "";
    setVehicles(await apiFetch<Vehicle[]>(`/api/v1/vehicles${suffix}`));
  }, []);

  useEffect(() => {
    let active = true;

    void (async () => {
      try {
        const me = await apiFetch<AuthResponse>("/api/v1/auth/me");
        if (!active) return;
        setAuth(me);
        await loadVehicles("");
      } catch (err) {
        if (active && !redirectIfUnauthorized(err)) {
          setError(errorMessage(err));
        }
      } finally {
        if (active) setLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [loadVehicles, redirectIfUnauthorized]);

  async function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRefreshing(true);
    setError(null);
    try {
      await loadVehicles(search);
    } catch (err) {
      if (!redirectIfUnauthorized(err)) setError(errorMessage(err));
    } finally {
      setRefreshing(false);
    }
  }

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      await apiFetch<Vehicle>("/api/v1/vehicles", {
        method: "POST",
        body: JSON.stringify({
          plate,
          model,
          year: year.trim() ? Number(year) : null,
        }),
      });
      setPlate("");
      setModel("");
      setYear("");
      await loadVehicles(search);
    } catch (err) {
      if (!redirectIfUnauthorized(err)) setCreateError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function onDelete(vehicle: Vehicle) {
    if (!window.confirm(`Удалить машину ${vehicle.plate}?`)) return;
    setError(null);
    try {
      await apiFetch<void>(`/api/v1/vehicles/${vehicle.id}`, { method: "DELETE" });
      await loadVehicles(search);
    } catch (err) {
      if (!redirectIfUnauthorized(err)) setError(errorMessage(err));
    }
  }

  async function onLogout() {
    setLoggingOut(true);
    try {
      await apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
    } catch {
      // Переход на логин всё равно очистит доступ к данным.
    } finally {
      router.replace("/login");
    }
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center text-slate-500" role="status">
        Загрузка…
      </main>
    );
  }

  if (!auth) {
    return null;
  }

  const canManage = auth.user.role === "admin" || auth.user.role === "manager";

  return (
    <div className="min-h-screen">
      <AppHeader auth={auth} onLogout={onLogout} loggingOut={loggingOut} />

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
        {error ? (
          <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        {canManage ? (
          <section className={`${cardClass} p-4 sm:p-6`} aria-labelledby="add-vehicle-title">
            <h2 id="add-vehicle-title" className="text-base font-semibold text-slate-900">
              Добавить машину
            </h2>
            <form
              className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_120px_auto] sm:items-end"
              onSubmit={onCreate}
            >
              <TextField
                label="Госномер"
                required
                maxLength={32}
                value={plate}
                onChange={(event) => setPlate(event.target.value)}
              />
              <TextField
                label="Модель"
                required
                maxLength={120}
                value={model}
                onChange={(event) => setModel(event.target.value)}
              />
              <TextField
                label="Год"
                type="number"
                min={1950}
                max={2100}
                value={year}
                onChange={(event) => setYear(event.target.value)}
              />
              <button type="submit" disabled={creating} className={primaryButtonClass}>
                {creating ? "Добавляем…" : "Добавить"}
              </button>
            </form>
            {createError ? (
              <p role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                {createError}
              </p>
            ) : null}
          </section>
        ) : null}

        <section className={cardClass} aria-labelledby="vehicle-list-title">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-4 sm:px-6">
            <h2 id="vehicle-list-title" className="text-base font-semibold text-slate-900">
              Машины организации
            </h2>
            <form role="search" className="flex w-full gap-2 sm:w-auto" onSubmit={onSearch}>
              <label htmlFor="vehicle-search" className="sr-only">
                Поиск по номеру или модели
              </label>
              <input
                id="vehicle-search"
                type="search"
                placeholder="Номер или модель"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className={`${inputClass} sm:w-64`}
              />
              <button type="submit" disabled={refreshing} className={secondaryButtonClass}>
                {refreshing ? "Ищем…" : "Найти"}
              </button>
            </form>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <caption className="sr-only">Машины организации</caption>
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium sm:px-6">
                    Госномер
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Модель
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Год
                  </th>
                  <th scope="col" className="px-4 py-3 text-right font-medium sm:px-6">
                    Действия
                  </th>
                </tr>
              </thead>
              <tbody>
                {vehicles.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-slate-500 sm:px-6">
                      Машин пока нет. Добавьте первую машину.
                    </td>
                  </tr>
                ) : (
                  vehicles.map((vehicle) => (
                    <tr key={vehicle.id} className="border-t border-slate-100">
                      <td className="px-4 py-3 font-medium text-slate-900 sm:px-6">
                        {vehicle.plate}
                      </td>
                      <td className="px-4 py-3 text-slate-700">{vehicle.model}</td>
                      <td className="px-4 py-3 text-slate-500">{vehicle.year ?? "—"}</td>
                      <td className="px-4 py-3 text-right sm:px-6">
                        {canManage ? (
                          <button
                            type="button"
                            onClick={() => void onDelete(vehicle)}
                            className="text-sm font-medium text-red-600 hover:text-red-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
                            aria-label={`Удалить машину ${vehicle.plate}`}
                          >
                            Удалить
                          </button>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
