import { Suspense } from "react";

import { InspectionDetails } from "@/components/InspectionDetails";

interface InspectionPageProps {
  params: Promise<{ id: string }>;
}

async function InspectionContent({ params }: InspectionPageProps) {
  const { id } = await params;
  return <InspectionDetails inspectionId={id} />;
}

export default function InspectionPage(props: InspectionPageProps) {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center text-slate-500" role="status">
          Загрузка…
        </main>
      }
    >
      <InspectionContent {...props} />
    </Suspense>
  );
}
