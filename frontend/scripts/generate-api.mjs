import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";
import openapiTS, { astToString, COMMENT_HEADER } from "openapi-typescript";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const backendDir = resolve(frontendDir, "../backend");
const outputPath = resolve(frontendDir, "src/api/generated.ts");
const checkOnly = process.argv.includes("--check");
const temporaryDir = await mkdtemp(resolve(tmpdir(), "zppz-openapi-"));
const schemaPath = resolve(temporaryDir, "openapi.json");

function exportSchema() {
  const candidates = process.env.PYTHON
    ? [[process.env.PYTHON, []]]
    : process.platform === "win32"
      ? [["python", []], ["py", ["-3"]]]
      : [["python3", []], ["python", []]];
  for (const [command, prefix] of candidates) {
    const result = spawnSync(command, [...prefix, "-m", "app.export_openapi", "--output", schemaPath], {
      cwd: backendDir,
      env: { ...process.env, DATA_DIR: resolve(temporaryDir, "data") },
      encoding: "utf8",
    });
    if (!result.error && result.status === 0) return;
  }
  throw new Error("Unable to export OpenAPI schema. Ensure Python and backend dependencies are installed.");
}

try {
  exportSchema();
  const nodes = await openapiTS(pathToFileURL(schemaPath));
  const generated = `${COMMENT_HEADER}${astToString(nodes)}`;
  if (checkOnly) {
    const current = await readFile(outputPath, "utf8").catch(() => "");
    if (current !== generated) {
      throw new Error("Generated OpenAPI types are stale. Run npm run generate:api and commit the result.");
    }
    console.log("Generated OpenAPI types are current.");
  } else {
    await writeFile(outputPath, generated, "utf8");
    console.log(`Generated ${outputPath}`);
  }
} finally {
  await rm(temporaryDir, { recursive: true, force: true });
}
