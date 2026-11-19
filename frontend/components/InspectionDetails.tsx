"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppHeader } from "@/components/AppHeader";
import { LoadingScreen } from "@/components/LoadingScreen";
import { ApiError, apiFetch, errorMessage } from "@/lib/api";
import {
  PHOTO_SIDES,
  inspectionKindLabels,
  inspectionStatusLabels,
  qualityFlagLabel,
  sideLabels,
} from "@/lib/labels";
import { cardClass, primaryButtonClass, secondaryButtonClass } from "@/lib/styles";
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
  draft: "tone-slate",
  uploading: "tone-amber",
  processing: "tone-amber",
  done: "tone-emerald",
  failed: "tone-red",
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

type StepState = "done" | "active" | "error" | "todo";

interface TimelineStep {
  title: string;
  text: string;
  state: StepState;
}

function buildTimeline(detail: InspectionDetail): TimelineStep[] {
  const photoCount = detail.photos.length;
  const photosDone = photoCount === PHOTO_SIDES.length;
  const pending = isPending(detail.status);
  const done = detail.status === "done";
  const failed = detail.status === "failed";

  return [
    {
      title: "Осмотр создан",
      text: formatDate(detail.created_at),
      state: "done",
    },
    {
      title: "Фото загружены",
      text: `${photoCount} из ${PHOTO_SIDES.length} сторон`,
      state: photosDone ? "done" : detail.status === "draft" ? "active" : "todo",
    },
    {
      title: "Обработка кадров",
      text: failed
        ? (detail.failure_reason ?? "Обработка не удалась")
        : done
          ? "Повреждения найдены и сравнены"
          : pending
            ? "Проверяем кадры и ищем повреждения"
            : "Начнётся после загрузки фото",
      state: failed ? "error" : done ? "done" : pending ? "active" : "todo",
    },
    {
      title: "Акт осмотра",
      text: done
        ? "Отчёт готов к просмотру"
        : failed
          ? "Акт не сформирован"
          : "Появится после обработки",
      state: done ? "done" : "todo",
    },
  ];
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
    return <LoadingScreen label="Загружаем осмотр…" />;
  }

  if (!auth) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-4 text-center">
        <p role="alert" className="callout callout-danger w-full">
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
  const timeline = detail ? buildTimeline(detail) : [];

  return (
    <div className="min-h-screen pb-16">
      <AppHeader auth={auth} onLogout={onLogout} loggingOut={loggingOut} title="Осмотр" />

      <main className="mx-auto max-w-4xl space-y-4 px-4 py-6 sm:px-6">
        <div className="flex items-center justify-between gap-3">
          <Link
            href="/vehicles"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-400 transition hover:text-cyan-200"
          >
            <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
              <path
                d="M19 12H6M11 6l-6 6 6 6"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            К списку машин
          </Link>
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className={`${secondaryButtonClass} px-3 py-2 text-[0.8rem]`}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`}
              aria-hidden="true"
            >
              <path
                d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            {refreshing ? "Обновляем…" : "Обновить"}
          </button>
        </div>

        {error ? (
          <p role="alert" className="callout callout-danger reveal">
            {error}
          </p>
        ) : null}

        {notFound ? (
          <section className={`${cardClass} reveal p-8 text-center`}>
            <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-amber-300/25 bg-amber-300/[0.08] text-amber-200">
              <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7" aria-hidden="true">
                <path
                  d="M12 8v5m0 3.5v.5M10.3 4.3 3.6 17a2 2 0 0 0 1.8 3h13.2a2 2 0 0 0 1.8-3L13.7 4.3a2 2 0 0 0-3.4 0Z"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <h2 className="mt-4 text-xl font-semibold text-white">Осмотр не найден</h2>
            <p className="mt-2 text-sm text-slate-400">
              Ссылка устарела или осмотр принадлежит другой организации.
            </p>
            <Link href="/vehicles" className={`${secondaryButtonClass} mt-6`}>
              К списку машин
            </Link>
          </section>
        ) : null}

        {detail ? (
          <>
            <section className="hero-panel reveal">
              <div className="relative z-10 p-5 sm:p-7">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-cyan-300/75">
                      Осмотр {inspectionKindLabels[detail.kind]} смены
                    </p>
                    <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
                      {vehicle ? `${vehicle.plate} · ${vehicle.model}` : "Машина"}
                    </h1>
                    <p className="mt-1.5 text-sm text-slate-400">
                      Начат {formatDate(detail.created_at)}
                      {detail.finished_at ? ` · завершён ${formatDate(detail.finished_at)}` : ""}
                    </p>
                  </div>
                  <span
                    className={`pill pill-dot ${statusTone[detail.status]} ${
                      isPending(detail.status) ? "animate-pulse" : ""
                    }`}
                  >
                    {inspectionStatusLabels[detail.status]}
                  </span>
                </div>

                <div className="mt-6 grid grid-cols-3 gap-2.5">
                  <div className="stat-tile">
                    <p className="text-[0.64rem] font-semibold uppercase tracking-[0.14em] text-slate-500">
                      Фото
                    </p>
                    <p className="mt-1 text-xl font-semibold text-white">
                      {detail.photos.length}
                      <span className="text-sm font-normal text-slate-500">
                        {" "}
                        / {PHOTO_SIDES.length}
                      </span>
                    </p>
                  </div>
                  <div className="stat-tile">
                    <p className="text-[0.64rem] font-semibold uppercase tracking-[0.14em] text-slate-500">
                      С замечаниями
                    </p>
                    <p className="mt-1 text-xl font-semibold text-white">{flaggedCount}</p>
                  </div>
                  <div className="stat-tile">
                    <p className="text-[0.64rem] font-semibold uppercase tracking-[0.14em] text-slate-500">
                      Статус
                    </p>
                    <p className="mt-1 text-sm font-semibold text-white">
                      {inspectionStatusLabels[detail.status]}
                    </p>
                  </div>
                </div>
              </div>
            </section>

            {isPending(detail.status) ? (
              <div className="callout callout-info reveal flex flex-wrap items-center gap-3">
                <span className="loader-ring h-5 w-5 border" aria-hidden="true" />
                <div className="min-w-0">
                  <p className="font-medium text-cyan-100">Осмотр обрабатывается</p>
                  <p className="mt-0.5 text-[0.8rem] opacity-80">
                    {pollingStopped
                      ? "Автообновление остановлено. Нажмите «Обновить», чтобы проверить статус."
                      : "Статус обновляется автоматически каждые 5 секунд."}
                  </p>
                </div>
              </div>
            ) : null}

            {detail.status === "failed" ? (
              <div role="alert" className="callout callout-danger reveal">
                <p className="font-medium">Обработка не удалась.</p>
                {detail.failure_reason ? <p className="mt-1">{detail.failure_reason}</p> : null}
              </div>
            ) : null}

            <div className="grid gap-4 lg:grid-cols-[1.45fr_minmax(0,0.75fr)]">
              <section className={`${cardClass} reveal overflow-hidden`}>
                <div className="flex items-start justify-between gap-3 border-b border-white/[0.06] px-5 py-4">
                  <div>
                    <h2 className="text-base font-semibold text-white">Фото осмотра</h2>
                    <p className="mt-0.5 text-xs text-slate-500">
                      Ссылки временные — обновление страницы их продлевает
                    </p>
                  </div>
                  <span className="pill tone-slate">{detail.photos.length} / 4</span>
                </div>

                <div className="grid gap-4 p-4 sm:grid-cols-2 sm:p-5">
                  {PHOTO_SIDES.map((side) => {
                    const photo = photos.get(side);
                    const flags = photo?.quality_flags ?? [];

                    return (
                      <figure key={side}>
                        <div className="photo-tile aspect-[4/3]">
                          {photo ? (
                            <div
                              role="img"
                              aria-label={`Фото машины: ${sideLabels[side].toLowerCase()}`}
                              className="photo-image absolute inset-0 bg-cover bg-center"
                              style={{ backgroundImage: `url(${photo.url})` }}
                            />
                          ) : (
                            <span className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 text-xs text-slate-600">
                              <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                className="h-6 w-6"
                                aria-hidden="true"
                              >
                                <path
                                  d="M4 8.5A2.5 2.5 0 0 1 6.5 6h2L10 4h4l1.5 2h2A2.5 2.5 0 0 1 20 8.5v8A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-8Z"
                                  stroke="currentColor"
                                  strokeWidth="1.5"
                                  strokeLinejoin="round"
                                />
                                <circle
                                  cx="12"
                                  cy="12.5"
                                  r="3.2"
                                  stroke="currentColor"
                                  strokeWidth="1.5"
                                />
                              </svg>
                              Нет фото
                            </span>
                          )}

                          <span className="absolute left-3 top-3 z-10 inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-[#05070f]/70 px-2 py-1 text-[0.65rem] font-semibold uppercase tracking-[0.12em] text-slate-200 backdrop-blur">
                            {sideLabels[side]}
                          </span>

                          {flags.length > 0 ? (
                            <span className="pill tone-amber absolute right-3 top-3 z-10">
                              замечание
                            </span>
                          ) : null}
                        </div>
                        <figcaption className="mt-2 px-0.5">
                          {flags.length > 0 ? (
                            <p className="text-[0.72rem] leading-snug text-amber-200/90">
                              {flags.map(qualityFlagLabel).join(", ")}
                            </p>
                          ) : (
                            <p className="text-[0.72rem] text-slate-500">
                              {photo ? "Качество в порядке" : "Сторона не снята"}
                            </p>
                          )}
                        </figcaption>
                      </figure>
                    );
                  })}
                </div>
              </section>

              <section className={`${cardClass} reveal p-5`} style={{ animationDelay: "80ms" }}>
                <h2 className="text-base font-semibold text-white">Ход осмотра</h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  Каждый этап фиксируется автоматически
                </p>

                <ol className="timeline mt-5">
                  {timeline.map((step) => (
                    <li key={step.title} className="timeline-item" data-state={step.state}>
                      <span className="timeline-dot" aria-hidden="true">
                        {step.state === "done" ? (
                          <svg viewBox="0 0 24 24" fill="none" className="h-3 w-3">
                            <path
                              d="m5 12.5 4.2 4.2L19 6.8"
                              stroke="currentColor"
                              strokeWidth="2.6"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        ) : step.state === "error" ? (
                          "!"
                        ) : (
                          "•"
                        )}
                      </span>
                      <span>
                        <span className="block text-sm font-medium text-slate-200">
                          {step.title}
                        </span>
                        <span className="mt-0.5 block text-[0.72rem] leading-snug text-slate-500">
                          {step.text}
                        </span>
                      </span>
                    </li>
                  ))}
                </ol>

                <div className="mt-6 border-t border-white/[0.06] pt-4">
                  <Link
                    href="/inspections/new"
                    className={`${primaryButtonClass} w-full`}
                  >
                    Новый осмотр
                  </Link>
                  <Link href="/vehicles" className={`${secondaryButtonClass} mt-2 w-full`}>
                    Все машины
                  </Link>
                </div>
              </section>
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}
