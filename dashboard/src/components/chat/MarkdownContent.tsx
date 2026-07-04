import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type { PluggableList } from "unified";
import "highlight.js/styles/github.min.css";

type Props = {
  content: string;
  className?: string;
  allowHtml?: boolean;
};

const markdownComponents: Components = {
  table: ({ children, ...props }) => (
    <div className="table-scroll">
      <table {...props}>{children}</table>
    </div>
  ),
};

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames || []),
    "div",
    "span",
    "p",
    "br",
    "strong",
    "em",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "img",
    "a",
    "code",
    "pre",
  ],
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a || []), "href", "title", "target", "rel"],
    img: ["src", "alt", "title", "width", "height"],
    td: [...(defaultSchema.attributes?.td || []), "colSpan", "rowSpan"],
    th: [...(defaultSchema.attributes?.th || []), "colSpan", "rowSpan"],
  },
  protocols: {
    ...defaultSchema.protocols,
    href: ["http", "https", "mailto", "xmpp", "tel"],
    src: ["http", "https"],
  },
};

export default function MarkdownContent({
  content,
  className = "message-bubble",
  allowHtml = false,
}: Props) {
  const rehypePlugins: PluggableList = allowHtml
    ? [rehypeRaw, [rehypeSanitize, sanitizeSchema], rehypeHighlight]
    : [rehypeHighlight];

  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={rehypePlugins}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
