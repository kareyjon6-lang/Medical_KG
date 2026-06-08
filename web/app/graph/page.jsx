import { Suspense } from "react";

import Workbench from "../../components/Workbench";

export default function GraphPage() {
  return (
    <Suspense>
      <Workbench initialView="graph" />
    </Suspense>
  );
}
