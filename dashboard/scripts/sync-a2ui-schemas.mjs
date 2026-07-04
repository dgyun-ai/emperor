import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const schemas = join(root, "node_modules/@a2ui/web_core/src/v0_9/schemas");
const basicCatalogCandidates = [
  join(
    root,
    "node_modules/@copilotkit/a2ui-renderer/node_modules/@a2ui/web_core/src/v0_9/schemas/basic_catalog.json",
  ),
  join(schemas, "basic_catalog.json"),
];
const targetRoot = join(root, "public/a2ui/specification/v0_9");

const copies = [
  ["catalogs/basic/catalog.json", "catalogs/basic/catalog.json"],
  ["common_types.json", "common_types.json"],
];

const A2UI_COMMON_TYPES =
  "https://a2ui.org/specification/v0_9/common_types.json";

mkdirSync(join(targetRoot, "catalogs/basic"), { recursive: true });

const basicCatalogSource = basicCatalogCandidates.find((path) => existsSync(path));
if (basicCatalogSource) {
  copyFileSync(
    basicCatalogSource,
    join(targetRoot, "basic_catalog.json"),
  );
}

for (const [sourceRel, targetRel] of copies) {
  const source = join(schemas, sourceRel);
  const target = join(targetRoot, targetRel);
  mkdirSync(dirname(target), { recursive: true });

  let text = readFileSync(source, "utf8");
  if (targetRel === "catalogs/basic/catalog.json") {
    // Use relative refs so local hosting does not hit a2ui.org.
    text = text.replaceAll(
      `${A2UI_COMMON_TYPES}#`,
      "../../common_types.json#",
    );
  }
  writeFileSync(target, text, "utf8");
}

console.log(`Synced A2UI v0.9 schemas -> ${targetRoot}`);
