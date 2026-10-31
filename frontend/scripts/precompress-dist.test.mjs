import { createHash } from "node:crypto";
import { mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { brotliDecompressSync, gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";

import { MIN_BYTES, precompressDir } from "./precompress-dist.mjs";

function compressibleBody() {
  return `/* zppz static ${"asset ".repeat(40)} */\n`.repeat(12);
}

function highEntropy(size) {
  const chunks = [];
  let index = 0;
  while (Buffer.concat(chunks).length < size) {
    chunks.push(createHash("sha256").update(`zppz-entropy-${index}`).digest());
    index += 1;
  }
  return Buffer.concat(chunks).subarray(0, size);
}

describe("precompressDir", () => {
  it("writes gzip and brotli siblings for text assets and skips compressed binaries", async () => {
    const dir = await mkdtemp(join(tmpdir(), "zppz-precompress-"));
    const body = compressibleBody();
    expect(Buffer.byteLength(body)).toBeGreaterThanOrEqual(MIN_BYTES);
    const compressible = [
      "app.js",
      "app.mjs",
      "app.css",
      "index.html",
      "icon.svg",
      "data.json",
      "site.webmanifest",
      "notes.txt",
      "app.js.map",
      "mod.wasm",
    ];
    const skipped = ["icon.png", "photo.jpg", "photo.webp", "photo.avif", "font.woff2", "font.woff", "pic.gif", "archive.zip"];
    try {
      await Promise.all(compressible.map((name) => writeFile(join(dir, name), body)));
      await Promise.all(skipped.map((name) => writeFile(join(dir, name), body)));
      await writeFile(join(dir, "tiny.txt"), "ok\n");

      const summary = await precompressDir(dir);
      expect(summary.missing).toEqual([]);
      expect(summary.gzipCount).toBe(compressible.length);
      expect(summary.brotliCount).toBe(compressible.length);

      const original = await readFile(join(dir, "app.js"));
      const gz = await readFile(join(dir, "app.js.gz"));
      const br = await readFile(join(dir, "app.js.br"));
      expect(gz.length).toBeLessThan(original.length);
      expect(br.length).toBeLessThan(original.length);
      expect(Buffer.compare(gunzipSync(gz), original)).toBe(0);
      expect(Buffer.compare(brotliDecompressSync(br), original)).toBe(0);

      for (const name of skipped) {
        await expect(stat(join(dir, `${name}.gz`))).rejects.toMatchObject({ code: "ENOENT" });
        await expect(stat(join(dir, `${name}.br`))).rejects.toMatchObject({ code: "ENOENT" });
      }
      await expect(stat(join(dir, "tiny.txt.gz"))).rejects.toMatchObject({ code: "ENOENT" });
      const names = await readdir(dir);
      expect(names.some((name) => name.endsWith(".zst"))).toBe(false);

      const again = await precompressDir(dir);
      expect(again.missing).toEqual([]);
      expect(again.gzipCount).toBe(compressible.length);
      expect(again.brotliCount).toBe(compressible.length);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  it("reports a required text file that does not shrink", async () => {
    const dir = await mkdtemp(join(tmpdir(), "zppz-precompress-entropy-"));
    try {
      const noise = highEntropy(512);
      expect(noise.length).toBeGreaterThanOrEqual(MIN_BYTES);
      await writeFile(join(dir, "noise.js"), noise);
      const summary = await precompressDir(dir);
      expect(summary.missing.map((item) => item.file)).toEqual([join(dir, "noise.js")]);
      expect(summary.gzipCount).toBe(0);
      expect(summary.brotliCount).toBe(0);
      await expect(stat(join(dir, "noise.js.gz"))).rejects.toMatchObject({ code: "ENOENT" });
      await expect(stat(join(dir, "noise.js.br"))).rejects.toMatchObject({ code: "ENOENT" });
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});
