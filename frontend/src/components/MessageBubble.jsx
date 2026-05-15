export default function MessageBubble({ role, title, text, sources = [], status }) {
  if (role === 'user') {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[78%] rounded-2xl px-4 py-3
            bg-[rgba(255,255,255,0.06)]
            border border-[rgba(255,255,255,0.08)]"
        >
          <p className="text-sm text-[#e6e7ea] leading-relaxed m-0 whitespace-pre-line">
            {text}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="rounded-2xl p-4
        bg-gradient-to-br from-[rgba(122,162,247,0.12)] to-[rgba(122,162,247,0.04)]
        border border-[rgba(122,162,247,0.2)]"
    >
      <div className="flex items-center gap-3 mb-2.5">
        <div
          className="w-8 h-8 rounded-full shrink-0 overflow-hidden
            bg-[#0b0f1a]
            shadow-[0_0_14px_rgba(122,162,247,0.35)]"
        >
          <img src="/logos/project_logo.png" alt="ContextForge" className="w-full h-full object-contain" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-white brand-title">
            Context<span className="brand-title-accent">Forge</span>
          </div>
          <div className="text-[10px] text-[#a6abb3]">
            {status === 'streaming' ? 'Streaming reply' : 'RAG response'}
          </div>
        </div>
      </div>
      <p className="text-sm text-[#e6e7ea] leading-relaxed m-0 mb-3 whitespace-pre-line">
        {text || (status === 'streaming' ? (
          <span className="inline-flex items-center gap-0.5 text-[#a6abb3]">
            <span className="animate-pulse duration-1000">Thinking</span>
            <span className="animate-pulse duration-1000 delay-150">.</span>
            <span className="animate-pulse duration-1000 delay-300">.</span>
            <span className="animate-pulse duration-1000 delay-450">.</span>
          </span>
        ) : '')}
      </p>
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
