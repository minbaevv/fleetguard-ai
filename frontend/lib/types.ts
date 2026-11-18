export type UserRole = "admin" | "manager" | "driver";

export interface User {
  id: string;
  org_id: string;
  email: string;
  name: string;
  role: UserRole;
}

export interface Organization {
  id: string;
  name: string;
}

export interface AuthResponse {
  user: User;
  organization: Organization;
}

export interface Vehicle {
  id: string;
  org_id: string;
  plate: string;
  model: string;
  year: number | null;
  created_at: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}
