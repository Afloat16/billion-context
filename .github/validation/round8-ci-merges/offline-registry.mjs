// Validation-only: use the repository's network seam to keep the optional
// models.dev catalog refresh offline. Product sources and test assertions
// are unchanged; loadRegistry uses its committed snapshot fallback.
import { pathToFileURL } from "node:url";
import path from "node:path";

const { _setRegistryFetchForTest } = await import(pathToFileURL(path.join(process.cwd(), "src/registry.ts")).href);
_setRegistryFetchForTest(async () => {
    throw new Error("Validation runs offline: registry network access is disabled");
});
