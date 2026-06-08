import { Suspense } from "react";

import Workbench from "../components/Workbench";

export default function Home() {
  return (
    <Suspense>
      <Workbench initialView="assistant" />
    </Suspense>
  );
}
