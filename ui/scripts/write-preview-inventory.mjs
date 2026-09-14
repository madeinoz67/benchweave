import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const uiRoot = resolve(here, "..");
const packageDocument = JSON.parse(await readFile(join(uiRoot, "package.json"), "utf8"));
const previewRoot = resolve(uiRoot, "../packages/sdk/src/benchweave_sdk/preview_assets");
const siteRoot = join(previewRoot, "site");

async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => entry.isDirectory() ? files(join(directory, entry.name)) : [join(directory, entry.name)]));
  return nested.flat();
}

const assets = [];
for (const path of (await files(siteRoot)).sort()) {
  const content = await readFile(path);
  assets.push({
    path: relative(previewRoot, path).split(sep).join("/"),
    sha256: createHash("sha256").update(content).digest("hex"),
    size: content.byteLength,
  });
}
if (assets.length === 0) throw new Error("Preview renderer produced no assets");
const inventory = { api_version: 1, renderer_version: packageDocument.version, assets };
await writeFile(join(previewRoot, "inventory.json"), `${JSON.stringify(inventory, null, 2)}\n`, "utf8");
