import { Suspense } from "react";

import { InspectionDetails } from "@/components/InspectionDetails";
import { LoadingScreen } from "@/components/LoadingScreen";

interface InspectionPageProps {
  params: Promise<{ id: string }>;
}

async function InspectionContent({ params }: InspectionPageProps) {
  const { id } = await params;
  return <InspectionDetails inspectionId={id} />;
}

export default function InspectionPage(props: InspectionPageProps) {
  return (
    <Suspense fallback={<LoadingScreen label="Загружаем осмотр…" />}>
      <InspectionContent {...props} />
    </Suspense>
  );
}
