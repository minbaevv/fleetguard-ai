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
    return (
      <main className="flex min-h-screen items-center justify-center text-slate-500" role="status">
        Загрузка…
      </main>
    );
  }

  if (!auth) {
    return null;
  }

  const selectedVehicle = vehicles.find((vehicle) => vehicle.id === vehicleId) ?? null;

  if (inspectionId && status && status !== "draft") {
    return (
      <div className="min-h-screen">
        <AppHeader
          auth={auth}
          onLogout={onLogout}
          loggingOut={loggingOut}
          title="Осмотр машины"
        />
        <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
          <section className={`${cardClass} p-6 text-center sm:p-8`}>
            <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
              Готово
            </p>
            <h2 className="mt-2 text-xl font-semibold text-slate-900">
              Осмотр отправлен на обработку
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              Все 4 фото загружены. Статус: {inspectionStatusLabels[status]}.
            </p>
            {selectedVehicle ? (
              <p className="mt-1 text-sm text-slate-500">
                Машина {selectedVehicle.plate} · {selectedVehicle.model}
              </p>
            ) : null}
            <p className="mt-4 break-all text-xs text-slate-400">Номер осмотра: {inspectionId}</p>
            <div className="mt-6 flex flex-col justify-center gap-2 sm:flex-row">
              <Link href="/vehicles" className={primaryButtonClass}>
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
      <div className="min-h-screen">
        <AppHeader
          auth={auth}
          onLogout={onLogout}
          loggingOut={loggingOut}
          title="Осмотр машины"
        />
        <main className="mx-auto max-w-3xl space-y-4 px-4 py-6 sm:px-6">
          {error ? (
            <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </p>
          ) : null}

          <section className={`${cardClass} p-4 sm:p-6`}>
            <h2 className="text-lg font-semibold text-slate-900">Новый осмотр «до»</h2>
            <p className="mt-2 text-sm text-slate-600">
              Снимем машину с четырёх сторон. Каждое фото проверяется сразу: если кадр размыт
              или тёмный, мастер попросит переснять.
            </p>

            <div className="mt-5 space-y-1">
              <label htmlFor="vehicle-select" className="block text-sm font-medium text-slate-700">
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
            </div>

            {vehicles.length === 0 ? (
              <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
                В организации пока нет машин.{" "}
                <Link href="/vehicles" className="font-medium underline">
                  Добавьте машину
                </Link>
                , чтобы начать осмотр.
              </p>
            ) : null}

            {resuming ? (
              <p role="status" className="mt-4 text-sm text-slate-500">
                Загружаем черновик осмотра…
              </p>
            ) : null}

            <div className="mt-6 flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                onClick={() => void onStart()}
                disabled={!vehicleId || starting || resuming}
                className={`${primaryButtonClass} w-full sm:w-auto`}
              >
                {starting ? "Создаём…" : "Начать осмотр"}
              </button>
              <Link href="/vehicles" className={`${secondaryButtonClass} w-full sm:w-auto`}>
                Отмена
              </Link>
            </div>
          </section>
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

  return (
    <div className="min-h-screen">
      <AppHeader auth={auth} onLogout={onLogout} loggingOut={loggingOut} title="Осмотр машины" />

      <main className="mx-auto max-w-3xl space-y-4 px-4 py-6 sm:px-6">
        {error ? (
          <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        <section className={`${cardClass} p-4 sm:p-6`}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
                Шаг {sideIndex + 1} из {PHOTO_SIDES.length}
                {selectedVehicle ? ` · ${selectedVehicle.plate}` : ""}
              </p>
              <h2 className="mt-1 text-xl font-semibold text-slate-900">
                {sideLabels[activeSide]}
              </h2>
              <p className="mt-1 text-sm text-slate-600">{sideHints[activeSide]}</p>
            </div>
            <Link href="/vehicles" className={`${secondaryButtonClass} shrink-0`}>
              К машинам
            </Link>
          </div>

          <nav aria-label="Стороны осмотра" className="mt-4 grid grid-cols-4 gap-2">
            {PHOTO_SIDES.map((side) => {
              const quality = photos[side]?.quality;
              const current = side === activeSide;
              const className = current
                ? "border-indigo-600 bg-indigo-50 text-indigo-700"
                : !quality
                  ? "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  : quality.ok
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "border-amber-300 bg-amber-50 text-amber-800";
              return (
                <button
                  key={side}
                  type="button"
                  onClick={() => setActiveSide(side)}
                  disabled={uploading || finishing}
                  aria-current={current ? "step" : undefined}
                  className={`rounded-xl border px-2 py-2 text-xs font-semibold transition disabled:cursor-not-allowed ${className}`}
                >
                  <span className="block">{sideLabels[side]}</span>
                  <span className="block text-[11px] font-normal">
                    {!quality ? "нет фото" : quality.ok ? "готово" : "переснять"}
                  </span>
                </button>
              );
            })}
          </nav>

          <div className="relative mt-4 aspect-[4/3] overflow-hidden rounded-2xl bg-slate-900">
            {photo ? (
              <div
                role="img"
                aria-label={`Фото машины: ${sideLabels[activeSide].toLowerCase()}`}
                className="absolute inset-0 bg-cover bg-center"
                style={{ backgroundImage: `url(${photo.previewUrl})` }}
              />
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center px-8 text-center text-slate-300">
                <p className="text-sm">Впишите машину в рамку целиком</p>
                <p className="mt-1 text-xs text-slate-400">Свет должен падать на кузов, а не в камеру</p>
              </div>
            )}

            <span aria-hidden="true" className="pointer-events-none absolute left-4 top-4 h-8 w-8 rounded-tl-lg border-l-4 border-t-4 border-white/70" />
            <span aria-hidden="true" className="pointer-events-none absolute right-4 top-4 h-8 w-8 rounded-tr-lg border-r-4 border-t-4 border-white/70" />
            <span aria-hidden="true" className="pointer-events-none absolute bottom-4 left-4 h-8 w-8 rounded-bl-lg border-b-4 border-l-4 border-white/70" />
            <span aria-hidden="true" className="pointer-events-none absolute bottom-4 right-4 h-8 w-8 rounded-br-lg border-b-4 border-r-4 border-white/70" />

            {uploading ? (
              <div
                role="status"
                className="absolute inset-0 flex items-center justify-center bg-slate-900/60 text-sm font-medium text-white"
              >
                Проверяем фото…
              </div>
            ) : null}
          </div>

          {photo ? (
            photo.quality.ok ? (
              <p
                role="status"
                className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
              >
                Качество в порядке. Переходите к следующей стороне.
              </p>
            ) : (
              <div role="alert" className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">
                <p className="font-medium">Фото может не подойти:</p>
                <ul className="mt-1 list-inside list-disc">
                  {photo.quality.flags.map((flag) => (
                    <li key={flag}>{qualityFlagLabel(flag)}</li>
                  ))}
                </ul>
                <p className="mt-1">Переснимите при ровном свете и с более близкого расстояния.</p>
              </div>
            )
          ) : null}

          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={onPick}
          />

          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            {previousSide ? (
              <button
                type="button"
                onClick={() => setActiveSide(previousSide)}
                disabled={uploading || finishing}
                className={secondaryButtonClass}
              >
                Назад
              </button>
            ) : (
              <span className="hidden sm:block" />
            )}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || finishing}
              className={primaryButtonClass}
            >
              {uploading ? "Проверяем…" : photo ? "Переснять" : "Сделать фото"}
            </button>
            {nextSide ? (
              <button
                type="button"
                onClick={() => setActiveSide(nextSide)}
                disabled={!photo || uploading || finishing}
                className={secondaryButtonClass}
              >
                Дальше
              </button>
            ) : (
              <span className="hidden sm:block" />
            )}
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
            <div>
              <p className="text-sm text-slate-600">
                Снято {capturedCount} из {PHOTO_SIDES.length} сторон
              </p>
              {retakesCount > 0 ? (
                <p className="text-xs text-amber-800">
                  С замечаниями: {retakesCount}. Лучше переснять.
                </p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => void onFinish()}
              disabled={!canFinish}
              className={`${primaryButtonClass} w-full sm:w-auto`}
            >
              {finishing ? "Отправляем…" : "Завершить осмотр"}
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}
