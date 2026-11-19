import type { ReactNode } from "react";

import { Logo } from "@/components/Logo";

interface AuthShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}

const features = [
  {
    title: "4 ракурса за минуту",
    text: "Перед, зад и два борта — съёмка прямо с телефона водителя.",
    icon: (
      <path
        d="M4 8.5A2.5 2.5 0 0 1 6.5 6h2L10 4h4l1.5 2h2A2.5 2.5 0 0 1 20 8.5v8A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5v-8Z M12 15.5a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    ),
  },
  {
    title: "Контроль качества",
    text: "Размытые и тёмные кадры отсекаются сразу, ещё до обработки.",
    icon: (
      <path
        d="m4 13 4.2 4.2L20 6.5"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
  },
  {
    title: "Прозрачная история",
    text: "Акт осмотра, фото и время — всё хранится и доступно менеджеру.",
    icon: (
      <path
        d="M12 7v5l3 2M21 12a9 9 0 1 1-9-9 9 9 0 0 1 9 9Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
  },
];

export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <main className="relative flex min-h-screen items-center justify-center px-4 py-10 sm:px-6 lg:py-16">
      <div className="grid w-full max-w-6xl gap-10 lg:grid-cols-[1.05fr_minmax(0,440px)] lg:items-center lg:gap-14">
        <section className="reveal hidden lg:block">
          <Logo />

          <div className="mt-10">
            <span className="eyebrow">AI-осмотр кузова</span>
          </div>

          <h1 className="mt-5 text-[3.35rem] font-semibold leading-[1.03] tracking-[-0.03em] text-white">
            Каждая царапина
            <br />
            <span className="text-gradient">под контролем.</span>
          </h1>

          <p className="mt-5 max-w-lg text-[0.98rem] leading-relaxed text-slate-400">
            Фотофиксация до и после смены, проверка качества кадров и поиск новых
            повреждений. История, которую нельзя оспорить.
          </p>

          <ul className="mt-8 grid max-w-lg gap-3">
            {features.map((feature) => (
              <li key={feature.title} className="flex items-start gap-3">
                <span className="mt-0.5 grid h-9 w-9 flex-none place-items-center rounded-xl border border-cyan-300/20 bg-cyan-300/[0.07] text-cyan-200">
                  <svg viewBox="0 0 24 24" fill="none" className="h-[18px] w-[18px]">
                    {feature.icon}
                  </svg>
                </span>
                <span>
                  <span className="block text-sm font-semibold text-slate-100">
                    {feature.title}
                  </span>
                  <span className="mt-0.5 block text-[0.82rem] leading-relaxed text-slate-500">
                    {feature.text}
                  </span>
                </span>
              </li>
            ))}
          </ul>

          <div
            className="float-slow mt-10 max-w-md overflow-hidden rounded-2xl border border-white/10 bg-[#070b16]/85 p-4 shadow-[0_40px_90px_-45px_rgba(0,0,0,0.95)]"
            aria-hidden="true"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-300 opacity-70" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-cyan-300" />
                </span>
                Схема осмотра
              </span>
              <span className="pill tone-cyan">CV + LLM</span>
            </div>

            <div className="relative mt-3 aspect-[16/8] overflow-hidden rounded-xl border border-cyan-200/15 bg-[radial-gradient(120%_120%_at_50%_0%,rgba(56,189,248,0.16),rgba(2,6,23,0.9))]">
              <svg
                viewBox="0 0 320 120"
                fill="none"
                className="absolute inset-0 h-full w-full text-cyan-100/45"
              >
                <path
                  d="M20 86h280M48 86l10-26c2-6 8-10 14-10h44l22-18h58c7 0 13 4 16 10l12 26"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M104 50h64l16 14H92l12-14Z"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinejoin="round"
                />
                <circle cx="96" cy="86" r="12" stroke="currentColor" strokeWidth="1.8" />
                <circle cx="232" cy="86" r="12" stroke="currentColor" strokeWidth="1.8" />
                <path d="M20 86h64M256 86h44" stroke="currentColor" strokeWidth="1.6" />
              </svg>

              <span className="scan-line" />

              <span className="pointer-events-none absolute left-3 top-3 h-6 w-6 rounded-tl-md border-l-2 border-t-2 border-cyan-200/60" />
              <span className="pointer-events-none absolute right-3 top-3 h-6 w-6 rounded-tr-md border-r-2 border-t-2 border-cyan-200/60" />
              <span className="pointer-events-none absolute bottom-3 left-3 h-6 w-6 rounded-bl-md border-b-2 border-l-2 border-cyan-200/60" />
              <span className="pointer-events-none absolute bottom-3 right-3 h-6 w-6 rounded-br-md border-b-2 border-r-2 border-cyan-200/60" />
            </div>

            <div className="mt-3 grid grid-cols-4 gap-1.5 text-center text-[10px] font-medium text-slate-400">
              {["Перед", "Зад", "Левый", "Правый"].map((side) => (
                <span
                  key={side}
                  className="rounded-lg border border-white/10 bg-white/[0.03] px-1 py-1.5"
                >
                  {side}
                </span>
              ))}
            </div>
          </div>
        </section>

        <section className="panel reveal w-full p-6 sm:p-8">
          <div className="mb-7 flex items-center justify-between lg:hidden">
            <Logo />
            <span className="pill tone-cyan">AI</span>
          </div>

          <p className="text-[0.66rem] font-semibold uppercase tracking-[0.24em] text-cyan-300/80">
            FleetGuard AI
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">{title}</h2>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{subtitle}</p>

          <div className="mt-7">{children}</div>

          <div className="mt-7 border-t border-white/[0.06] pt-5 text-sm text-slate-400">
            {footer}
          </div>
        </section>
      </div>
    </main>
  );
}
