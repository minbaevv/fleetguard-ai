"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";

import { AppHeader } from "@/components/AppHeader";
import { LoadingScreen } from "@/components/LoadingScreen";
import { ApiError, apiFetch, apiUpload, errorMessage } from "@/lib/api";
import {
  PHOTO_SIDES,
  inspectionStatusLabels,
  qualityFlagLabel,
  sideHints,
  sideLabels,
} from "@/lib/labels";
import { preparePhoto } from "@/lib/photos";
import { cardClass, inputClass, primaryButtonClass, secondaryButtonClass } from "@/lib/styles";
import type {
  AuthResponse,
  InspectionCreated,
  InspectionDetail,
  InspectionStatus,
  InspectionStatusUpdate,
  PhotoQuality,
  PhotoSide,
  UploadedPhoto,
  Vehicle,
} from "@/lib/types";

interface CaptureWizardProps {
  initialVehicleId: string | null;
}

interface CapturedPhoto {
  previewUrl: string;
  quality: PhotoQuality;
}

type CapturedPhotos = Partial<Record<PhotoSide, CapturedPhoto>>;

const draftStorageKey = (vehicleId: string) => `fleetguard:inspection:${vehicleId}`;

function firstMissingSide(photos: CapturedPhotos): PhotoSide {
  return PHOTO_SIDES.find((side) => !photos[side]) ?? PHOTO_SIDES[0];
}

function toCapturedPhotos(detail: InspectionDetail): CapturedPhotos {
  const restored: CapturedPhotos = {};
  for (const photo of detail.photos) {
    restored[photo.side] = {
      previewUrl: photo.url,
      quality: {
        ok: (photo.quality_flags?.length ?? 0) === 0,
        flags: photo.quality_flags ?? [],
        score: photo.quality_score ?? 0,
      },
    };
  }
  return restored;
}

function statusTone(status: InspectionStatus): string {
  if (status === "done") return "tone-emerald";
  if (status === "failed") return "tone-red";
  return "tone-amber";
}

const steps = [
  { number: "01", title: "Выберите машину", text: "Из парка организации" },
  { number: "02", title: "Снимите 4 стороны", text: "Спереди, сзади и борта" },
  { number: "03", title: "Проверьте качество", text: "Кадры проверяются сразу" },
];

