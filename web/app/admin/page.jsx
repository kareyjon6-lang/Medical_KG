import { Suspense } from "react";

import Workbench from "../../components/Workbench";

export default function AdminPage() {
  return (
    <Suspense>
      <Workbench initialView="admin" />
    </Suspense>
  );
}
