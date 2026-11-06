import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/** GFM rendering tweaks shared by every AI-generated surface: links open in
 * a new tab without leaking app context. `node` is stripped so it never
 * reaches the DOM anchor. */
const markdownComponents: Components = {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  a: ({ node: _node, ...props }) => (
    <a target="_blank" rel="noopener noreferrer" {...props} />
  ),
};

/**
 * Renders AI-generated text as GitHub-flavored Markdown (lists, tables,
 * code). Prose spacing is clamped so the output reads cleanly inside cards
 * and bubbles. Shared by chat bubbles and the AI-tools report views.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_p]:my-1.5 [&_ul]:my-1.5 [&_ol]:my-1.5 [&_li]:my-0.5 [&_table]:my-2 [&_pre]:my-2">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={markdownComponents}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
