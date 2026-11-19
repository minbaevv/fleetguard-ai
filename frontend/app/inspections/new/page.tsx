import { Suspense } from "react";

import { CaptureWizard } from "@/components/CaptureWizard";

interface NewInspectionPageProps {
  searchParams: Promise<{ vehicleId?: string | string[] }>;
}

async function NewInspectionContent({ searchParams }: NewInspectionPageProps) {
  const params = await searchParams;
  const vehicleId = typeof params.vehicleId === "string" ? params.vehicleId : null;
  return <CaptureWizard initialVehicleId={vehicleId} />;
}

export default function NewInspectionPage(props: NewInspectionPageProps) {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center text-slate-500" role="status">
          Загрузка…
        </main>
      }
    >
      <NewInspectionContent {...props} />
    </Suspense>
  );
}
