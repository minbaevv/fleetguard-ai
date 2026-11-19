interface LogoProps {
  withWordmark?: boolean;
  className?: string;
}

export function Logo({ withWordmark = true, className = "" }: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span className="logo-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
          <path
            d="M12 3.2 19 6v5.4c0 4.1-2.8 7.6-7 9.4-4.2-1.8-7-5.3-7-9.4V6l7-2.8Z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
          <path
            d="M8.6 11.9h2.1l1.1-2.1 1.6 3.8 1-.9h1.4"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      {withWordmark ? (
        <span className="text-[0.82rem] font-semibold uppercase tracking-[0.2em] text-white">
          Fleetguard<span className="text-cyan-300"> AI</span>
        </span>
      ) : null}
    </span>
  );
}
