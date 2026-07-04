import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "node_modules/@a2ui/react/v0_9/index.css");
const target = join(root, "src/styles/a2ui-v0_9.css");

mkdirSync(dirname(target), { recursive: true });
let css = readFileSync(source, "utf8");
css = css.replace(/:global\(([^)]+)\)/g, "$1");
writeFileSync(target, css, "utf8");
console.log(`Synced A2UI CSS -> ${target}`);
