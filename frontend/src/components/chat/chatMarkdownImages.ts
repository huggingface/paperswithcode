/**
 * Never load images from model output. An <img> fetches its URL without a
 * click, so text injected through papers, web results or uploads could make
 * the model write an image whose query string leaks the conversation.
 *
 * This rehype plugin rewrites every image before rendering: outside a link it
 * becomes a link to the image URL (rendered by the normal link handler), and
 * inside a link it becomes its alt text, so anchors are never nested.
 */

interface HastNode {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
  value?: string;
}

function imageLabel(node: HastNode): string {
  const alt = node.properties?.alt;
  return (typeof alt === "string" && alt.trim()) || "Image";
}

function rewrite(node: HastNode, insideLink: boolean): void {
  if (!node.children) return;
  node.children = node.children.map((child) => {
    if (child.type !== "element") return child;
    if (child.tagName === "img") {
      const text: HastNode = { type: "text", value: imageLabel(child) };
      const src = child.properties?.src;
      if (insideLink || typeof src !== "string" || !src) return text;
      return { type: "element", tagName: "a", properties: { href: src }, children: [text] };
    }
    rewrite(child, insideLink || child.tagName === "a");
    return child;
  });
}

export function rehypeImagesAsLinks() {
  return (tree: HastNode) => rewrite(tree, false);
}
