import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function MarkdownRenderer({ content }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // Keep links from capturing the chat scroll; open in a new tab.
        a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export default function MessageBubble({ role, title, text, sources = [], status }) {
  if (role === 'user') {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[78%] rounded-2xl px-4 py-3
            bg-[rgba(255,255,255,0.06)]
            border border-[rgba(255,255,255,0.08)]"
        >
          <p className="text-base text-white leading-relaxed m-0 whitespace-pre-line">
            {text}
          </p>
        </div>
      </div>
    );
  }

  const isStreamingEmpty = status === 'streaming' && !text;

  return (
    <div
      className="rounded-2xl p-4"
    >
      {isStreamingEmpty ? (
        <span className="inline-flex items-center gap-0.5 text-[#a6abb3]">
          <span className="animate-pulse duration-1000">Thinking</span>
          <span className="animate-pulse duration-1000 delay-150">.</span>
          <span className="animate-pulse duration-1000 delay-300">.</span>
          <span className="animate-pulse duration-1000 delay-450">.</span>
        </span>
      ) : (
        <div className="font-sans text-base leading-relaxed text-white markdown-body">
          <MarkdownRenderer content={text || ''} />
        </div>
      )}
      {sources.length > 0 ? (
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="text-[10px] text-[#a6abb3]">Sources</span>
          <div className="flex gap-1.5 flex-wrap">
            {sources.map((source) => (
              <span
                key={source}
                className="px-2 py-0.5 rounded-full text-[10px] font-mono
                  border border-[rgba(122,162,247,0.3)] text-[#d3e3ff]"
              >
                {source}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
