import { readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(await readFile(resolve(root, "dist/.vite/manifest.json"), "utf8"));
const entry = manifest["index.html"];
if (!entry?.file) throw new Error("Vite manifest does not contain the index entry");

const bytes = (await stat(resolve(root, "dist", entry.file))).size;
const limit = 500 * 1024;
if (bytes > limit) {
  throw new Error(`Entry bundle ${(bytes / 1024).toFixed(1)} KiB exceeds the 500 KiB budget`);
}
console.log(`Entry bundle ${(bytes / 1024).toFixed(1)} KiB is within the 500 KiB budget`);
