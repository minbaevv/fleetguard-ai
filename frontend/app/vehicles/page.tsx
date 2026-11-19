"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { AppHeader } from "@/components/AppHeader";
import { LoadingScreen } from "@/components/LoadingScreen";
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
  const [appliedSearch, setAppliedSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);

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
    setAppliedSearch(trimmed);
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

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3600);
    return () => window.clearTimeout(timer);
  }, [notice]);

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
      const createdPlate = plate;
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
      setNotice(`Машина ${createdPlate} добавлена в парк`);
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
      setNotice(`Машина ${vehicle.plate} удалена`);
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
    return <LoadingScreen label="Собираем парк…" />;
  }

  if (!auth) {
    return null;
  }

  const canManage = auth.user.role === "admin" || auth.user.role === "manager";
  const hasSearch = appliedSearch.length > 0;

  return (
    <div className="min-h-screen pb-16">
      <AppHeader auth={auth} onLogout={onLogout} loggingOut={loggingOut} />

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6">
        {error ? (
          <p role="alert" className="callout callout-danger reveal">
            {error}
          </p>
        ) : null}

        <section className="hero-panel reveal" aria-labelledby="fleet-title">
          <div className="relative z-10 p-6 sm:p-8">
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-center">
              <div className="min-w-0">
                <span className="eyebrow">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-300" />
                  Панель автопарка
                </span>
                <h1
                  id="fleet-title"
                  className="mt-4 text-3xl font-semibold leading-[1.08] tracking-[-0.025em] text-white sm:text-[2.55rem]"
                >
                  Парк <span className="text-gradient">под контролем</span>
                </h1>
                <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-400 sm:text-[0.95rem]">
                  Снимайте машину до и после смены. Система проверит кадры, сохранит
                  историю и покажет только новые повреждения.
                </p>

                <div className="mt-6 grid max-w-xl grid-cols-2 gap-2.5 sm:grid-cols-3">
                  <div className="stat-tile">
                    <p className="text-[0.66rem] font-semibold uppercase tracking-[0.16em] text-slate-500">
                      {hasSearch ? "Найдено" : "Машин в парке"}
                    </p>
                    <p className="mt-1 text-2xl font-semibold tracking-tight text-white">
                      {vehicles.length}
                    </p>
                    <p className="mt-0.5 text-[0.7rem] text-slate-500">
                      {hasSearch ? `по запросу «${appliedSearch}»` : "в организации"}
                    </p>
                  </div>
                  <div className="stat-tile">
                    <p className="text-[0.66rem] font-semibold uppercase tracking-[0.16em] text-slate-500">
                      Сторон осмотра
                    </p>
                    <p className="mt-1 text-2xl font-semibold tracking-tight text-white">4</p>
                    <p className="mt-0.5 text-[0.7rem] text-slate-500">перед · зад · борта</p>
                  </div>
                  <div className="stat-tile col-span-2 sm:col-span-1">
                    <p className="text-[0.66rem] font-semibold uppercase tracking-[0.16em] text-slate-500">
                      Проверка кадров
                    </p>
                    <p className="mt-1 text-2xl font-semibold tracking-tight text-cyan-200">AI</p>
                    <p className="mt-0.5 text-[0.7rem] text-slate-500">качество и повреждения</p>
                  </div>
                </div>
              </div>

              <div className="panel-soft relative overflow-hidden p-4 sm:p-5">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[0.64rem] font-semibold uppercase tracking-[0.18em] text-slate-500">
                    Быстрый старт
                  </p>
                  <span className="pill tone-cyan">4 фото</span>
                </div>
                <p className="mt-3 text-sm font-semibold text-white">Новый осмотр «до»</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">
                  Снимите машину с четырёх сторон — качество каждого кадра проверим сразу.
                </p>
                <Link href="/inspections/new" className={`${primaryButtonClass} mt-4 w-full`}>
                  Начать осмотр
                  <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
                    <path
                      d="M5 12h13M13 6l6 6-6 6"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </Link>
                {canManage ? (
                  <button
                    type="button"
                    onClick={() => setFormOpen((current) => !current)}
                    className={`${secondaryButtonClass} mt-2 w-full`}
                    aria-expanded={formOpen}
                  >
                    Добавить машину
                  </button>
                ) : null}
                <p className="mt-3 flex items-center gap-2 text-[0.68rem] text-slate-500">
                  <span className="h-1.5 w-1.5 flex-none rounded-full bg-emerald-400 shadow-[0_0_0_3px_rgba(52,211,153,0.14)]" />
                  Ссылки на фото подписанные
                </p>
              </div>
            </div>
          </div>
        </section>

        {canManage && formOpen ? (
          <section
            id="add-vehicle"
            className={`${cardClass} reveal p-5 sm:p-6`}
            aria-labelledby="add-vehicle-title"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 id="add-vehicle-title" className="text-base font-semibold text-white">
                  Добавить машину
                </h2>
                <p className="mt-1 text-xs text-slate-500">
                  Госномер и модель обязательны, год можно указать позже.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setFormOpen(false)}
                className="btn btn-secondary btn-icon"
                aria-label="Закрыть форму добавления"
              >
                <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
                  <path
                    d="M6 6l12 12M18 6 6 18"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>

            <form
              className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_120px_auto] sm:items-end"
              onSubmit={onCreate}
            >
              <TextField
                label="Госномер"
                required
                maxLength={32}
                placeholder="01KG123ABC"
                value={plate}
                onChange={(event) => setPlate(event.target.value)}
              />
              <TextField
                label="Модель"
                required
                maxLength={120}
                placeholder="Toyota Camry"
                value={model}
                onChange={(event) => setModel(event.target.value)}
              />
              <TextField
                label="Год"
                type="number"
                min={1950}
                max={2100}
                placeholder="2020"
                value={year}
                onChange={(event) => setYear(event.target.value)}
              />
              <button type="submit" disabled={creating} className={primaryButtonClass}>
                {creating ? "Добавляем…" : "Добавить"}
              </button>
            </form>
            {createError ? (
              <p role="alert" className="callout callout-danger mt-3">
                {createError}
              </p>
            ) : null}
          </section>
        ) : null}

        <section
          className={`${cardClass} reveal overflow-hidden`}
          style={{ animationDelay: "70ms" }}
          aria-labelledby="vehicle-list-title"
        >
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-4 sm:px-6">
            <div>
              <h2 id="vehicle-list-title" className="text-base font-semibold text-white">
                Машины организации
              </h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Выберите машину, чтобы начать осмотр
              </p>
            </div>
            <form role="search" className="flex w-full gap-2 sm:w-auto" onSubmit={onSearch}>
              <div className="relative w-full sm:w-64">
                <label htmlFor="vehicle-search" className="sr-only">
                  Поиск по номеру или модели
                </label>
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                  className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
                >
                  <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.6" />
                  <path
                    d="m16 16 4 4"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                </svg>
                <input
                  id="vehicle-search"
                  type="search"
                  placeholder="Номер или модель"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  className={`${inputClass} pl-9`}
                />
              </div>
              <button type="submit" disabled={refreshing} className={secondaryButtonClass}>
                {refreshing ? "Ищем…" : "Найти"}
              </button>
            </form>
          </div>

          {vehicles.length === 0 ? (
            <div className="px-6 py-14 text-center">
              <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.06] text-cyan-200">
                <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7" aria-hidden="true">
                  <path
                    d="M4 16V9.5A2.5 2.5 0 0 1 6.5 7h1.2l1.6-2h5.4l1.6 2h1.2A2.5 2.5 0 0 1 20 9.5V16M4 16h16M4 16v2m16-2v2"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <circle cx="8" cy="13" r="1.2" fill="currentColor" />
                  <circle cx="16" cy="13" r="1.2" fill="currentColor" />
                </svg>
              </span>
              <p className="mt-4 text-sm font-semibold text-white">
                {hasSearch ? "Ничего не найдено" : "В парке пока нет машин"}
              </p>
              <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-slate-500">
                {hasSearch
                  ? "Попробуйте другой номер или модель — поиск идёт по обоим полям."
                  : "Добавьте первую машину, чтобы водители могли начать фотофиксацию."}
              </p>
              {canManage && !hasSearch ? (
                <button
                  type="button"
                  onClick={() => setFormOpen(true)}
                  className={`${primaryButtonClass} mt-5`}
                >
                  Добавить первую машину
                </button>
              ) : null}
            </div>
          ) : (
            <>
              <div className="hidden overflow-x-auto sm:block">
                <table className="data-table text-left text-sm">
                  <caption className="sr-only">Машины организации</caption>
                  <thead>
                    <tr>
                      <th scope="col">Госномер</th>
                      <th scope="col">Модель</th>
                      <th scope="col">Год</th>
                      <th scope="col" className="text-right">
                        Действия
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {vehicles.map((vehicle, index) => (
                      <tr
                        key={vehicle.id}
                        className="reveal"
                        style={{ animationDelay: `${Math.min(index, 8) * 45}ms` }}
                      >
                        <td>
                          <span className="plate-badge">{vehicle.plate}</span>
                        </td>
                        <td className="font-medium text-slate-200">{vehicle.model}</td>
                        <td className="text-slate-500">{vehicle.year ?? "—"}</td>
                        <td>
                          <div className="flex items-center justify-end gap-2">
                            <Link
                              href={`/inspections/new?vehicleId=${vehicle.id}`}
                              className="row-link"
                              aria-label={`Начать осмотр машины ${vehicle.plate}`}
                            >
                              Осмотр
                              <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                className="h-3.5 w-3.5"
                                aria-hidden="true"
                              >
                                <path
                                  d="M5 12h13M13 6l6 6-6 6"
                                  stroke="currentColor"
                                  strokeWidth="1.8"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                />
                              </svg>
                            </Link>
                            {canManage ? (
                              <button
                                type="button"
                                onClick={() => void onDelete(vehicle)}
                                className="row-danger"
                                aria-label={`Удалить машину ${vehicle.plate}`}
                              >
                                Удалить
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <ul className="divide-y divide-white/[0.06] sm:hidden">
                {vehicles.map((vehicle, index) => (
                  <li
                    key={vehicle.id}
                    className="reveal flex items-center justify-between gap-3 px-4 py-3.5"
                    style={{ animationDelay: `${Math.min(index, 8) * 45}ms` }}
                  >
                    <div className="min-w-0">
                      <span className="plate-badge">{vehicle.plate}</span>
                      <p className="mt-1.5 truncate text-sm font-medium text-slate-200">
                        {vehicle.model}
                        {vehicle.year ? (
                          <span className="ml-2 text-xs font-normal text-slate-500">
                            {vehicle.year}
                          </span>
                        ) : null}
                      </p>
                    </div>
                    <div className="flex flex-none items-center gap-1">
                      <Link
                        href={`/inspections/new?vehicleId=${vehicle.id}`}
                        className="row-link"
                        aria-label={`Начать осмотр машины ${vehicle.plate}`}
                      >
                        Осмотр
                      </Link>
                      {canManage ? (
                        <button
                          type="button"
                          onClick={() => void onDelete(vehicle)}
                          className="row-danger"
                          aria-label={`Удалить машину ${vehicle.plate}`}
                        >
                          Удалить
                        </button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </main>

      {notice ? (
        <div className="toast" role="status" aria-live="polite">
          <span className="toast-dot" aria-hidden="true" />
          {notice}
        </div>
      ) : null}
    </div>
  );
}
