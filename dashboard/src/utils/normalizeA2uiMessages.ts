type A2uiMessage = Record<string, unknown>;

const COPILOTKIT_BASIC_CATALOG_ID =
  "https://a2ui.org/specification/v0_9/basic_catalog.json";

const BASIC_CATALOG_ALIASES: Record<string, string> = {
  basic: COPILOTKIT_BASIC_CATALOG_ID,
  [COPILOTKIT_BASIC_CATALOG_ID]: COPILOTKIT_BASIC_CATALOG_ID,
  "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json":
    COPILOTKIT_BASIC_CATALOG_ID,
};

function normalizeCatalogId(catalogId: string): string {
  return BASIC_CATALOG_ALIASES[catalogId] ?? catalogId;
}

function normalizeCreateSurfaceMessage(message: A2uiMessage): A2uiMessage {
  const create = message.createSurface;
  if (!create || typeof create !== "object") {
    return message;
  }
  const catalogId = (create as { catalogId?: unknown }).catalogId;
  if (typeof catalogId !== "string") {
    return message;
  }
  const normalizedId = normalizeCatalogId(catalogId);
  if (normalizedId === catalogId) {
    return message;
  }
  return {
    ...message,
    createSurface: {
      ...(create as Record<string, unknown>),
      catalogId: normalizedId,
    },
  };
}

const VALUE_COMPONENTS = new Set([
  "TextField",
  "CheckBox",
  "Slider",
  "DateTimeInput",
  "ChoicePicker",
]);

function hasPathBinding(value: unknown): boolean {
  return Boolean(value && typeof value === "object" && "path" in value);
}

function defaultValueForComponent(component: string): unknown {
  switch (component) {
    case "CheckBox":
      return false;
    case "ChoicePicker":
      return [];
    case "Slider":
      return 0;
    default:
      return "";
  }
}

function isListTemplateChildren(value: unknown): value is { componentId: string; path: string } {
  return (
    Boolean(value) &&
    typeof value === "object" &&
    typeof (value as { componentId?: unknown }).componentId === "string" &&
    typeof (value as { path?: unknown }).path === "string"
  );
}

function collectChildIds(component: Record<string, unknown>): Set<string> {
  const refs = new Set<string>();
  for (const key of ["child", "children"] as const) {
    const value = component[key];
    if (typeof value === "string") {
      refs.add(value);
    } else if (Array.isArray(value)) {
      for (const item of value) {
        if (typeof item === "string") {
          refs.add(item);
        }
      }
    }
  }
  return refs;
}

function collectTemplateSubtree(
  rootId: string,
  byId: Record<string, Record<string, unknown>>
): Set<string> {
  const seen = new Set<string>();
  const queue = [rootId];
  while (queue.length > 0) {
    const componentId = queue.pop();
    if (!componentId || seen.has(componentId) || !byId[componentId]) {
      continue;
    }
    seen.add(componentId);
    for (const childId of collectChildIds(byId[componentId])) {
      queue.push(childId);
    }
  }
  return seen;
}

function rewriteSingleSegmentTemplatePath(value: unknown): unknown {
  if (!value || typeof value !== "object" || !("path" in value)) {
    return value;
  }
  const path = (value as { path?: unknown }).path;
  if (typeof path !== "string") {
    return value;
  }
  if (path.startsWith("/") && !path.slice(1).includes("/")) {
    return { path: path.slice(1) };
  }
  return value;
}

function normalizeListTemplatePaths(components: unknown[]): unknown[] {
  const byId: Record<string, Record<string, unknown>> = {};
  for (const raw of components) {
    if (!raw || typeof raw !== "object") {
      continue;
    }
    const id = (raw as { id?: unknown }).id;
    if (typeof id === "string") {
      byId[id] = raw as Record<string, unknown>;
    }
  }

  const templateIds = new Set<string>();
  for (const comp of Object.values(byId)) {
    if (isListTemplateChildren(comp.children)) {
      for (const id of collectTemplateSubtree(comp.children.componentId, byId)) {
        templateIds.add(id);
      }
    }
  }

  if (templateIds.size === 0) {
    return components;
  }

  return components.map((raw) => {
    if (!raw || typeof raw !== "object") {
      return raw;
    }
    const comp = raw as Record<string, unknown>;
    const id = comp.id;
    if (typeof id !== "string" || !templateIds.has(id)) {
      return raw;
    }
    const next: Record<string, unknown> = { ...comp };
    for (const [key, value] of Object.entries(next)) {
      if (key === "id" || key === "component") {
        continue;
      }
      if (value && typeof value === "object") {
        next[key] = rewriteSingleSegmentTemplatePath(value);
      }
    }
    return next;
  });
}

function normalizeUpdateComponentsMessage(message: A2uiMessage): A2uiMessage[] {
  const update = message.updateComponents;
  if (!update || typeof update !== "object") {
    return [message];
  }

  const surfaceId = (update as { surfaceId?: unknown }).surfaceId;
  const components = (update as { components?: unknown }).components;
  if (typeof surfaceId !== "string" || !Array.isArray(components)) {
    return [message];
  }

  const nextComponents: unknown[] = [];
  const dataModelPatches: Array<{ path: string; value: unknown }> = [];

  for (const raw of components) {
    if (!raw || typeof raw !== "object") {
      nextComponents.push(raw);
      continue;
    }
    const comp = { ...(raw as Record<string, unknown>) };
    const componentName = String(comp.component || "");
    if (VALUE_COMPONENTS.has(componentName) && !hasPathBinding(comp.value)) {
      const id = String(comp.id || "").trim();
      if (id) {
        const path = `/fields/${id}`;
        comp.value = { path };
        dataModelPatches.push({
          path,
          value: defaultValueForComponent(componentName),
        });
      }
    }
    nextComponents.push(comp);
  }

  const normalizedComponents = normalizeListTemplatePaths(nextComponents);

  if (dataModelPatches.length === 0) {
    return [
      {
        ...message,
        updateComponents: {
          ...(update as Record<string, unknown>),
          surfaceId,
          components: normalizedComponents,
        },
      },
    ];
  }

  const normalizedUpdate: A2uiMessage = {
    ...message,
    updateComponents: {
      ...(update as Record<string, unknown>),
      surfaceId,
      components: normalizedComponents,
    },
  };

  const dataModelMessages: A2uiMessage[] = dataModelPatches.map(({ path, value }) => ({
    version: "v0.9",
    updateDataModel: {
      surfaceId,
      path,
      value,
    },
  }));

  return [normalizedUpdate, ...dataModelMessages];
}

/** Ensure interactive components have data-model paths so inputs remain editable. */
export function normalizeA2uiMessages(messages: A2uiMessage[]): A2uiMessage[] {
  const normalized: A2uiMessage[] = [];
  for (const message of messages) {
    if (!message || typeof message !== "object") {
      normalized.push(message);
      continue;
    }
    if (message.createSurface) {
      normalized.push(normalizeCreateSurfaceMessage(message));
      continue;
    }
    if (message.updateComponents) {
      normalized.push(...normalizeUpdateComponentsMessage(message));
      continue;
    }
    normalized.push(message);
  }
  return normalized;
}
