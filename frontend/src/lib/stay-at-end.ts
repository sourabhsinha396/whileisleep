/** This close to the end counts as being there. */
const NEAR_PX = 80;

export function isAtEnd(box: HTMLElement): boolean {
  return box.scrollHeight - box.scrollTop - box.clientHeight < NEAR_PX;
}

/** Keeps the newest message in view when the list gets shorter, because the box to write in
 * grew. Someone reading further up stays there. Returns what stops it. */
export function stayAtEnd(box: HTMLElement | null): () => void {
  if (!box || typeof ResizeObserver === "undefined") return () => {};
  let atEnd = true;
  const onScroll = () => (atEnd = isAtEnd(box));
  const observer = new ResizeObserver(() => {
    if (atEnd) box.scrollTop = box.scrollHeight;
  });
  box.addEventListener("scroll", onScroll, { passive: true });
  observer.observe(box);
  return () => {
    box.removeEventListener("scroll", onScroll);
    observer.disconnect();
  };
}
