import { readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";

const root = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(await readFile(resolve(root, "dist/.vite/manifest.json"), "utf8"));
const entry = manifest["index.html"];
if (!entry?.file) throw new Error("Vite manifest does not contain the index entry");

async function sizeOf(file) {
  const path = resolve(root, "dist", file);
  const [bytes, contents] = await Promise.all([stat(path).then((value) => value.size), readFile(path)]);
  return { bytes, gzipBytes: gzipSync(contents).byteLength };
}

function format(bytes) {
  return `${(bytes / 1024).toFixed(1)} KiB`;
}

const entrySize = await sizeOf(entry.file);
const rawLimit = 500 * 1024;
const gzipLimit = 160 * 1024;
if (entrySize.bytes > rawLimit || entrySize.gzipBytes > gzipLimit) {
  throw new Error(
    `Entry bundle ${format(entrySize.bytes)} raw / ${format(entrySize.gzipBytes)} gzip exceeds `
    + `the ${format(rawLimit)} raw / ${format(gzipLimit)} gzip budget`,
  );
}
console.log(`Entry bundle ${format(entrySize.bytes)} raw / ${format(entrySize.gzipBytes)} gzip is within budget`);

const routeChunks = await Promise.all(
  Object.entries(manifest)
    .filter(([source, item]) => source.includes("src/pages/") && item.file?.endsWith(".js"))
    .map(async ([source, item]) => ({ source, ...(await sizeOf(item.file)) })),
);
routeChunks.sort((left, right) => right.bytes - left.bytes);
console.log("Route chunk report (raw / gzip):");
for (const chunk of routeChunks) {
  console.log(`  ${chunk.source}: ${format(chunk.bytes)} / ${format(chunk.gzipBytes)}`);
}
