import { injectBasicCatalogStyles } from "@a2ui/web_core/v0_9/basic_catalog";

const FALLBACK_STYLE_ID = "a2ui-theme-fallback";

const HOST_THEME_CSS = `
  .a2ui-host {
    color-scheme: light;
    --a2ui-color-background: #eee;
    --a2ui-color-on-background: #333;
    --a2ui-color-surface: #f5f5f5;
    --a2ui-color-on-surface: #333;
    --a2ui-color-primary: #1177ee;
    --a2ui-color-primary-hover: #3399ff;
    --a2ui-color-on-primary: #fff;
    --a2ui-color-secondary: #ddd;
    --a2ui-color-secondary-hover: #ccc;
    --a2ui-color-on-secondary: #333;
    --a2ui-border-radius: 0.25rem;
    --a2ui-color-border: #ccc;
    --a2ui-border-width: 1px;
    --a2ui-color-input: #fff;
    --a2ui-color-on-input: #333;
    --a2ui-grid-base: 0.5rem;
    --a2ui-spacing-xs: calc(var(--a2ui-spacing-s) / 2);
    --a2ui-spacing-s: calc(var(--a2ui-spacing-m) / 2);
    --a2ui-spacing-m: var(--a2ui-grid-base);
    --a2ui-spacing-l: calc(var(--a2ui-spacing-m) * 2);
    --a2ui-spacing-xl: calc(var(--a2ui-spacing-l) * 2);
    --a2ui-font-size: 1rem;
    --a2ui-font-scale: 1.2;
    --a2ui-font-size-xs: calc(var(--a2ui-font-size-s) / var(--a2ui-font-scale));
    --a2ui-font-size-s: calc(var(--a2ui-font-size-m) / var(--a2ui-font-scale));
    --a2ui-font-size-m: var(--a2ui-font-size);
    --a2ui-font-size-l: calc(var(--a2ui-font-size-m) * var(--a2ui-font-scale));
    --a2ui-font-size-xl: calc(var(--a2ui-font-size-l) * var(--a2ui-font-scale));
    --a2ui-font-size-2xl: calc(var(--a2ui-font-size-xl) * var(--a2ui-font-scale));
    --a2ui-line-height-headings: 1.2;
    --a2ui-line-height-body: 1.5;
    --a2ui-color-border-hover: #999;
  }
`;

function supportsAdoptedStyleSheets(): boolean {
  return typeof document !== "undefined" && "adoptedStyleSheets" in document;
}

function injectHostThemeFallback(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById(FALLBACK_STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = FALLBACK_STYLE_ID;
  style.textContent = HOST_THEME_CSS;
  document.head.appendChild(style);
}

function themeVariablesActive(): boolean {
  if (typeof document === "undefined") return false;
  const value = getComputedStyle(document.documentElement).getPropertyValue("--a2ui-color-primary");
  return value.trim().length > 0;
}

let initialized = false;

export function ensureA2uiTheme(): void {
  if (typeof document === "undefined" || initialized) return;
  initialized = true;

  if (supportsAdoptedStyleSheets()) {
    injectBasicCatalogStyles();
  }

  if (!supportsAdoptedStyleSheets() || !themeVariablesActive()) {
    injectHostThemeFallback();
  }
}
