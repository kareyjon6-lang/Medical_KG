import { Suspense } from "react";

import Workbench from "../../components/Workbench";

export default function SearchPage() {
  return (
    <Suspense>
      <Workbench initialView="search" />
    </Suspense>
  );
}
