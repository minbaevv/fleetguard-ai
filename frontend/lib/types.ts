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

export type PhotoSide = "front" | "back" | "left" | "right";
export type InspectionKind = "before" | "after";
export type InspectionStatus = "draft" | "uploading" | "processing" | "done" | "failed";

export interface PhotoQuality {
  ok: boolean;
  flags: string[];
  score: number;
}

export interface UploadedPhoto {
  photo_id: string;
  side: PhotoSide;
  width: number;
  height: number;
  quality: PhotoQuality;
}

export interface InspectionCreated {
  id: string;
  status: InspectionStatus;
  kind: InspectionKind;
  pair_id: string;
  required_sides: PhotoSide[];
}

export interface InspectionStatusUpdate {
  id: string;
  status: InspectionStatus;
}

export interface Damage {
  id: string;
  type: string;
  zone: string | null;
  severity: string | null;
  confidence: number;
  polygon: number[][];
  source: "cv" | "llm";
  is_new: boolean | null;
  llm_note: string | null;
}

export interface InspectionPhoto {
  id: string;
  side: PhotoSide;
  url: string;
  width: number | null;
  height: number | null;
  quality_score: number | null;
  quality_flags: string[] | null;
  damages: Damage[];
}

export interface InspectionDetail {
  id: string;
  vehicle_id: string;
  driver_id: string;
  kind: InspectionKind;
  pair_id: string | null;
  status: InspectionStatus;
  failure_reason: string | null;
  created_at: string;
  finished_at: string | null;
  photos: InspectionPhoto[];
}
