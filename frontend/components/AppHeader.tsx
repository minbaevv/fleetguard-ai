import { roleLabels } from "@/lib/labels";
import { secondaryButtonClass } from "@/lib/styles";
import type { AuthResponse } from "@/lib/types";

interface AppHeaderProps {
  auth: AuthResponse;
  onLogout: () => void;
  loggingOut: boolean;
}

export function AppHeader({ auth, onLogout, loggingOut }: AppHeaderProps) {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
            FleetGuard AI
          </p>
          <h1 className="text-xl font-semibold text-slate-900">Машины</h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-sm font-medium text-slate-900">{auth.user.name}</p>
            <p className="text-xs text-slate-500">
              {roleLabels[auth.user.role]} · {auth.organization.name}
            </p>
          </div>
          <button
            type="button"
            onClick={onLogout}
            disabled={loggingOut}
            className={secondaryButtonClass}
          >
            {loggingOut ? "Выходим…" : "Выйти"}
          </button>
        </div>
      </div>
    </header>
  );
}
