import { useCallback, useMemo, useRef, useState } from 'react';

import { queryAnswer, streamQuery } from '../services/api';

const SUGGESTIONS = [
  'Explain positional encoding',
  'How does self-attention work?',
  'Show code example in PyTorch',
];

const DEFAULT_CONFIDENCE = {
  answer_confidence: 0,
  source_coverage: 'Weak',
  sources_used: 0,
  retrieved_chunks: 0,
};

export function useChat() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState('');
  const [sources, setSources] = useState([]);
  const [latency, setLatency] = useState({});
  // FIX: store server-side confidence metrics
  const [confidence, setConfidence] = useState(null);
  const [showUploadHint, setShowUploadHint] = useState(false);
  const abortRef = useRef(null);
  const lastQuestionRef = useRef('');

  const suggestions = useMemo(() => SUGGESTIONS, []);

  const appendMessage = useCallback((message) => {
    setMessages((prev) => [...prev, message]);
  }, []);

  const updateAssistant = useCallback((id, patch) => {
    setMessages((prev) =>
      prev.map((message) => (message.id === id ? { ...message, ...patch } : message)),
    );
  }, []);

  const stopStream = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, []);

  const sendMessage = useCallback(
    async (question) => {
      const trimmed = question.trim();
      if (!trimmed) {
        return;
      }

      lastQuestionRef.current = trimmed;
      setError('');
      setSources([]);
      setLatency({});
      // FIX: reset confidence on new query
      setConfidence(null);
      setShowUploadHint(false);
      setInput('');

      const userId = `user-${Date.now()}`;
      const assistantId = `assistant-${Date.now()}`;

      appendMessage({
        id: userId,
        role: 'user',
        text: trimmed,
      });

      appendMessage({
        id: assistantId,
        role: 'assistant',
        text: '',
        status: 'streaming',
      });

      setIsStreaming(true);
      stopStream();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        let hasTokens = false;
        await streamQuery(
          { question: trimmed },
          {
            signal: controller.signal,
            onToken: (token) => {
              hasTokens = true;
              setMessages((prev) =>
                prev.map((message) =>
                  message.id === assistantId
                    ? { ...message, text: message.text + token }
                    : message,
                ),
              );
            },
            onSources: (nextSources) => {
              const normalized = nextSources || [];
              setSources(normalized);
              const tagList = normalized.map((item) => item.chunk_id);
              updateAssistant(assistantId, { sources: tagList });
              setShowUploadHint(normalized.length === 0);
            },
            onLatency: (timings) => {
              setLatency(timings || {});
            },
            // FIX: store confidence from the SSE [CONFIDENCE] event
            onConfidence: (data) => {
              setConfidence(data || DEFAULT_CONFIDENCE);
            },
            onDone: () => {
              updateAssistant(assistantId, { status: 'done' });
            },
            onError: (message) => {
              throw new Error(message);
            },
          },
        );

        if (!hasTokens) {
          throw new Error('No response received from the server.');
        }
      } catch (streamError) {
        stopStream();
        try {
          const fallback = await queryAnswer({ question: trimmed });
          updateAssistant(assistantId, {
            text: fallback.answer,
            status: 'done',
            sources: (fallback.sources || []).map((item) => item.chunk_id),
          });
          setSources(fallback.sources || []);
          setShowUploadHint((fallback.sources || []).length === 0);
          setLatency(fallback.latency_ms || {});
          // FIX: parse confidence from fallback response
          setConfidence(fallback.confidence || DEFAULT_CONFIDENCE);
        } catch (fallbackError) {
          updateAssistant(assistantId, { status: 'error' });
          setError(fallbackError.message || 'Request failed');
        }
      } finally {
        setIsStreaming(false);
      }
    },
    [appendMessage, stopStream, updateAssistant],
  );

  const retryLast = useCallback(() => {
    if (lastQuestionRef.current) {
      sendMessage(lastQuestionRef.current);
    }
  }, [sendMessage]);

  return {
    input,
    setInput,
    messages,
    sendMessage,
    isStreaming,
    error,
    setError,
    sources,
    latency,
    // FIX: expose confidence so SourceViewer can consume it
    confidence,
    suggestions,
    retryLast,
    stopStream,
    showUploadHint,
  };
}
