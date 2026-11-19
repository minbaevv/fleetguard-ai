import { Suspense } from "react";

import { CaptureWizard } from "@/components/CaptureWizard";
import { LoadingScreen } from "@/components/LoadingScreen";

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
    <Suspense fallback={<LoadingScreen label="Готовим мастер съёмки…" />}>
      <NewInspectionContent {...props} />
    </Suspense>
  );
}
