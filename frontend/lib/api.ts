import type { ApiErrorBody } from "@/lib/types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }

  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const errorBody = body as ApiErrorBody | null;
    throw new ApiError(
      response.status,
      errorBody?.error.code ?? "unknown_error",
      errorBody?.error.message ?? "Не удалось выполнить запрос",
    );
  }

  return body as T;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers,
  });
  return readResponse<T>(response);
}

export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  // Content-Type для multipart выставляет браузер: вместе с boundary вручную его не собрать.
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });
  return readResponse<T>(response);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Неизвестная ошибка";
}
