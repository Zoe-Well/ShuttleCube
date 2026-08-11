import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { parse, stringify } from "yaml";

const source = "specs/001-badminton-operations/contracts/openapi.yaml";
const operationsSource = "specs/002-intelligent-operations/contracts/openapi.yaml";
const temp = "frontend/src/api/generated/current-openapi.yaml";
const output = "frontend/src/api/generated/schema.d.ts";
const document = parse(readFileSync(source, "utf8"));
const future = document["x-future-path-prefixes"] ?? [];
for (const path of Object.keys(document.paths ?? {})) {
  if (future.some((prefix) => path === prefix || path.startsWith(`${prefix}/`) || path.startsWith(`${prefix}{`))) delete document.paths[path];
}
delete document["x-future-path-prefixes"];
const operations = parse(readFileSync(operationsSource, "utf8"));
document.tags = [
  ...(document.tags ?? []),
  ...(operations.tags ?? []).filter(
    (candidate) => !(document.tags ?? []).some((tag) => tag.name === candidate.name),
  ),
];
document.paths = { ...(document.paths ?? {}), ...(operations.paths ?? {}) };
document.components = document.components ?? {};
for (const [section, values] of Object.entries(operations.components ?? {})) {
  document.components[section] = {
    ...(document.components[section] ?? {}),
    ...values,
  };
}
mkdirSync("frontend/src/api/generated", { recursive: true });
writeFileSync(temp, stringify(document));
execFileSync(process.execPath, ["node_modules/openapi-typescript/bin/cli.js", temp, "-o", output], { stdio: "inherit" });
