import { useLayoutEffect, useState } from "react";

/** Keep standalone chat inside the visible viewport, including the mobile keyboard. */
export function useChatViewportHeight(enabled: boolean): string {
  const [height, setHeight] = useState("calc(100dvh - 60px)");

  useLayoutEffect(() => {
    if (!enabled) return;
    const header = document.querySelector<HTMLElement>(".app-header");
    const viewport = window.visualViewport;
    const update = () => {
      const visibleHeight = viewport?.height ?? window.innerHeight;
      setHeight(`${Math.max(0, visibleHeight - (header?.offsetHeight ?? 0))}px`);
    };
    update();
    const observer = new ResizeObserver(update);
    if (header) observer.observe(header);
    viewport?.addEventListener("resize", update);
    window.addEventListener("resize", update);
    return () => {
      observer.disconnect();
      viewport?.removeEventListener("resize", update);
      window.removeEventListener("resize", update);
    };
  }, [enabled]);

  return enabled ? height : "100%";
}