export function CaptureWizard({ initialVehicleId }: CaptureWizardProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [auth, setAuth] = useState<AuthResponse | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [vehicleId, setVehicleId] = useState(initialVehicleId ?? "");
  const [inspectionId, setInspectionId] = useState<string | null>(null);
  const [status, setStatus] = useState<InspectionStatus | null>(null);
  const [photos, setPhotos] = useState<CapturedPhotos>({});
  const [activeSide, setActiveSide] = useState<PhotoSide>(PHOTO_SIDES[0]);

  const [loading, setLoading] = useState(true);
  const [resuming, setResuming] = useState(false);
  const [starting, setStarting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const fetchDraft = useCallback(
    async (currentVehicleId: string, draftId: string): Promise<InspectionDetail | null> => {
      try {
        return await apiFetch<InspectionDetail>(`/api/v1/inspections/${draftId}`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          window.sessionStorage.removeItem(draftStorageKey(currentVehicleId));
          return null;
        }
        throw err;
      }
    },
    [],
  );

  const applyDraft = useCallback((detail: InspectionDetail) => {
    setInspectionId(detail.id);
    setStatus(detail.status);
    if (detail.status === "draft") {
      const restored = toCapturedPhotos(detail);
      setPhotos(restored);
      setActiveSide(firstMissingSide(restored));
    } else {
      window.sessionStorage.removeItem(draftStorageKey(detail.vehicle_id));
      setPhotos({});
    }
  }, []);

  useEffect(() => {
    let active = true;

    void (async () => {
      try {
        const me = await apiFetch<AuthResponse>("/api/v1/auth/me");
        const list = await apiFetch<Vehicle[]>("/api/v1/vehicles");
        if (!active) return;
        setAuth(me);
        setVehicles(list);

        if (!initialVehicleId) return;
        const draftId = window.sessionStorage.getItem(draftStorageKey(initialVehicleId));
        if (!draftId) return;
        const detail = await fetchDraft(initialVehicleId, draftId);
        if (active && detail) applyDraft(detail);
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
  }, [applyDraft, fetchDraft, initialVehicleId, redirectIfUnauthorized]);

  async function onSelectVehicle(nextVehicleId: string) {
    setVehicleId(nextVehicleId);
    setInspectionId(null);
    setStatus(null);
    setPhotos({});
    setActiveSide(PHOTO_SIDES[0]);
    setError(null);
    if (!nextVehicleId) return;

    const draftId = window.sessionStorage.getItem(draftStorageKey(nextVehicleId));
    if (!draftId) return;

    setResuming(true);
    try {
      const detail = await fetchDraft(nextVehicleId, draftId);
      if (detail) applyDraft(detail);
    } catch (err) {
      if (!redirectIfUnauthorized(err)) setError(errorMessage(err));
    } finally {
      setResuming(false);
    }
  }

  async function onStart() {
    if (!vehicleId) {
      setError("Выберите машину.");
      return;
    }

    setStarting(true);
    setError(null);
    try {
      const created = await apiFetch<InspectionCreated>("/api/v1/inspections", {
        method: "POST",
        body: JSON.stringify({ vehicle_id: vehicleId, kind: "before" }),
      });
      window.sessionStorage.setItem(draftStorageKey(vehicleId), created.id);
      setInspectionId(created.id);
      setStatus(created.status);
      setPhotos({});
      setActiveSide(PHOTO_SIDES[0]);
    } catch (err) {
      if (!redirectIfUnauthorized(err)) setError(errorMessage(err));
    } finally {
      setStarting(false);
    }
  }

  async function onPick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !inspectionId) return;

    const side = activeSide;
    setUploading(true);
    setError(null);
    try {
      const prepared = await preparePhoto(file);
      const form = new FormData();
      form.append("file", prepared.blob, "photo.jpg");
      const uploaded = await apiUpload<UploadedPhoto>(
        `/api/v1/inspections/${inspectionId}/photos?side=${side}`,
        form,
      );
      setPhotos((current) => ({
        ...current,
        [side]: { previewUrl: prepared.previewUrl, quality: uploaded.quality },
      }));
    } catch (err) {
      if (!redirectIfUnauthorized(err)) setError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function onFinish() {
    if (!inspectionId || !vehicleId) return;

    setFinishing(true);
    setError(null);
    try {
      const finished = await apiFetch<InspectionStatusUpdate>(
        `/api/v1/inspections/${inspectionId}/finish`,
        { method: "POST" },
      );
      window.sessionStorage.removeItem(draftStorageKey(vehicleId));
      setStatus(finished.status);
    } catch (err) {
      if (!redirectIfUnauthorized(err)) setError(errorMessage(err));
    } finally {
      setFinishing(false);
    }
  }

  function onRestart() {
    setInspectionId(null);
    setStatus(null);
    setPhotos({});
    setActiveSide(PHOTO_SIDES[0]);
    setError(null);
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
    return <LoadingScreen label="Готовим мастер съёмки…" />;
  }

  if (!auth) {
    return null;
  }

  const selectedVehicle = vehicles.find((vehicle) => vehicle.id === vehicleId) ?? null;

  if (inspectionId && status && status !== "draft") {
    return (
      <div className="min-h-screen pb-16">
        <AppHeader
          auth={auth}
          onLogout={onLogout}
          loggingOut={loggingOut}
          title="Осмотр машины"
        />
        <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
          <section className={`${cardClass} reveal overflow-hidden p-6 text-center sm:p-10`}>
            <span className="success-ring" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" className="h-9 w-9">
                <path
                  d="m5 12.5 4.2 4.2L19 6.8"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>

            <p className="mt-6 text-[0.66rem] font-semibold uppercase tracking-[0.22em] text-emerald-300/80">
              Осмотр до смены
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">
              Фото загружены, осмотр отправлен
            </h2>
            <p className="mt-2 text-sm text-slate-400">
              Все 4 стороны сняты. Дальше система обработает кадры и подготовит акт.
            </p>

            <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
              <span className={`pill pill-dot ${statusTone(status)}`}>
                {inspectionStatusLabels[status]}
              </span>
              {selectedVehicle ? (
                <span className="plate-badge">
                  {selectedVehicle.plate} · {selectedVehicle.model}
                </span>
              ) : null}
            </div>

            <div className="mt-8 flex flex-col justify-center gap-2 sm:flex-row">
              <Link href={`/inspections/${inspectionId}`} className={primaryButtonClass}>
                Открыть осмотр
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
              <Link href="/vehicles" className={secondaryButtonClass}>
                К списку машин
              </Link>
              <button type="button" onClick={onRestart} className={secondaryButtonClass}>
                Новый осмотр
              </button>
            </div>
          </section>
        </main>
      </div>
    );
  }

  if (!inspectionId) {
    return (
      <div className="min-h-screen pb-16">
        <AppHeader
          auth={auth}
          onLogout={onLogout}
          loggingOut={loggingOut}
          title="Осмотр машины"
        />
        <main className="mx-auto max-w-4xl space-y-5 px-4 py-6 sm:px-6">
          {error ? (
            <p role="alert" className="callout callout-danger reveal">
              {error}
            </p>
          ) : null}

          <section className="hero-panel reveal">
            <div className="relative z-10 grid gap-6 p-6 sm:p-8 lg:grid-cols-[1fr_320px] lg:items-end">
              <div>
                <span className="eyebrow">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-300" />
                  Новый осмотр
                </span>
                <h1 className="mt-4 text-3xl font-semibold leading-[1.08] tracking-[-0.025em] text-white sm:text-4xl">
                  <span className="block">Снимок «до»</span>
                  <span className="text-gradient">за пару минут</span>
                </h1>
                <p className="mt-3 max-w-lg text-sm leading-relaxed text-slate-400">
                  Четыре стороны, проверка качества каждого кадра и сохранение в историю
                  организации. Начните с выбора машины.
                </p>

                <div className="mt-6 hidden gap-2 sm:grid sm:grid-cols-3">
                  {steps.map((step) => (
                    <div key={step.number} className="stat-tile">
                      <p className="text-[0.62rem] font-semibold tracking-[0.18em] text-cyan-300/70">
                        {step.number}
                      </p>
                      <p className="mt-1.5 text-[0.8rem] font-semibold text-slate-100">
                        {step.title}
                      </p>
                      <p className="mt-0.5 text-[0.7rem] leading-snug text-slate-500">
                        {step.text}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel-soft w-full p-4">
                <label htmlFor="vehicle-select" className="field-label">
                  Машина
                </label>
                <select
                  id="vehicle-select"
                  value={vehicleId}
                  onChange={(event) => void onSelectVehicle(event.target.value)}
                  disabled={starting || resuming}
                  className={inputClass}
                >
                  <option value="">Выберите машину</option>
                  {vehicles.map((vehicle) => (
                    <option key={vehicle.id} value={vehicle.id}>
                      {vehicle.plate} · {vehicle.model}
                    </option>
                  ))}
                </select>

                {selectedVehicle ? (
                  <p className="mt-2.5 text-[0.72rem] text-slate-500">
                    {selectedVehicle.model}
                    {selectedVehicle.year ? ` · ${selectedVehicle.year}` : ""}
                  </p>
                ) : null}

                {resuming ? (
                  <p role="status" className="mt-2.5 text-xs text-cyan-200">
                    Загружаем черновик осмотра…
                  </p>
                ) : null}

                <button
                  type="button"
                  onClick={() => void onStart()}
                  disabled={!vehicleId || starting || resuming}
                  className={`${primaryButtonClass} mt-4 w-full`}
                >
                  {starting ? "Создаём…" : "Начать осмотр"}
                </button>
                <Link
                  href="/vehicles"
                  className={`${secondaryButtonClass} mt-2 w-full`}
                >
                  Отмена
                </Link>

                <p className="mt-3 text-center text-[0.68rem] leading-relaxed text-slate-600">
                  Ссылки на фото подписанные и временные
                </p>
              </div>
            </div>
          </section>

          {vehicles.length === 0 ? (
            <section className={`${cardClass} reveal p-5 sm:p-6`}>
              <p className="callout callout-warning">
                В организации пока нет машин.{" "}
                <Link href="/vehicles" className="font-semibold underline underline-offset-2">
                  Добавьте машину
                </Link>
                , чтобы начать осмотр.
              </p>
            </section>
          ) : null}
        </main>
      </div>
    );
  }

  const photo = photos[activeSide];
  const sideIndex = PHOTO_SIDES.indexOf(activeSide);
  const previousSide = sideIndex > 0 ? PHOTO_SIDES[sideIndex - 1] : null;
  const nextSide = sideIndex < PHOTO_SIDES.length - 1 ? PHOTO_SIDES[sideIndex + 1] : null;
  const capturedCount = PHOTO_SIDES.filter((side) => photos[side]).length;
  const retakesCount = PHOTO_SIDES.filter((side) => {
    const quality = photos[side]?.quality;
    return quality ? !quality.ok : false;
  }).length;
  const canFinish = capturedCount === PHOTO_SIDES.length && !uploading && !finishing;

  const renderSideChip = (side: PhotoSide) => {
    const quality = photos[side]?.quality;
    const current = side === activeSide;
    return (
      <button
        key={side}
        type="button"
        onClick={() => setActiveSide(side)}
        disabled={uploading || finishing}
        aria-current={current ? "step" : undefined}
        data-quality={quality ? (quality.ok ? "ok" : "warn") : undefined}
        className="side-chip"
      >
        <span className="block text-[0.78rem]">{sideLabels[side]}</span>
        <span className="mt-0.5 flex items-center justify-center gap-1 text-[0.63rem] font-normal opacity-80">
          {quality ? (
            <>
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 rounded-full ${
                  quality.ok ? "bg-emerald-300" : "bg-amber-300"
                }`}
              />
              {quality.ok ? "готово" : "переснять"}
            </>
          ) : (
            "нет фото"
          )}
        </span>
      </button>
    );
  };

  return (
    <div className="min-h-screen pb-16">
      <AppHeader auth={auth} onLogout={onLogout} loggingOut={loggingOut} title="Осмотр машины" />

      <main className="mx-auto max-w-5xl space-y-4 px-4 py-6 sm:px-6">
        {error ? (
          <p role="alert" className="callout callout-danger reveal">
            {error}
          </p>
        ) : null}

        <section className={`${cardClass} reveal overflow-hidden`}>
          <div className="border-b border-white/[0.06] p-5 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[0.66rem] font-semibold uppercase tracking-[0.2em] text-cyan-300/75">
                  Шаг {sideIndex + 1} из {PHOTO_SIDES.length}
                  {selectedVehicle ? ` · ${selectedVehicle.plate}` : ""}
                </p>
                <h2 className="mt-1.5 text-2xl font-semibold tracking-tight text-white">
                  {sideLabels[activeSide]}
                </h2>
                <p className="mt-1 max-w-lg text-sm leading-relaxed text-slate-400">
                  {sideHints[activeSide]}
                </p>
              </div>
              <Link href="/vehicles" className={`${secondaryButtonClass} shrink-0`}>
                К машинам
              </Link>
            </div>

            <div className="stepper mt-5">
              {PHOTO_SIDES.map((side) => {
                const captured = Boolean(photos[side]);
                const state = side === activeSide ? "active" : captured ? "done" : "todo";
                return (
                  <div key={side} className="stepper-step" data-state={state}>
                    <span className="stepper-dot" aria-hidden="true">
                      {captured && side !== activeSide ? (
                        <svg viewBox="0 0 24 24" fill="none" className="h-3 w-3">
                          <path
                            d="m5 12.5 4.2 4.2L19 6.8"
                            stroke="currentColor"
                            strokeWidth="2.4"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      ) : (
                        PHOTO_SIDES.indexOf(side) + 1
                      )}
                    </span>
                    <span className="min-w-0">{sideLabels[side]}</span>
                  </div>
                );
              })}
            </div>

            <div className="progress mt-4">
              <span style={{ width: `${(capturedCount / PHOTO_SIDES.length) * 100}%` }} />
            </div>
          </div>

          <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(250px,0.75fr)]">
            <div className="space-y-3">
              <nav aria-label="Стороны осмотра" className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:hidden">
                {PHOTO_SIDES.map(renderSideChip)}
              </nav>

              <div className="relative aspect-[4/3] overflow-hidden rounded-2xl border border-white/10 bg-[#04070f]">
                {photo ? (
                  <div
                    role="img"
                    aria-label={`Фото машины: ${sideLabels[activeSide].toLowerCase()}`}
                    className="photo-image absolute inset-0 bg-cover bg-center"
                    style={{ backgroundImage: `url(${photo.previewUrl})` }}
                  />
                ) : (
                  <div className="absolute inset-0 flex flex-col items-center justify-center px-8 text-center">
                    <span className="grid h-14 w-14 place-items-center rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.06] text-cyan-200">
                      <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7" aria-hidden="true">
                        <path
                          d="M4 8.5A2.5 2.5 0 0 1 6.5 6h2L10 4h4l1.5 2h2A2.5 2.5 0 0 1 20 8.5v8A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-8Z"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinejoin="round"
                        />
                        <circle cx="12" cy="12.5" r="3.2" stroke="currentColor" strokeWidth="1.5" />
                      </svg>
                    </span>
                    <p className="mt-4 text-sm font-medium text-slate-200">
                      Впишите машину в рамку целиком
                    </p>
                    <p className="mt-1 max-w-xs text-xs leading-relaxed text-slate-500">
                      Свет должен падать на кузов, а не в камеру. Держите телефон ровно.
                    </p>
                  </div>
                )}

                <span className="pointer-events-none absolute left-3 top-3 h-7 w-7 rounded-tl-lg border-l-2 border-t-2 border-cyan-100/60" />
                <span className="pointer-events-none absolute right-3 top-3 h-7 w-7 rounded-tr-lg border-r-2 border-t-2 border-cyan-100/60" />
                <span className="pointer-events-none absolute bottom-3 left-3 h-7 w-7 rounded-bl-lg border-b-2 border-l-2 border-cyan-100/60" />
                <span className="pointer-events-none absolute bottom-3 right-3 h-7 w-7 rounded-br-lg border-b-2 border-r-2 border-cyan-100/60" />

                {photo ? (
                  <span
                    className={`pill absolute bottom-3 left-1/2 -translate-x-1/2 ${
                      photo.quality.ok ? "tone-emerald" : "tone-amber"
                    }`}
                  >
                    {photo.quality.ok ? "Качество в порядке" : "Есть замечания"}
                  </span>
                ) : null}

                {uploading ? (
                  <div
                    role="status"
                    className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[#04070f]/70 text-sm font-medium text-white backdrop-blur-[2px]"
                  >
                    <span className="loader-ring" aria-hidden="true" />
                    Проверяем кадр…
                    <span className="scan-line" aria-hidden="true" />
                  </div>
                ) : null}
              </div>

              {photo ? (
                photo.quality.ok ? (
                  <div role="status" className="callout callout-success">
                    <span className="flex items-center gap-2 font-medium">
                      <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
                        <path
                          d="m5 12.5 4.2 4.2L19 6.8"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      Кадр принят
                    </span>
                    <p className="mt-1 opacity-85">Переходите к следующей стороне.</p>
                  </div>
                ) : (
                  <div role="alert" className="callout callout-warning">
                    <p className="font-medium">Фото может не подойти:</p>
                    <ul className="mt-1 list-inside list-disc space-y-0.5 opacity-90">
                      {photo.quality.flags.map((flag) => (
                        <li key={flag}>{qualityFlagLabel(flag)}</li>
                      ))}
                    </ul>
                    <p className="mt-1.5 opacity-80">
                      Переснимите при ровном свете и с более близкого расстояния.
                    </p>
                  </div>
                )
              ) : null}
            </div>

            <div className="space-y-3">
              <nav
                aria-label="Стороны осмотра"
                className="hidden grid-cols-2 gap-2 lg:grid"
              >
                {PHOTO_SIDES.map(renderSideChip)}
              </nav>

              <div className="panel-soft p-4">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-[0.66rem] font-semibold uppercase tracking-[0.16em] text-slate-500">
                    Прогресс
                  </p>
                  <p className="text-sm font-semibold text-white">
                    {capturedCount} / {PHOTO_SIDES.length}
                  </p>
                </div>
                <div className="mt-2 flex gap-1.5">
                  {PHOTO_SIDES.map((side) => (
                    <span
                      key={side}
                      className={`h-1.5 flex-1 rounded-full ${
                        photos[side]
                          ? photos[side]?.quality.ok
                            ? "bg-emerald-400/80"
                            : "bg-amber-400/80"
                          : "bg-white/10"
                      }`}
                    />
                  ))}
                </div>
                <p className="mt-2.5 text-[0.72rem] leading-relaxed text-slate-500">
                  {retakesCount > 0
                    ? `С замечаниями: ${retakesCount}. Лучше переснять до завершения.`
                    : capturedCount === PHOTO_SIDES.length
                      ? "Все стороны сняты. Можно завершать осмотр."
                      : `Осталось сторон: ${PHOTO_SIDES.length - capturedCount}.`}
                </p>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={onPick}
              />

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading || finishing}
                className={`${primaryButtonClass} w-full`}
              >
                <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
                  <path
                    d="M4 8.5A2.5 2.5 0 0 1 6.5 6h2L10 4h4l1.5 2h2A2.5 2.5 0 0 1 20 8.5v8A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-8Z"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                  />
                  <circle cx="12" cy="12.5" r="3.2" stroke="currentColor" strokeWidth="1.5" />
                </svg>
                {uploading ? "Проверяем…" : photo ? "Переснять" : "Сделать фото"}
              </button>

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => previousSide && setActiveSide(previousSide)}
                  disabled={!previousSide || uploading || finishing}
                  className={secondaryButtonClass}
                >
                  ← Назад
                </button>
                <button
                  type="button"
                  onClick={() => nextSide && setActiveSide(nextSide)}
                  disabled={!nextSide || !photo || uploading || finishing}
                  className={secondaryButtonClass}
                >
                  Дальше →
                </button>
              </div>

              <button
                type="button"
                onClick={() => void onFinish()}
                disabled={!canFinish}
                className={`${primaryButtonClass} w-full`}
              >
                {finishing ? "Отправляем…" : "Завершить осмотр"}
              </button>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
