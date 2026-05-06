import React, { useEffect, useRef, useState } from 'react';
import { Bot, Cpu, MessageSquare, Send, Sparkles, User } from 'lucide-react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'bot';
  timestamp: Date;
  model?: string;
  context?: string;
}

const API_BASE = 'http://localhost:8000';

interface Model {
  model_id: string;
  display_name: string;
}

interface ChatViewProps {
  selectedModel: string;
  models: Model[];
  selectedWikiId: string;
  selectedWikiName: string;
  onNavigate?: (page: string) => void;
  onNavigateSource?: (source: string) => void;
}

const ChatView: React.FC<ChatViewProps> = ({
  selectedModel,
  models,
  selectedWikiId,
  selectedWikiName,
  onNavigate,
  onNavigateSource,
}) => {
  const [input, setInput] = useState('');
  const [expandedContext, setExpandedContext] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const response = await axios.get(`${API_BASE}/chat/${selectedWikiId}`);
        const history = response.data.history;
        if (history && history.length > 0) {
          setMessages(history.map((msg: any) => ({
            id: msg.id,
            text: msg.text,
            sender: msg.sender,
            timestamp: new Date(msg.timestamp),
            model: msg.model,
            context: msg.context
          })));
        } else {
          setMessages([
            {
              id: `chat-${selectedWikiId}`,
              text: `You're chatting with "${selectedWikiName}". Retrieval is scoped to this wiki.`,
              sender: 'bot',
              timestamp: new Date(),
            },
          ]);
        }
      } catch (error) {
        console.error('Failed to load chat history:', error);
        setMessages([
          {
            id: `chat-${selectedWikiId}`,
            text: `You're chatting with "${selectedWikiName}". Retrieval is scoped to this wiki.`,
            sender: 'bot',
            timestamp: new Date(),
          },
        ]);
      }
    };

    void fetchHistory();
  }, [selectedWikiId, selectedWikiName]);

  const toggleContext = (id: string) => {
    setExpandedContext((previous) => ({ ...previous, [id]: !previous[id] }));
  };

  const getModelDisplayName = (modelId: string) =>
    models.find((model) => model.model_id === modelId)?.display_name || modelId;

  const handleSend = async (overrideInput?: string) => {
    const messageText = overrideInput || input;
    if (!messageText.trim()) {
      return;
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      text: messageText,
      sender: 'user',
      timestamp: new Date(),
    };

    setMessages((previous) => [...previous, userMessage]);
    setInput('');
    setIsTyping(true);

    try {
      const history = messages.filter(m => !m.id.startsWith('chat-')).map((message) => ({
        role: message.sender === 'user' ? 'user' : 'assistant',
        content: message.text,
      }));
      const modelToUse = selectedModel;
      const response = await axios.post(`${API_BASE}/chat`, {
        message: messageText,
        history,
        model: modelToUse,
        wiki_id: selectedWikiId,
      });

      setMessages((previous) => [
        ...previous,
        {
          id: `${Date.now() + 1}`,
          text: response.data.response,
          sender: 'bot',
          timestamp: new Date(),
          model: modelToUse,
          context: response.data.context,
        },
      ]);
    } catch (error) {
      console.error('Chat error:', error);
      setMessages((previous) => [
        ...previous,
        {
          id: `${Date.now() + 1}`,
          text: 'I hit an error while talking to the local model. Check that Ollama is running and the selected model is available.',
          sender: 'bot',
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const suggestions = [
    'What are the main concepts in this wiki?',
    'Summarize the most important pages.',
    'How do the key ideas relate to each other?',
    'What is still missing or contradictory?',
  ];

  return (
    <div className="h-full min-h-0">
      <section className="flex h-full min-h-0 flex-col rounded-none">
        {/* <div className="border-b border-white/10 px-6 py-5">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-white/35">
              <MessageSquare className="h-3.5 w-3.5" />
              <span>Knowledge Chat</span>
            </div>
            <h2 className="mt-2 text-2xl font-black text-white">{selectedWikiName}</h2>
            <p className="mt-1 max-w-2xl text-sm text-white/50">Ask questions against the whole selected wiki. Related answers stay scoped to this knowledge base only.</p>
          </div>
        </div> */}

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 custom-scrollbar">
          <div className="mb-8 flex flex-col items-center justify-center space-y-8 py-8 text-center">
            <div className="rounded-3xl bg-primary/10 p-4">
              <Sparkles className="h-12 w-12 animate-pulse text-primary" />
            </div>
            <div className="space-y-2">
              <h3 className="text-2xl font-bold text-white">Wiki Intelligence</h3>
              <p className="mx-auto max-w-lg text-white/40">Use Knowledge Chat to summarize pages, compare concepts, and ask questions about only the selected wiki.</p>
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary/70">Active Wiki: {selectedWikiName}</p>
            </div>
            <div className="grid w-full max-w-2xl gap-3 md:grid-cols-2">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => void handleSend(suggestion)}
                  className="rounded-2xl border border-white/5 bg-white/[0.03] p-4 text-left text-sm text-white/60 transition-all hover:border-primary/20 hover:bg-white/5 hover:text-white"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-6">
            {messages.map((message) => (
              <div key={message.id} className={`flex items-start gap-4 ${message.sender === 'user' ? 'flex-row-reverse' : ''}`}>
                <div
                  className={`flex h-10 w-10 flex-none items-center justify-center rounded-2xl ${message.sender === 'bot' ? 'bg-gradient-to-br from-primary to-blue-600 text-white' : 'bg-white/10 text-white/70'
                    }`}
                >
                  {message.sender === 'bot' ? <Bot className="h-5 w-5" /> : <User className="h-5 w-5" />}
                </div>

                <div className={`min-w-0 max-w-[82%] space-y-2 ${message.sender === 'user' ? 'items-end' : ''}`}>
                  <div
                    className={`rounded-2xl border p-4 shadow-xl ${message.sender === 'bot'
                      ? 'glass rounded-tl-none border-white/10 text-white/90'
                      : 'rounded-tr-none border-primary/20 bg-primary/20 text-white'
                      }`}
                  >
                    {message.sender === 'bot' ? (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h1: ({ node, ...props }: any) => <h1 className="mb-2 mt-4 text-xl font-bold text-white" {...props} />,
                          h2: ({ node, ...props }: any) => <h2 className="mb-2 mt-3 text-lg font-bold text-white" {...props} />,
                          h3: ({ node, ...props }: any) => <h3 className="mb-1 mt-2 text-base font-bold text-white" {...props} />,
                          p: ({ node, ...props }: any) => <p className="mb-2 whitespace-pre-wrap text-sm leading-relaxed text-white/90" {...props} />,
                          ul: ({ node, ...props }: any) => <ul className="mb-2 ml-4 list-disc space-y-1 text-sm text-white/90" {...props} />,
                          ol: ({ node, ...props }: any) => <ol className="mb-2 ml-4 list-decimal space-y-1 text-sm text-white/90" {...props} />,
                          strong: ({ node, ...props }: any) => <strong className="font-bold text-white" {...props} />,
                          em: ({ node, ...props }: any) => <em className="italic text-white/80" {...props} />,
                          code: ({ node, inline, ...props }: any) =>
                            inline ? (
                              <code className="rounded bg-black/30 px-1 py-0.5 font-mono text-xs text-emerald-400" {...props} />
                            ) : (
                              <code className="mb-2 block overflow-x-auto rounded-lg bg-black/50 p-3 font-mono text-xs text-emerald-400" {...props} />
                            ),
                          a: ({ node, href, children, ...props }: any) => {
                            if (href?.startsWith('wiki://')) {
                              const pageName = decodeURIComponent(href.replace('wiki://', ''));
                              return (
                                <button
                                  onClick={() => onNavigate && onNavigate(`${pageName}.md`)}
                                  className="cursor-pointer font-semibold text-primary underline decoration-primary/50 underline-offset-4 transition-colors hover:text-primary/80"
                                  title={`Navigate to ${pageName}`}
                                >
                                  {children}
                                </button>
                              );
                            }
                            if (href?.startsWith('source://')) {
                              const sourceName = decodeURIComponent(href.replace('source://', ''));
                              return (
                                <button
                                  onClick={() => onNavigateSource && onNavigateSource(sourceName.endsWith('.md') ? sourceName : `${sourceName}.md`)}
                                  className="cursor-pointer font-semibold text-sky-300 underline decoration-sky-300/50 underline-offset-4 transition-colors hover:text-sky-200"
                                  title={`Open ${sourceName}`}
                                >
                                  {children}
                                </button>
                              );
                            }
                            return (
                              <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-400 underline underline-offset-2 hover:text-blue-300" {...props}>
                                {children}
                              </a>
                            );
                          },
                        }}
                      >
                        {message.text}
                      </ReactMarkdown>
                    ) : (
                      <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.text}</p>
                    )}

                    <div className="mt-3 flex items-center justify-between gap-3">
                      <span className="block font-mono text-[10px] opacity-30">
                        {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                      {message.sender === 'bot' && message.model && (
                        <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-widest text-emerald-400/40">
                          <Cpu className="h-2.5 w-2.5" />
                          <span>{getModelDisplayName(message.model)}</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {message.sender === 'bot' && message.context && (
                    <div>
                      <button
                        onClick={() => toggleContext(message.id)}
                        className="ml-1 flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-white/30 transition-colors hover:text-primary"
                      >
                        <span>{expandedContext[message.id] ? '− Hide Context' : '+ View Context Sent to Model'}</span>
                      </button>
                      {expandedContext[message.id] && (
                        <div className="mt-2 max-h-60 overflow-x-auto overflow-y-auto rounded-xl border border-white/5 bg-black/40 p-4 font-mono text-[10px] whitespace-pre-wrap text-white/50 custom-scrollbar">
                          {message.context}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isTyping && (
              <div className="flex items-start gap-4 animate-pulse">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary/50">
                  <Bot className="h-6 w-6" />
                </div>
                <div className="glass rounded-2xl rounded-tl-none border-white/5 p-4">
                  <div className="flex space-x-1">
                    <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/40" />
                    <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/40 [animation-delay:0.2s]" />
                    <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/40 [animation-delay:0.4s]" />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="px-6 py-5">
          <div className="grid gap-3">
            <div className="relative rounded-[1.5rem] border border-white/10 bg-[#0a0c12] p-2 pl-5 shadow-2xl">
              <div className="flex items-center">
                <input
                  type="text"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={`Ask anything about ${selectedWikiName}...`}
                  className="flex-1 border-none bg-transparent py-3 text-sm text-white outline-none placeholder:text-white/20 focus:ring-0"
                />
                <button
                  onClick={() => void handleSend()}
                  disabled={!input.trim() || isTyping}
                  aria-label="Send message"
                  className={`ml-2 rounded-xl p-3 text-white transition-all ${input.trim() && !isTyping
                    ? 'bg-blue-600 shadow-lg shadow-blue-600/20 hover:scale-105 active:scale-95'
                    : 'bg-white/10 text-white/35'
                    }`}
                >
                  <Send className="h-5 w-5" />
                </button>
              </div>
            </div>
          </div>
          {/* <p className="mt-4 text-center text-[10px] font-bold uppercase tracking-[0.2em] text-white/20">
            <Sparkles className="mb-0.5 mr-1 inline-block h-3 w-3" />
            {selectedWikiName} • {getModelDisplayName(selectedModel)}
          </p> */}
        </div>
      </section>
    </div>
  );
};

export default ChatView;

