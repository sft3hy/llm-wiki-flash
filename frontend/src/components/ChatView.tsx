import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Sparkles, Cpu, Cloud } from 'lucide-react';
import axios from 'axios';

interface Message {
  id: string;
  text: string;
  sender: 'user' | 'bot';
  timestamp: Date;
  model?: string;
}

const API_BASE = "http://localhost:8000";

interface ChatViewProps {
  selectedModel: string;
}

const ChatView: React.FC<ChatViewProps> = ({ selectedModel }) => {
  const [input, setInput] = useState('');
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

  const getModelDisplayName = (modelId: string) => {
    const names: Record<string, string> = {
      'gemma4:e4b': 'Gemma 4',
      'llama-3.3-70b-versatile': 'Llama 3.3 70B',
      'openai/gpt-oss-120b': 'GPT-OSS 120B',
      'meta-llama/llama-4-scout-17b-16e-instruct': 'Llama 4 Scout',
    };
    return names[modelId] || modelId;
  };

  const isLocalModel = (modelId: string) => modelId.includes('gemma');

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      text: input,
      sender: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    const currentInput = input;
    setInput('');
    setIsTyping(true);

    try {
      // Prepare history for backend
      const history = messages.slice(1).map(msg => ({
        role: msg.sender === 'user' ? 'user' : 'assistant',
        content: msg.text
      }));

      const response = await axios.post(`${API_BASE}/chat`, {
        message: currentInput,
        history: history,
        model: selectedModel,
      });

      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: response.data.response,
        sender: 'bot',
        timestamp: new Date(),
        model: selectedModel,
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

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto animate-in fade-in duration-500">
      <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
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
            <div className={`p-4 rounded-2xl max-w-[80%] shadow-xl border ${
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
