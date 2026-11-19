import Link from "next/link";

import { Logo } from "@/components/Logo";
import { roleLabels } from "@/lib/labels";
import { secondaryButtonClass } from "@/lib/styles";
import type { AuthResponse } from "@/lib/types";

interface AppHeaderProps {
  auth: AuthResponse;
  onLogout: () => void;
  loggingOut: boolean;
  title?: string;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function AppHeader({ auth, onLogout, loggingOut, title = "Машины" }: AppHeaderProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#05070f]/72 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 sm:px-6">
        <Link
          href="/vehicles"
          className="group flex items-center gap-3 rounded-xl focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-300"
        >
          <span className="transition-transform duration-300 group-hover:scale-105">
            <Logo withWordmark={false} />
          </span>
          <span className="leading-tight">
            <span className="block text-[9px] font-semibold uppercase tracking-[0.26em] text-cyan-300/75">
              FleetGuard AI
            </span>
            <span className="block text-[0.95rem] font-semibold text-white">{title}</span>
          </span>
        </Link>

        <nav aria-label="Основная навигация" className="hidden items-center gap-1 sm:flex sm:ml-6">
          <Link
            href="/vehicles"
            className="rounded-lg px-2.5 py-1.5 text-[0.8rem] font-medium text-slate-400 transition hover:bg-white/[0.05] hover:text-white"
          >
            Парк
          </Link>
          <Link
            href="/inspections/new"
            className="rounded-lg px-2.5 py-1.5 text-[0.8rem] font-medium text-slate-400 transition hover:bg-white/[0.05] hover:text-white"
          >
            Новый осмотр
          </Link>
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <div className="hidden text-right sm:block">
            <p className="text-[0.8rem] font-semibold leading-tight text-white">{auth.user.name}</p>
            <p className="mt-0.5 text-[0.68rem] leading-tight text-slate-500">
              {roleLabels[auth.user.role]} · {auth.organization.name}
            </p>
          </div>

          <span
            aria-hidden="true"
            className="grid h-9 w-9 flex-none place-items-center rounded-full border border-cyan-300/25 bg-gradient-to-br from-indigo-500/30 to-cyan-400/20 text-[0.7rem] font-semibold text-cyan-100 shadow-[0_0_0_4px_rgba(34,211,238,0.06)] sm:hidden"
          >
            {initials(auth.user.name)}
          </span>

          <button
            type="button"
            onClick={onLogout}
            disabled={loggingOut}
            className={`${secondaryButtonClass} px-2.5 py-2 text-[0.78rem] sm:px-3`}
          >
            <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
              <path
                d="M15 17l5-5-5-5M20 12H9M12 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h6"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="hidden sm:inline">{loggingOut ? "Выходим…" : "Выйти"}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
