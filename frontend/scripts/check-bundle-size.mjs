import { readdir, readFile, stat } from "node:fs/promises";
import { join, resolve } from "node:path";
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

const javascriptFiles = [...new Set(Object.values(manifest).map((item) => item.file).filter((file) => file?.endsWith(".js")))];
for (const file of javascriptFiles) {
  const size = await sizeOf(file);
  if (size.bytes > rawLimit || size.gzipBytes > gzipLimit) {
    throw new Error(
      `JavaScript chunk ${file} ${format(size.bytes)} raw / ${format(size.gzipBytes)} gzip exceeds `
      + `the ${format(rawLimit)} raw / ${format(gzipLimit)} gzip budget`,
    );
  }
}

const chunkReport = await Promise.all(
  Object.entries(manifest)
    .filter(([, item]) => item.file?.endsWith(".js") && !item.isEntry)
    .map(async ([source, item]) => ({ source, ...(await sizeOf(item.file)) })),
);
chunkReport.sort((left, right) => right.bytes - left.bytes);
console.log("JavaScript chunk report (raw / gzip):");
for (const chunk of chunkReport) {
  console.log(`  ${chunk.source}: ${format(chunk.bytes)} / ${format(chunk.gzipBytes)}`);
}

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) files.push(...await walk(path));
    else files.push(path);
  }
  return files;
}

const distDir = resolve(root, "dist");
const fontFiles = (await walk(distDir)).filter((file) => /\.(?:woff2|woff)$/i.test(file));
const sansFonts = fontFiles.filter((file) => /noto-sans/i.test(file));
if (sansFonts.length) {
  throw new Error(`Noto Sans webfonts must not be emitted: ${sansFonts.join(", ")}`);
}

const cjkWoff2 = [];
for (const file of fontFiles) {
  if (!file.endsWith(".woff2") || !/noto-serif|chinese-simplified/i.test(file)) continue;
  const contents = await readFile(file);
  cjkWoff2.push({ file, bytes: contents.byteLength });
}
const cjkBytes = cjkWoff2.reduce((sum, item) => sum + item.bytes, 0);
const cjkLimit = Math.round(1.7 * 1024 * 1024);
if (cjkWoff2.length !== 1 || cjkBytes > cjkLimit) {
  throw new Error(
    `CJK woff2 must be a single Noto Serif SC file within ${format(cjkLimit)}; `
    + `found ${cjkWoff2.length} file(s), ${format(cjkBytes)}`
    + (cjkWoff2.length ? `: ${cjkWoff2.map((item) => item.file).join(", ")}` : ""),
  );
}
console.log(`CJK woff2 ${format(cjkBytes)} is within the ${format(cjkLimit)} budget`);
