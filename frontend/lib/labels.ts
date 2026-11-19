import type { InspectionKind, InspectionStatus, PhotoSide, UserRole } from "@/lib/types";

export const roleLabels: Record<UserRole, string> = {
  admin: "Администратор",
  manager: "Менеджер",
  driver: "Водитель",
};

export const PHOTO_SIDES: readonly PhotoSide[] = ["front", "back", "left", "right"];

export const sideLabels: Record<PhotoSide, string> = {
  front: "Спереди",
  back: "Сзади",
  left: "Слева",
  right: "Справа",
};

export const sideHints: Record<PhotoSide, string> = {
  front: "Встаньте перед машиной: в кадре бампер, фары и номер целиком.",
  back: "Сфотографируйте заднюю часть: бампер и фонари целиком.",
  left: "Обойдите машину слева: в кадре оба колеса и весь борт.",
  right: "Обойдите машину справа: в кадре оба колеса и весь борт.",
};

export const inspectionStatusLabels: Record<InspectionStatus, string> = {
  draft: "черновик",
  uploading: "загрузка фото",
  processing: "обработка",
  done: "готово",
  failed: "ошибка обработки",
};

export const inspectionKindLabels: Record<InspectionKind, string> = {
  before: "до",
  after: "после",
};

export const qualityFlagLabels: Record<string, string> = {
  blurry: "Фото размытое",
  too_dark: "Слишком темно",
  too_bright: "Слишком светло",
  low_resolution: "Низкое разрешение",
};

export function qualityFlagLabel(flag: string): string {
  return qualityFlagLabels[flag] ?? flag;
}
