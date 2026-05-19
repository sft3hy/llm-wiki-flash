import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Bot, Cpu, FileText, MessageSquare, MoreHorizontal, Pencil, Plus, RefreshCw, Save, Send, Sparkles, Trash2, User, X } from 'lucide-react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const LATEX_UNICODE_MAP: [RegExp, string][] = [
  [/\$\\rightarrow\$/g, '→'],[/\$\\leftarrow\$/g, '←'],[/\$\\leftrightarrow\$/g, '↔'],
  [/\$\\Rightarrow\$/g, '⇒'],[/\$\\neq\$/g, '≠'],[/\$\\leq\$/g, '≤'],[/\$\\geq\$/g, '≥'],
  [/\$\\approx\$/g, '≈'],[/\$\\infty\$/g, '∞'],[/\$\\times\$/g, '×'],[/\$\\pm\$/g, '±'],
  [/\$\\alpha\$/g, 'α'],[/\$\\beta\$/g, 'β'],[/\$\\gamma\$/g, 'γ'],[/\$\\delta\$/g, 'δ'],
  [/\$\\pi\$/g, 'π'],[/\$\\sigma\$/g, 'σ'],[/\$\\theta\$/g, 'θ'],[/\$\\mu\$/g, 'μ'],[/\$\\lambda\$/g, 'λ'],
];
const latexToUnicode = (text: string): string => {
  let r = text; for (const [p, s] of LATEX_UNICODE_MAP) r = r.replace(p, s); return r;
};
const rewriteWikiLinks = (content: string) =>
  content.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_m, t: string, l?: string) => {
    const target = t.trim(); const label = (l || t).trim();
    return target.startsWith('sources/') ? `[${label}](source://${target.split('/')[1]})` : `[${label}](wiki://${target})`;
  });

const API_BASE = 'http://localhost:8000';

interface Conversation { id: string; wiki_id: string; title: string; created_at: string; updated_at: string; message_count: number; }
interface Message { id: string; text: string; sender: 'user' | 'bot'; timestamp: Date; model?: string; context?: string; citations?: Record<string, string>; retrieval_stats?: Record<string, number>; }
interface Model { model_id: string; display_name: string; }
interface ChatViewProps { selectedModel: string; models: Model[]; selectedWikiId: string; selectedWikiName: string; onNavigate?: (page: string) => void; onNavigateSource?: (source: string) => void; }

