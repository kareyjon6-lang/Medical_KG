import { Suspense } from "react";

import Workbench from "../../components/Workbench";

export default function AssistantPage() {
  return (
    <Suspense>
      <Workbench initialView="assistant" />
    </Suspense>
  );
}
