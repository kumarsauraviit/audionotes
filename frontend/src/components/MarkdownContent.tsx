import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  h1: ({ node: _node, ...props }) => <h2 className="mt-2 text-lg font-semibold" {...props} />,
  h2: ({ node: _node, ...props }) => <h3 className="mt-2 text-base font-semibold" {...props} />,
  h3: ({ node: _node, ...props }) => <h4 className="mt-1 text-sm font-semibold" {...props} />,
  p: ({ node: _node, ...props }) => <p className="leading-relaxed" {...props} />,
  ul: ({ node: _node, ...props }) => <ul className="ml-4 list-disc space-y-1" {...props} />,
  ol: ({ node: _node, ...props }) => <ol className="ml-4 list-decimal space-y-1" {...props} />,
  li: ({ node: _node, ...props }) => <li className="pl-1" {...props} />,
  a: ({ node: _node, ...props }) => (
    <a className="text-primary underline underline-offset-4" target="_blank" rel="noreferrer" {...props} />
  ),
  strong: ({ node: _node, ...props }) => <strong className="font-semibold" {...props} />,
  blockquote: ({ node: _node, ...props }) => (
    <blockquote className="border-l-2 border-line pl-3 text-muted-foreground" {...props} />
  ),
  code: ({ node: _node, ...props }) => (
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]" {...props} />
  ),
  pre: ({ node: _node, ...props }) => (
    <pre
      className="overflow-auto rounded-md bg-ink p-3 text-xs text-paper [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-paper"
      {...props}
    />
  ),
  hr: () => <hr className="border-line" />,
  table: ({ node: _node, ...props }) => (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-sm" {...props} />
    </div>
  ),
  th: ({ node: _node, ...props }) => (
    <th className="border-b border-line px-2 py-1 text-left font-semibold" {...props} />
  ),
  td: ({ node: _node, ...props }) => <td className="border-b border-line/60 px-2 py-1" {...props} />,
};

export function MarkdownContent({ source }: { source: string }) {
  return (
    <div className="flex flex-col gap-3 text-sm leading-relaxed text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {source}
      </ReactMarkdown>
    </div>
  );
}
