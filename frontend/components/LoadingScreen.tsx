interface LoadingScreenProps {
  label?: string;
}

export function LoadingScreen({ label = "Загрузка…" }: LoadingScreenProps) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-5 px-4">
      <span className="loader-ring" aria-hidden="true" />
      <p role="status" className="text-sm tracking-wide text-slate-400">
        {label}
      </p>
    </main>
  );
}