const ChatView: React.FC<ChatViewProps> = ({ selectedModel, models, selectedWikiId, selectedWikiName, onNavigate, onNavigateSource }) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [expandedContext, setExpandedContext] = useState<Record<string, boolean>>({});
  const [expandedCitations, setExpandedCitations] = useState<Record<string, boolean>>({});
  const [editingConvId, setEditingConvId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [menuConvId, setMenuConvId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, isTyping]);

  const loadConversations = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/chats`, { params: { wiki_id: selectedWikiId } });
      setConversations(res.data.conversations || []);
    } catch { setConversations([]); }
  }, [selectedWikiId]);

  useEffect(() => { setActiveConvId(null); setMessages([]); void loadConversations(); }, [selectedWikiId, loadConversations]);

  useEffect(() => {
    if (!activeConvId) { setMessages([]); return; }
    const load = async () => {
      try {
        const res = await axios.get(`${API_BASE}/api/chats/${activeConvId}/messages`);
        setMessages((res.data.messages || []).map((m: any) => ({
          id: m.id, text: m.text, sender: m.sender, timestamp: new Date(m.timestamp),
          model: m.model, context: m.context, citations: m.citations, retrieval_stats: m.retrieval_stats,
        })));
      } catch { setMessages([]); }
    };
    void load();
  }, [activeConvId]);

  const createConversation = async () => {
    try {
      const res = await axios.post(`${API_BASE}/api/chats`, { wiki_id: selectedWikiId });
      await loadConversations();
      setActiveConvId(res.data.id);
    } catch (e) { console.error('Failed to create conversation:', e); }
  };

  const deleteConversation = async (id: string) => {
    try {
      await axios.delete(`${API_BASE}/api/chats/${id}`);
      if (activeConvId === id) { setActiveConvId(null); setMessages([]); }
      await loadConversations();
    } catch (e) { console.error('Delete failed:', e); }
  };

  const renameConversation = async (id: string, title: string) => {
    if (!title.trim()) return;
    try {
      await axios.patch(`${API_BASE}/api/chats/${id}`, { title: title.trim() });
      setEditingConvId(null);
      await loadConversations();
    } catch (e) { console.error('Rename failed:', e); }
  };

  const handleSend = async (overrideInput?: string) => {
    const text = overrideInput || input;
    if (!text.trim()) return;

    let convId = activeConvId;
    if (!convId) {
      try {
        const res = await axios.post(`${API_BASE}/api/chats`, { wiki_id: selectedWikiId });
        convId = res.data.id;
        setActiveConvId(convId);
        await loadConversations();
      } catch { return; }
    }

    const userMsg: Message = { id: Date.now().toString(), text, sender: 'user', timestamp: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    try {
      const res = await axios.post(`${API_BASE}/api/chats/${convId}/messages`, { message: text, model: selectedModel });
      setMessages(prev => [...prev, {
        id: res.data.bot_message_id, text: res.data.response, sender: 'bot', timestamp: new Date(),
        model: selectedModel, context: res.data.context, citations: res.data.citation_map, retrieval_stats: res.data.retrieval_stats,
      }]);
      await loadConversations();
    } catch {
      setMessages(prev => [...prev, { id: `${Date.now()}`, text: 'Error talking to the model. Check Ollama.', sender: 'bot', timestamp: new Date() }]);
    } finally { setIsTyping(false); }
  };

  const handleRegenerate = async () => {
    if (!activeConvId) return;
    setIsTyping(true);
    try {
      const res = await axios.post(`${API_BASE}/api/chats/${activeConvId}/regenerate`, null, { params: { model: selectedModel } });
      // Remove last 2 messages (user + bot) and add new ones
      setMessages(prev => {
        const trimmed = prev.slice(0, -2);
        return [...trimmed,
          { id: res.data.user_message_id, text: res.data.response ? prev[prev.length - 2]?.text || '' : '', sender: 'user' as const, timestamp: new Date() },
          { id: res.data.bot_message_id, text: res.data.response, sender: 'bot' as const, timestamp: new Date(), model: selectedModel, context: res.data.context, citations: res.data.citation_map, retrieval_stats: res.data.retrieval_stats },
        ];
      });
    } catch { /* keep existing messages */ }
    finally { setIsTyping(false); }
  };

  const handleSaveToWiki = async () => {
    if (!activeConvId) return;
    try {
      await axios.post(`${API_BASE}/api/chats/${activeConvId}/save-to-wiki`);
      alert('Conversation saved to wiki!');
    } catch { alert('Failed to save.'); }
  };

  const getModelName = (id: string) => models.find(m => m.model_id === id)?.display_name || id;
  const suggestions = ['What are the main concepts in this wiki?', 'Summarize the most important pages.', 'How do the key ideas relate to each other?', 'What is still missing or contradictory?'];
  const lastBotIdx = messages.map((m, i) => m.sender === 'bot' ? i : -1).filter(i => i >= 0).pop();

  return (
    <div className="flex h-full min-h-0 gap-0">
      {/* Conversation Sidebar */}
      <div className="flex w-64 flex-none flex-col border-r border-white/5 bg-[#0a0c12]/60">
        <div className="flex items-center justify-between p-4">
          <span className="text-xs font-bold uppercase tracking-[0.18em] text-white/35">Conversations</span>
          <button onClick={() => void createConversation()} className="rounded-lg bg-white/5 p-1.5 text-white/60 transition hover:bg-white/10 hover:text-white" title="New conversation">
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2 custom-scrollbar">
          {conversations.length === 0 && <p className="px-3 py-6 text-center text-xs text-white/25">No conversations yet</p>}
          {conversations.map(c => (
            <div key={c.id}
              className={`group relative mb-1 flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 transition ${activeConvId === c.id ? 'bg-white/10 text-white' : 'text-white/50 hover:bg-white/5 hover:text-white/80'}`}
              onClick={() => { setActiveConvId(c.id); setMenuConvId(null); }}
              onDoubleClick={() => { setEditingConvId(c.id); setEditTitle(c.title); }}>
              <MessageSquare className="h-3.5 w-3.5 flex-none opacity-50" />
              {editingConvId === c.id ? (
                <input autoFocus value={editTitle} onChange={e => setEditTitle(e.target.value)}
                  onBlur={() => void renameConversation(c.id, editTitle)}
                  onKeyDown={e => { if (e.key === 'Enter') void renameConversation(c.id, editTitle); if (e.key === 'Escape') setEditingConvId(null); }}
                  onClick={e => e.stopPropagation()}
                  className="min-w-0 flex-1 rounded border border-primary/30 bg-transparent px-1 py-0.5 text-xs text-white outline-none" />
              ) : (
                <span className="min-w-0 flex-1 truncate text-xs font-medium">{c.title}</span>
              )}
              <div className="flex-none opacity-0 group-hover:opacity-100 transition">
                <button onClick={e => { e.stopPropagation(); setMenuConvId(menuConvId === c.id ? null : c.id); }}
                  className="rounded p-1 text-white/40 hover:text-white"><MoreHorizontal className="h-3.5 w-3.5" /></button>
              </div>
              {menuConvId === c.id && (
                <div className="absolute right-0 top-full z-20 mt-1 w-36 rounded-xl border border-white/10 bg-[#0a0c12] p-1 shadow-2xl" onClick={e => e.stopPropagation()}>
                  <button onClick={() => { setEditingConvId(c.id); setEditTitle(c.title); setMenuConvId(null); }}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-white/70 hover:bg-white/5"><Pencil className="h-3 w-3" />Rename</button>
                  <button onClick={() => void handleSaveToWiki()} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-white/70 hover:bg-white/5"><Save className="h-3 w-3" />Save to Wiki</button>
                  <button onClick={() => { void deleteConversation(c.id); setMenuConvId(null); }}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-red-300/70 hover:bg-red-500/10"><Trash2 className="h-3 w-3" />Delete</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 custom-scrollbar">
          {!activeConvId || messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center space-y-8 py-8 text-center">
              <div className="rounded-3xl bg-primary/10 p-4"><Sparkles className="h-12 w-12 animate-pulse text-primary" /></div>
              <div className="space-y-2">
                <h3 className="text-2xl font-bold text-white">Wiki Intelligence</h3>
                <p className="mx-auto max-w-lg text-white/40">
                  {activeConvId 
                    ? `Ask questions scoped to "${selectedWikiName}". Your research is isolated and persistent.`
                    : "Create or select a conversation to start chatting with your wiki."
                  }
                </p>
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary/70">Active Wiki: {selectedWikiName}</p>
              </div>
              
              {!activeConvId && (
                <button onClick={() => void createConversation()} className="rounded-2xl border border-primary/30 bg-primary/10 px-6 py-3 text-sm font-semibold text-primary transition hover:bg-primary/20">
                  <Plus className="mr-2 inline h-4 w-4" />New Conversation
                </button>
              )}

              <div className="grid w-full max-w-2xl gap-3 md:grid-cols-2">
                {suggestions.map(s => (
                  <button key={s} onClick={() => void handleSend(s)}
                    className="rounded-2xl border border-white/5 bg-white/[0.03] p-4 text-left text-sm text-white/60 transition-all hover:border-primary/20 hover:bg-white/5 hover:text-white">{s}</button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((message, idx) => (
                <div key={message.id} className={`flex items-start gap-4 ${message.sender === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`flex h-10 w-10 flex-none items-center justify-center rounded-2xl ${message.sender === 'bot' ? 'bg-gradient-to-br from-primary to-blue-600 text-white' : 'bg-white/10 text-white/70'}`}>
                    {message.sender === 'bot' ? <Bot className="h-5 w-5" /> : <User className="h-5 w-5" />}
                  </div>
                  <div className={`min-w-0 max-w-[82%] space-y-2 ${message.sender === 'user' ? 'items-end' : ''}`}>
                    <div className={`rounded-2xl border p-4 shadow-xl ${message.sender === 'bot' ? 'glass rounded-tl-none border-white/10 text-white/90' : 'rounded-tr-none border-primary/20 bg-primary/20 text-white'}`}>
                      {message.sender === 'bot' ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={(v: string) => v}
                          components={{
                            h1: ({ node, ...p }: any) => <h1 className="mb-2 mt-4 text-xl font-bold text-white" {...p} />,
                            h2: ({ node, ...p }: any) => <h2 className="mb-2 mt-3 text-lg font-bold text-white" {...p} />,
                            h3: ({ node, ...p }: any) => <h3 className="mb-1 mt-2 text-base font-bold text-white" {...p} />,
                            p: ({ node, ...p }: any) => <p className="mb-2 whitespace-pre-wrap text-sm leading-relaxed text-white/90" {...p} />,
                            ul: ({ node, ...p }: any) => <ul className="mb-2 ml-4 list-disc space-y-1 text-sm text-white/90" {...p} />,
                            ol: ({ node, ...p }: any) => <ol className="mb-2 ml-4 list-decimal space-y-1 text-sm text-white/90" {...p} />,
                            strong: ({ node, ...p }: any) => <strong className="font-bold text-white" {...p} />,
                            em: ({ node, ...p }: any) => <em className="italic text-white/80" {...p} />,
                            code: ({ node, inline, ...p }: any) => inline
                              ? <code className="rounded bg-black/30 px-1 py-0.5 font-mono text-xs text-emerald-400" {...p} />
                              : <code className="mb-2 block overflow-x-auto rounded-lg bg-black/50 p-3 font-mono text-xs text-emerald-400" {...p} />,
                            a: ({ node, href, children, ...p }: any) => {
                              if (href?.startsWith('wiki://')) { const pg = decodeURIComponent(href.replace('wiki://', '')); return <button onClick={() => onNavigate?.(`${pg}.md`)} className="cursor-pointer font-semibold text-primary underline decoration-primary/50 underline-offset-4 transition-colors hover:text-primary/80">{children}</button>; }
                              if (href?.startsWith('source://')) { const s = decodeURIComponent(href.replace('source://', '')); return <button onClick={() => onNavigateSource?.(s.endsWith('.md') ? s : `${s}.md`)} className="cursor-pointer font-semibold text-sky-300 underline decoration-sky-300/50 underline-offset-4 transition-colors hover:text-sky-200">{children}</button>; }
                              if (href && !href.startsWith('http') && !href.startsWith('#') && !href.startsWith('mailto:')) { return <button onClick={() => onNavigate?.(href.endsWith('.md') ? href : `${href}.md`)} className="cursor-pointer font-semibold text-primary underline decoration-primary/50 underline-offset-4">{children}</button>; }
                              return <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-400 underline underline-offset-2 hover:text-blue-300" {...p}>{children}</a>;
                            },
                          }}>{rewriteWikiLinks(latexToUnicode(message.text))}</ReactMarkdown>
                      ) : (<p className="whitespace-pre-wrap text-sm leading-relaxed">{message.text}</p>)}
                      <div className="mt-3 flex items-center justify-between gap-3">
                        <span className="block font-mono text-[10px] opacity-30">{message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        {message.sender === 'bot' && message.model && (
                          <span className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-widest text-emerald-400/40"><Cpu className="h-2.5 w-2.5" /><span>{getModelName(message.model)}</span></span>
                        )}
                      </div>
                    </div>
                    {/* Actions row for bot messages */}
                    {message.sender === 'bot' && (
                      <div className="flex flex-wrap items-center gap-2 ml-1">
                        {message.context && (
                          <button onClick={() => setExpandedContext(p => ({ ...p, [message.id]: !p[message.id] }))}
                            className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-white/30 transition-colors hover:text-primary">
                            {expandedContext[message.id] ? '− Hide Context' : '+ Context'}
                          </button>
                        )}
                        {message.citations && Object.keys(message.citations).length > 0 && (
                          <button onClick={() => setExpandedCitations(p => ({ ...p, [message.id]: !p[message.id] }))}
                            className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-white/30 transition-colors hover:text-sky-400">
                            <FileText className="h-2.5 w-2.5" />{expandedCitations[message.id] ? '− Hide' : `${Object.keys(message.citations).length} Sources`}
                          </button>
                        )}
                        {idx === lastBotIdx && !isTyping && (
                          <button onClick={() => void handleRegenerate()}
                            className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-white/30 transition-colors hover:text-amber-400">
                            <RefreshCw className="h-2.5 w-2.5" />Regenerate
                          </button>
                        )}
                      </div>
                    )}
                    {/* Expanded context */}
                    {message.sender === 'bot' && expandedContext[message.id] && message.context && (
                      <div className="mt-1 max-h-60 overflow-auto rounded-xl border border-white/5 bg-black/40 p-4 font-mono text-[10px] whitespace-pre-wrap text-white/50 custom-scrollbar">{message.context}</div>
                    )}
                    {/* Expanded citations */}
                    {message.sender === 'bot' && expandedCitations[message.id] && message.citations && (
                      <div className="mt-1 rounded-xl border border-white/5 bg-black/30 p-3 space-y-1">
                        <p className="text-[9px] font-bold uppercase tracking-widest text-white/30 mb-2">Referenced Sources</p>
                        {Object.entries(message.citations).map(([num, path]) => {
                          const display = String(path).split('/').slice(-2).join('/');
                          return (
                            <button key={num} onClick={() => onNavigate?.(`${display.replace(/\.md$/, '')}.md`)}
                              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs text-sky-300/80 transition hover:bg-white/5">
                              <span className="flex-none rounded bg-white/10 px-1.5 py-0.5 font-mono text-[9px] text-white/50">[{num}]</span>
                              <span className="truncate">{display}</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {isTyping && (
                <div className="flex items-start gap-4 animate-pulse">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary/50"><Bot className="h-6 w-6" /></div>
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
          )}
        </div>
        <div className="px-6 py-5">
          <div className="relative rounded-[1.5rem] border border-white/10 bg-[#0a0c12] p-2 pl-5 shadow-2xl">
            <div className="flex items-center">
              <input type="text" value={input} onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSend(); } }}
                placeholder={`Ask anything about ${selectedWikiName}...`}
                className="flex-1 border-none bg-transparent py-3 text-sm text-white outline-none placeholder:text-white/20 focus:ring-0" />
              <button onClick={() => void handleSend()} disabled={!input.trim() || isTyping} aria-label="Send message"
                className={`ml-2 rounded-xl p-3 text-white transition-all ${input.trim() && !isTyping ? 'bg-blue-600 shadow-lg shadow-blue-600/20 hover:scale-105 active:scale-95' : 'bg-white/10 text-white/35'}`}>
                <Send className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatView;
