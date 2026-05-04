import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Sparkles, Cpu, Cloud } from 'lucide-react';
import axios from 'axios';

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'bot';
  timestamp: Date;
  model?: string;
  context?: string;
}

const API_BASE = "http://localhost:8000";

interface ChatViewProps {
  selectedModel: string;
}

const ChatView: React.FC<ChatViewProps> = ({ selectedModel }) => {
  const [input, setInput] = useState('');
  const [expandedContext, setExpandedContext] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      text: "Hello! I'm your Wiki Assistant. I've indexed all your knowledge. What would you like to know today?",
      sender: 'bot',
      timestamp: new Date(),
    }
  ]);
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const toggleContext = (id: string) => {
    setExpandedContext(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const getModelDisplayName = (modelId: string) => {
    const names: Record<string, string> = {
      'auto-smart': 'Smart (Auto Tiering)',
      'llama3.2:1b': 'Llama 3.2 (Fast)',
      'gemma4:e4b': 'Gemma 4 Medium',
      'llama-3.3-70b-versatile': 'Llama 3.3 70B',
      'openai/gpt-oss-120b': 'GPT-OSS 120B',
      'meta-llama/llama-4-scout-17b-16e-instruct': 'Llama 4 Scout',
    };
    return names[modelId] || modelId;
  };

  const isLocalModel = (modelId: string) => modelId.includes('gemma') || modelId.includes('llama3.2');

  const handleSend = async (overrideInput?: string) => {
    const messageText = overrideInput || input;
    if (!messageText.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      text: messageText,
      sender: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);

    try {
      const history = messages.slice(1).map(msg => ({
        role: msg.sender === 'user' ? 'user' : 'assistant',
        content: msg.text
      }));

      const response = await axios.post(`${API_BASE}/chat`, {
        message: messageText,
        history: history,
        model: selectedModel,
      });

      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: response.data.response,
        sender: 'bot',
        timestamp: new Date(),
        model: selectedModel,
        context: response.data.context,
      };
      setMessages(prev => [...prev, botMessage]);
    } catch (error) {
      console.error("Chat error:", error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: "I'm sorry, I encountered an error while trying to connect to the intelligence engine. Please ensure the model provider is available.",
        sender: 'bot',
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const suggestions = [
    "What are the main concepts in my wiki?",
    "Summarize my recent additions",
    "How do these topics relate to each other?",
    "Identify any contradictions in my knowledge base"
  ];

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto animate-in fade-in duration-500">
      <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
        {messages.length === 1 && (
          <div className="flex flex-col items-center justify-center h-full space-y-8 py-12">
            <div className="p-4 bg-primary/10 rounded-3xl">
              <Sparkles className="w-12 h-12 text-primary animate-pulse" />
            </div>
            <div className="text-center space-y-2">
              <h3 className="text-2xl font-bold text-white">Wiki Intelligence</h3>
              <p className="text-white/40 max-w-sm">Ask me anything about your compiled knowledge. I can synthesize, summarize, and explore connections.</p>
            </div>
            <div className="grid grid-cols-2 gap-3 w-full max-w-xl">
              {suggestions.map((s, i) => (
                <button 
                  key={i} 
                  onClick={() => handleSend(s)}
                  className="p-4 bg-white/[0.03] border border-white/5 rounded-2xl text-left text-xs text-white/60 hover:bg-white/5 hover:text-white transition-all hover:border-primary/20"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <div 
            key={msg.id} 
            className={`flex items-start space-x-4 ${msg.sender === 'user' ? 'flex-row-reverse space-x-reverse' : ''} animate-in slide-in-from-bottom-2 duration-300`}
          >
            <div className={`w-10 h-10 rounded-2xl flex items-center justify-center shadow-lg ${
              msg.sender === 'bot' 
              ? 'bg-gradient-to-br from-primary to-blue-600 text-white' 
              : 'bg-white/10 text-white/70'
            }`}>
              {msg.sender === 'bot' ? <Bot className="w-6 h-6" /> : <User className="w-6 h-6" />}
            </div>
            <div className="flex-1 max-w-[80%] space-y-2">
              <div className={`p-4 rounded-2xl shadow-xl border ${
                msg.sender === 'bot' 
                ? 'glass rounded-tl-none border-white/10 text-white/90' 
                : 'bg-primary/20 border-primary/20 rounded-tr-none text-white'
              }`}>
                <p className="text-sm leading-relaxed whitespace-pre-wrap">
                  {msg.text}
                </p>
                <div className="flex items-center justify-between mt-2">
                  <span className="text-[10px] opacity-30 block font-mono">
                    {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  {msg.sender === 'bot' && msg.model && (
                    <span className={`text-[9px] font-bold uppercase tracking-widest flex items-center space-x-1 ${
                      isLocalModel(msg.model) ? 'text-emerald-400/40' : 'text-violet-400/40'
                    }`}>
                      {isLocalModel(msg.model) ? <Cpu className="w-2.5 h-2.5" /> : <Cloud className="w-2.5 h-2.5" />}
                      <span>{getModelDisplayName(msg.model)}</span>
                    </span>
                  )}
                </div>
              </div>
              
              {msg.sender === 'bot' && msg.context && (
                <div className="animate-in fade-in slide-in-from-top-1 duration-500">
                  <button 
                    onClick={() => toggleContext(msg.id)}
                    className="text-[10px] font-bold uppercase tracking-widest text-white/30 hover:text-primary transition-colors flex items-center space-x-1 ml-1"
                  >
                    <span>{expandedContext[msg.id] ? '− Hide Context' : '+ View Context Sent to Model'}</span>
                  </button>
                  {expandedContext[msg.id] && (
                    <div className="mt-2 p-4 bg-black/40 border border-white/5 rounded-xl text-[10px] font-mono text-white/50 whitespace-pre-wrap overflow-x-auto max-h-60 custom-scrollbar animate-in zoom-in-95 duration-200">
                      {msg.context}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {isTyping && (
          <div className="flex items-start space-x-4 animate-pulse">
            <div className="w-10 h-10 rounded-2xl bg-primary/10 flex items-center justify-center text-primary/50">
              <Bot className="w-6 h-6" />
            </div>
            <div className="glass p-4 rounded-2xl rounded-tl-none border-white/5">
              <div className="flex space-x-1">
                <div className="w-1.5 h-1.5 bg-primary/40 rounded-full animate-bounce"></div>
                <div className="w-1.5 h-1.5 bg-primary/40 rounded-full animate-bounce [animation-delay:0.2s]"></div>
                <div className="w-1.5 h-1.5 bg-primary/40 rounded-full animate-bounce [animation-delay:0.4s]"></div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-8">
        <div className="relative group">
          <div className="absolute -inset-1 bg-gradient-to-r from-primary/50 to-blue-500/50 rounded-[2rem] blur opacity-20 group-focus-within:opacity-40 transition duration-1000"></div>
          <div className="relative flex items-center bg-[#0a0c12] border border-white/10 rounded-[1.5rem] p-2 pl-6 shadow-2xl focus-within:border-primary/50 transition-all">
            <input 
              type="text" 
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about your wiki..." 
              className="flex-1 bg-transparent border-none focus:ring-0 text-sm outline-none placeholder:text-white/20 text-white py-3"
            />
            <button 
              onClick={handleSend}
              disabled={!input.trim() || isTyping}
              className={`p-3 bg-primary text-white rounded-xl transition-all shadow-lg shadow-primary/20 hover:scale-105 active:scale-95 disabled:opacity-50 disabled:hover:scale-100 ml-2`}
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </div>
        <p className="text-[10px] text-center text-white/20 mt-4 uppercase tracking-[0.2em] font-bold">
          <Sparkles className="w-3 h-3 inline-block mr-1 mb-0.5" />
          Wiki Intelligence Engine • {getModelDisplayName(selectedModel)}
        </p>
      </div>
    </div>
  );
};

export default ChatView;
