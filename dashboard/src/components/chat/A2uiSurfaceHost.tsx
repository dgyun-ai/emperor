import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MessageProcessor } from "@a2ui/web_core/v0_9";
import { A2uiSurface, basicCatalog, MarkdownContext } from "@a2ui/react/v0_9";
import type { ReactComponentImplementation } from "@a2ui/react/v0_9";
import { renderMarkdown } from "@a2ui/markdown-it";
import { ensureA2uiTheme } from "../../a2ui/ensureA2uiTheme";
import { applyA2uiMessagesIncrementally, type A2uiMessage } from "../../utils/a2uiProcessor";
import "../../styles/a2ui-v0_9.css";

export type { A2uiMessage };

type Props = {
  messages: A2uiMessage[];
  onAction?: (action: Record<string, unknown>) => void | Promise<void>;
  disabled?: boolean;
};

export default function A2uiSurfaceHost({ messages, onAction, disabled = false }: Props) {
  const onActionRef = useRef(onAction);
  const disabledRef = useRef(disabled);
  onActionRef.current = onAction;
  disabledRef.current = disabled;

  const appliedCountRef = useRef(0);
  const [processorGeneration, setProcessorGeneration] = useState(0);
  const processorRef = useRef<MessageProcessor<ReactComponentImplementation> | null>(null);

  const markdownRenderer = useMemo(() => renderMarkdown, []);

  const processor = useMemo(() => {
    const instance = new MessageProcessor<ReactComponentImplementation>([basicCatalog], (action) => {
      if (disabledRef.current) return;
      const surfaceId = String((action as { surfaceId?: unknown }).surfaceId || "");
      const surface = processorRef.current?.model.getSurface(surfaceId);
      const dataModel = surface?.dataModel.get("/");
      void onActionRef.current?.({
        ...(action as Record<string, unknown>),
        ...(dataModel !== undefined ? { dataModel } : {}),
      });
    });
    processorRef.current = instance;
    return instance;
  }, [processorGeneration]);

  const [surfaces, setSurfaces] = useState(() =>
    Array.from(processor.model.surfacesMap.values())
  );

  useEffect(() => {
    ensureA2uiTheme();
  }, []);

  useEffect(() => {
    appliedCountRef.current = 0;
    setSurfaces(Array.from(processor.model.surfacesMap.values()));
  }, [processor]);

  const syncSurfaces = useCallback(() => {
    setSurfaces(Array.from(processor.model.surfacesMap.values()));
  }, [processor]);

  useEffect(() => {
    const createdSub = processor.onSurfaceCreated(syncSurfaces);
    const deletedSub = processor.onSurfaceDeleted(syncSurfaces);
    return () => {
      createdSub.unsubscribe();
      deletedSub.unsubscribe();
    };
  }, [processor, syncSurfaces]);

  useEffect(() => {
    if (messages.length === 0) {
      appliedCountRef.current = 0;
      return;
    }
    if (messages.length < appliedCountRef.current) {
      appliedCountRef.current = 0;
      setProcessorGeneration((value) => value + 1);
      return;
    }
    appliedCountRef.current = applyA2uiMessagesIncrementally(
      processor,
      messages,
      appliedCountRef.current
    );
    syncSurfaces();
  }, [messages, processor, syncSurfaces]);

  if (surfaces.length === 0) return null;

  return (
    <MarkdownContext.Provider value={markdownRenderer}>
      <div className="a2ui-host a2ui-surface a2ui-light">
        {surfaces.map((surface) => (
          <A2uiSurface key={surface.id} surface={surface} />
        ))}
      </div>
    </MarkdownContext.Provider>
  );
}
