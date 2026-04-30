import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Cpu, Cloud, Check, Zap } from 'lucide-react';

interface Model {
  model_id: string;
  display_name: string;
  provider: string;
  description: string;
}

interface ModelSelectorProps {
  models: Model[];
  selectedModel: string;
  onModelChange: (modelId: string) => void;
  groqConfigured: boolean;
}

const ModelSelector: React.FC<ModelSelectorProps> = ({ models, selectedModel, onModelChange, groqConfigured }) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const selected = models.find(m => m.model_id === selectedModel);
  const ollamaModels = models.filter(m => m.provider === 'ollama');
  const groqModels = models.filter(m => m.provider === 'groq');

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const ProviderIcon = ({ provider }: { provider: string }) => (
    provider === 'ollama' 
      ? <Cpu className="w-3 h-3" />
      : <Cloud className="w-3 h-3" />
  );

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center space-x-2.5 px-4 py-2.5 rounded-2xl bg-white/5 border border-white/10 hover:border-primary/30 hover:bg-white/[0.07] transition-all duration-300 group"
      >
        <div className={`p-1 rounded-lg ${selected?.provider === 'ollama' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-violet-500/10 text-violet-400'}`}>
          <ProviderIcon provider={selected?.provider || 'ollama'} />
        </div>
        <span className="text-xs font-semibold text-white/80 tracking-wide">
          {selected?.display_name || 'Select Model'}
        </span>
        <ChevronDown className={`w-3.5 h-3.5 text-white/30 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-[#0c0e14] border border-white/10 rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.6)] overflow-hidden z-50 animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="p-3 border-b border-white/5">
            <div className="flex items-center space-x-2 px-2">
              <Zap className="w-3.5 h-3.5 text-primary/60" />
              <span className="text-[10px] font-black uppercase tracking-[0.2em] text-white/30">Model Selection</span>
            </div>
          </div>

          <div className="p-2 max-h-80 overflow-y-auto custom-scrollbar">
            {/* Local Models */}
            <div className="px-2 pt-2 pb-1">
              <span className="text-[9px] font-black uppercase tracking-[0.2em] text-emerald-400/50 flex items-center space-x-1.5">
                <Cpu className="w-3 h-3" />
                <span>Local · Ollama</span>
              </span>
            </div>
            {ollamaModels.map((model) => (
              <button
                key={model.model_id}
                onClick={() => { onModelChange(model.model_id); setIsOpen(false); }}
                className={`w-full flex items-center justify-between px-3 py-3 rounded-xl transition-all duration-200 group ${
                  selectedModel === model.model_id 
                    ? 'bg-emerald-500/10 border border-emerald-500/20' 
                    : 'hover:bg-white/5 border border-transparent'
                }`}
              >
                <div className="flex flex-col items-start">
                  <span className="text-sm font-semibold text-white/90">{model.display_name}</span>
                  <span className="text-[10px] text-white/30 mt-0.5">{model.description}</span>
                </div>
                {selectedModel === model.model_id && (
                  <Check className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                )}
              </button>
            ))}

            {/* Groq Models */}
            <div className="px-2 pt-4 pb-1">
              <span className="text-[9px] font-black uppercase tracking-[0.2em] text-violet-400/50 flex items-center space-x-1.5">
                <Cloud className="w-3 h-3" />
                <span>Cloud · Groq</span>
                {!groqConfigured && (
                  <span className="text-[8px] bg-amber-500/10 text-amber-400 px-1.5 py-0.5 rounded-full font-bold ml-1">
                    No API Key
                  </span>
                )}
              </span>
            </div>
            {groqModels.map((model) => (
              <button
                key={model.model_id}
                onClick={() => { onModelChange(model.model_id); setIsOpen(false); }}
                disabled={!groqConfigured}
                className={`w-full flex items-center justify-between px-3 py-3 rounded-xl transition-all duration-200 ${
                  !groqConfigured 
                    ? 'opacity-40 cursor-not-allowed' 
                    : selectedModel === model.model_id 
                      ? 'bg-violet-500/10 border border-violet-500/20' 
                      : 'hover:bg-white/5 border border-transparent'
                }`}
              >
                <div className="flex flex-col items-start">
                  <span className="text-sm font-semibold text-white/90">{model.display_name}</span>
                  <span className="text-[10px] text-white/30 mt-0.5">{model.description}</span>
                </div>
                {selectedModel === model.model_id && (
                  <Check className="w-4 h-4 text-violet-400 flex-shrink-0" />
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ModelSelector;
