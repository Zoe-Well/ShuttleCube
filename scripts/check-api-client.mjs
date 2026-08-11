import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parse, stringify } from "yaml";

const doc = parse(readFileSync("specs/001-badminton-operations/contracts/openapi.yaml", "utf8"));
const operations = parse(readFileSync("specs/002-intelligent-operations/contracts/openapi.yaml", "utf8"));
const future = doc["x-future-path-prefixes"] ?? [];
for (const path of Object.keys(doc.paths ?? {})) {
  if (future.some((prefix) => path === prefix || path.startsWith(`${prefix}/`) || path.startsWith(`${prefix}{`))) delete doc.paths[path];
}
delete doc["x-future-path-prefixes"];
doc.tags = [
  ...(doc.tags ?? []),
  ...(operations.tags ?? []).filter(
    (candidate) => !(doc.tags ?? []).some((tag) => tag.name === candidate.name),
  ),
];
doc.paths = { ...(doc.paths ?? {}), ...(operations.paths ?? {}) };
doc.components = doc.components ?? {};
for (const [section, values] of Object.entries(operations.components ?? {})) {
  doc.components[section] = { ...(doc.components[section] ?? {}), ...values };
}
const generatedDocument = parse(
  readFileSync("frontend/src/api/generated/current-openapi.yaml", "utf8"),
);
if (JSON.stringify(generatedDocument) !== JSON.stringify(doc)) {
  throw new Error("generated OpenAPI document drifted; run node scripts/generate-api-client.mjs");
}
const generated = readFileSync("frontend/src/api/generated/schema.d.ts", "utf8");
for (const prefix of future) {
  if (generated.includes(`\"${prefix}`)) throw new Error(`future Agent path leaked into generated client: ${prefix}`);
}
for (const path of Object.keys(operations.paths ?? {})) {
  if (!generated.includes(`"${path}"`)) throw new Error(`operations path missing from generated client: ${path}`);
}
const temporaryDirectory = mkdtempSync(join(tmpdir(), "shuttlecube-openapi-"));
try {
  const temporaryOpenApi = join(temporaryDirectory, "openapi.yaml");
  const temporaryTypes = join(temporaryDirectory, "schema.d.ts");
  writeFileSync(temporaryOpenApi, stringify(doc));
  execFileSync(
    process.execPath,
    ["node_modules/openapi-typescript/bin/cli.js", temporaryOpenApi, "-o", temporaryTypes],
    { stdio: "ignore" },
  );
  if (readFileSync(temporaryTypes, "utf8") !== generated) {
    throw new Error("generated TypeScript schema drifted; run node scripts/generate-api-client.mjs");
  }
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true });
}
console.log(`API client scope OK (${Object.keys(doc.paths ?? {}).length} documented paths)`);
