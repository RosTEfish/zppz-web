// Write gzip (.gz, level 9) and Brotli (.br, quality 11) siblings next to
// compressible files in a Vite dist directory. Host nginx can then serve
// them with gzip_static / brotli_static instead of compressing on the fly.
// Already-compressed binaries (images, woff/woff2, archives) are skipped.
// No zstd.

import { availableParallelism } from "node:os";
import { readdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { basename, extname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { promisify } from "node:util";
import { brotliCompress, constants as zlibConstants, gzip } from "node:zlib";

const gzipAsync = promisify(gzip);
const brotliAsync = promisify(brotliCompress);

export const MIN_BYTES = 256;
export const GZIP_LEVEL = 9;
export const BROTLI_QUALITY = 11;

const TEXT_EXTENSIONS = new Set([
  ".js",
  ".mjs",
  ".cjs",
  ".css",
  ".html",
  ".htm",
  ".svg",
  ".json",
  ".webmanifest",
  ".txt",
  ".map",
  ".xml",
]);

const GENERIC_EXTENSIONS = new Set([".wasm"]);

export const COMPRESSIBLE_EXTENSIONS = new Set([...TEXT_EXTENSIONS, ...GENERIC_EXTENSIONS]);

// These must gain a smaller .gz and a smaller .br once they pass MIN_BYTES.
// wasm and source maps are compressed when that helps, but a file that does
// not shrink is not a failed release.
export const REQUIRED_EXTENSIONS = new Set([
  ".js",
  ".mjs",
  ".cjs",
  ".css",
  ".html",
  ".htm",
  ".svg",
  ".json",
  ".webmanifest",
  ".txt",
  ".xml",
]);

export function compressionKind(filePath) {
  const name = basename(filePath);
  if (name.endsWith(".gz") || name.endsWith(".br") || name.endsWith(".zst")) return null;
  const ext = extname(name).toLowerCase();
  if (TEXT_EXTENSIONS.has(ext)) return "text";
  if (GENERIC_EXTENSIONS.has(ext)) return "generic";
  return null;
}

async function writeIfSmaller(filePath, suffix, compressed, originalSize) {
  const target = `${filePath}.${suffix}`;
  if (compressed.length >= originalSize) {
    await rm(target, { force: true });
    return false;
  }
  const temporary = `${target}.${process.pid}.tmp`;
  try {
    await writeFile(temporary, compressed, { mode: 0o644 });
    await rename(temporary, target);
  } catch (error) {
    await rm(temporary, { force: true });
    throw error;
  }
  return true;
}

export async function precompressFile(filePath, size) {
  const kind = compressionKind(filePath);
  if (!kind || size < MIN_BYTES) {
    return { gzip: false, brotli: false, considered: false };
  }
  const data = await readFile(filePath);
  const mode = kind === "text" ? zlibConstants.BROTLI_MODE_TEXT : zlibConstants.BROTLI_MODE_GENERIC;
  const [gz, br] = await Promise.all([
    gzipAsync(data, { level: GZIP_LEVEL }),
    brotliAsync(data, {
      params: {
        [zlibConstants.BROTLI_PARAM_QUALITY]: BROTLI_QUALITY,
        [zlibConstants.BROTLI_PARAM_SIZE_HINT]: data.length,
        [zlibConstants.BROTLI_PARAM_MODE]: mode,
      },
    }),
  ]);
  const [gzipWritten, brotliWritten] = await Promise.all([
    writeIfSmaller(filePath, "gz", gz, data.length),
    writeIfSmaller(filePath, "br", br, data.length),
  ]);
  return { gzip: gzipWritten, brotli: brotliWritten, considered: true };
}

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) files.push(...(await walk(path)));
    else if (entry.isFile()) files.push(path);
  }
  return files;
}

async function mapPool(items, limit, fn) {
  const results = new Array(items.length);
  let cursor = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      results[index] = await fn(items[index]);
    }
  });
  await Promise.all(workers);
  return results;
}

export async function precompressDir(distDir, options = {}) {
  const root = resolve(distDir);
  const info = await stat(root).catch((error) => {
    if (error?.code === "ENOENT") return null;
    throw error;
  });
  if (!info?.isDirectory()) {
    throw new Error(`precompress: dist directory not found: ${root}`);
  }
  const files = await walk(root);
  // libuv's default pool is 4. Stay within it so Brotli jobs do not pile up
  // behind a larger concurrency number than the process can actually run.
  const limit = options.concurrency ?? Math.max(1, Math.min(4, availableParallelism()));
  const outcomes = await mapPool(files, limit, async (file) => {
    const size = (await stat(file)).size;
    const result = await precompressFile(file, size);
    return { file, size, ...result };
  });
  const missing = outcomes.filter((item) => {
    if (!item.considered) return false;
    if (!REQUIRED_EXTENSIONS.has(extname(item.file).toLowerCase())) return false;
    return !item.gzip || !item.brotli;
  });
  return {
    gzipCount: outcomes.filter((item) => item.gzip).length,
    brotliCount: outcomes.filter((item) => item.brotli).length,
    missing,
  };
}

function invokedAsCli() {
  const entry = process.argv[1];
  if (!entry) return false;
  return import.meta.url === pathToFileURL(resolve(entry)).href;
}

async function main() {
  const distDir = process.argv[2] ? resolve(process.argv[2]) : resolve(import.meta.dirname, "..", "dist");
  const indexHtml = join(distDir, "index.html");
  try {
    const indexSize = (await stat(indexHtml)).size;
    if (indexSize < MIN_BYTES) {
      throw new Error(`precompress: index.html is ${indexSize} bytes, under ${MIN_BYTES}`);
    }
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new Error(`precompress: ${indexHtml} is missing`);
    }
    throw error;
  }
  const summary = await precompressDir(distDir);
  if (summary.missing.length) {
    const lines = summary.missing.map((item) => `  ${item.file}`);
    throw new Error(
      `precompress: required assets did not gain smaller .gz and .br siblings:\n${lines.join("\n")}`,
    );
  }
  console.log(`precompress: wrote ${summary.gzipCount} .gz and ${summary.brotliCount} .br under ${distDir}`);
}

if (invokedAsCli()) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
