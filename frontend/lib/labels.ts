import type { UserRole } from "@/lib/types";

export const roleLabels: Record<UserRole, string> = {
  admin: "Администратор",
  manager: "Менеджер",
  driver: "Водитель",
};
