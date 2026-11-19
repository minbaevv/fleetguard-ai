"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppHeader } from "@/components/AppHeader";
import { ApiError, apiFetch, errorMessage } from "@/lib/api";
import {
  PHOTO_SIDES,
  inspectionKindLabels,
  inspectionStatusLabels,
  qualityFlagLabel,
  sideLabels,
} from "@/lib/labels";
import { cardClass, secondaryButtonClass } from "@/lib/styles";
import type {
  AuthResponse,
  InspectionDetail,
  InspectionStatus,
  Vehicle,
} from "@/lib/types";

interface InspectionDetailsProps {
  inspectionId: string;
}

const POLL_INTERVAL_MS = 5000;
const MAX_POLLS = 12;

const statusTone: Record<InspectionStatus, string> = {
  draft: "bg-slate-100 text-slate-700",
  uploading: "bg-amber-100 text-amber-900",
  processing: "bg-amber-100 text-amber-900",
  done: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-700",
};

const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
  dateStyle: "long",
  timeStyle: "short",
});

function formatDate(value: string): string {
  return dateFormatter.format(new Date(value));
}

function isPending(status: InspectionStatus): boolean {
  return status === "uploading" || status === "processing";
}

export function InspectionDetails({ inspectionId }: InspectionDetailsProps) {
  const router = useRouter();

  const [auth, setAuth] = useState<AuthResponse | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [detail, setDetail] = useState<InspectionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [pollCount, setPollCount] = useState(0);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(
    async (silent = false): Promise<InspectionDetail | null> => {
      if (!silent) setRefreshing(true);
      try {
        const next = await apiFetch<InspectionDetail>(`/api/v1/inspections/${inspectionId}`);
        setDetail(next);
        setNotFound(false);
        setError(null);
        return next;
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
          return null;
        }
        if (err instanceof ApiError && err.status === 404) {
          setDetail(null);
          setNotFound(true);
          return null;
        }
        setError(errorMessage(err));
        return null;
      } finally {
        if (!silent) setRefreshing(false);
      }
    },
    [inspectionId, router],
  );

  useEffect(() => {
    let active = true;

    void (async () => {
      try {
        const [me, list] = await Promise.all([
          apiFetch<AuthResponse>("/api/v1/auth/me"),
          apiFetch<Vehicle[]>("/api/v1/vehicles"),
        ]);
        if (!active) return;
        setAuth(me);
        setVehicles(list);
        await loadDetail();
      } catch (err) {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
        setError(errorMessage(err));
      } finally {
        if (active) setLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [loadDetail, router]);

  // Пока идёт обработка, статус подтягивается сам; после лимита остаётся кнопка «Обновить».
  useEffect(() => {
    if (!detail || !isPending(detail.status) || pollCount >= MAX_POLLS) return;

    const timer = window.setTimeout(() => {
      void (async () => {
        const next = await loadDetail(true);
        setPollCount((current) => (next ? current + 1 : MAX_POLLS));
      })();
    }, POLL_INTERVAL_MS);

    return () => window.clearTimeout(timer);
  }, [detail, loadDetail, pollCount]);

  function onRefresh() {
    setPollCount(0);
    void loadDetail();
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
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-4 text-center">
        <p role="alert" className="text-sm text-red-700">
          {error ?? "Не удалось загрузить профиль."}
        </p>
        <Link href="/login" className={secondaryButtonClass}>
          Войти заново
        </Link>
      </main>
    );
  }

  const vehicle = detail
    ? (vehicles.find((item) => item.id === detail.vehicle_id) ?? null)
    : null;
  const photos = new Map(detail?.photos.map((photo) => [photo.side, photo]) ?? []);
  const flaggedCount =
    detail?.photos.filter((photo) => (photo.quality_flags?.length ?? 0) > 0).length ?? 0;
  const pollingStopped = pollCount >= MAX_POLLS;

  return (
    <div className="min-h-screen">
      <AppHeader auth={auth} onLogout={onLogout} loggingOut={loggingOut} title="Осмотр" />

      <main className="mx-auto max-w-4xl space-y-4 px-4 py-6 sm:px-6">
        <div className="flex items-center justify-between gap-3">
          <Link
            href="/vehicles"
            className="text-sm font-medium text-indigo-600 hover:text-indigo-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
          >
            ← К списку машин
          </Link>
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className={secondaryButtonClass}
          >
            {refreshing ? "Обновляем…" : "Обновить"}
          </button>
        </div>

        {error ? (
          <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        {notFound ? (
          <section className={`${cardClass} p-6 text-center sm:p-8`}>
            <h2 className="text-xl font-semibold text-slate-900">Осмотр не найден</h2>
            <p className="mt-2 text-sm text-slate-600">
              Ссылка устарела или осмотр принадлежит другой организации.
            </p>
            <Link href="/vehicles" className={`${secondaryButtonClass} mt-6`}>
              К списку машин
            </Link>
          </section>
        ) : null}

        {detail ? (
          <>
            <section className={`${cardClass} p-4 sm:p-6`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
                    Осмотр {inspectionKindLabels[detail.kind]}
                  </p>
                  <h2 className="mt-1 text-xl font-semibold text-slate-900">
                    {vehicle ? `${vehicle.plate} · ${vehicle.model}` : "Машина"}
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">
                    Начат {formatDate(detail.created_at)}
                    {detail.finished_at ? ` · завершён ${formatDate(detail.finished_at)}` : ""}
                  </p>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${statusTone[detail.status]}`}
                >
                  {inspectionStatusLabels[detail.status]}
                </span>
              </div>

              {isPending(detail.status) ? (
                <div className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  <p className="font-medium">Осмотр обрабатывается.</p>
                  <p className="mt-1">
                    {pollingStopped
                      ? "Автообновление остановлено. Нажмите «Обновить», чтобы проверить статус."
                      : "Статус обновляется автоматически каждые 5 секунд."}
                  </p>
                </div>
              ) : null}

              {detail.status === "failed" ? (
                <div role="alert" className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
                  <p className="font-medium">Обработка не удалась.</p>
                  {detail.failure_reason ? <p className="mt-1">{detail.failure_reason}</p> : null}
                </div>
              ) : null}

              <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-sm">
                <div>
                  <dt className="text-slate-500">Фото</dt>
                  <dd className="mt-0.5 font-medium text-slate-900">
                    {detail.photos.length} из {PHOTO_SIDES.length}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">С замечаниями</dt>
                  <dd className="mt-0.5 font-medium text-slate-900">{flaggedCount}</dd>
                </div>
              </dl>
            </section>

            <section className={`${cardClass} p-4 sm:p-6`}>
              <h2 className="text-lg font-semibold text-slate-900">Фото</h2>
              <p className="mt-1 text-sm text-slate-600">
                Ссылки на фото временные. Обновление страницы продлевает их.
              </p>

              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                {PHOTO_SIDES.map((side) => {
                  const photo = photos.get(side);
                  const flags = photo?.quality_flags ?? [];

                  return (
                    <figure
                      key={side}
                      className="overflow-hidden rounded-xl border border-slate-200"
                    >
                      <div className="relative aspect-[4/3] bg-slate-100">
                        {photo ? (
                          <div
                            role="img"
                            aria-label={`Фото машины: ${sideLabels[side].toLowerCase()}`}
                            className="absolute inset-0 bg-cover bg-center"
                            style={{ backgroundImage: `url(${photo.url})` }}
                          />
                        ) : (
                          <span className="absolute inset-0 flex items-center justify-center text-sm text-slate-400">
                            Нет фото
                          </span>
                        )}
                      </div>
                      <figcaption className="border-t border-slate-100 px-3 py-2">
                        <p className="text-sm font-medium text-slate-900">{sideLabels[side]}</p>
                        {flags.length > 0 ? (
                          <p className="mt-1 text-xs text-amber-800">
                            С замечаниями: {flags.map(qualityFlagLabel).join(", ")}
                          </p>
                        ) : null}
                      </figcaption>
                    </figure>
                  );
                })}
              </div>
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}
