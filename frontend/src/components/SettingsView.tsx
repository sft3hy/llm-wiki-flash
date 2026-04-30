import React, { useState, useEffect } from 'react';
import { Settings, Cpu, Cloud, Check, Database, Shield, BookOpen } from 'lucide-react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = "http://localhost:8000";

interface Model {
  model_id: string;
  display_name: string;
  provider: string;
  description: string;
}

interface SettingsViewProps {
  models: Model[];
  selectedModel: string;
  onModelChange: (modelId: string) => void;
  groqConfigured: boolean;
  wikiPages: string[];
}

const SettingsView: React.FC<SettingsViewProps> = ({ models, selectedModel, onModelChange, groqConfigured, wikiPages }) => {
  const [schemaContent, setSchemaContent] = useState('');
  const [showSchema, setShowSchema] = useState(false);

  useEffect(() => {
    axios.get(`${API_BASE}/schema`).then(r => setSchemaContent(r.data.content)).catch(() => {});
  }, []);

  const ollamaModels = models.filter(m => m.provider === 'ollama');
  const groqModels = models.filter(m => m.provider === 'groq');
  const systemPages = ['index.md', 'log.md', 'SCHEMA.md'];
  const contentPages = wikiPages.filter(p => !systemPages.includes(p));
  const currentProvider = models.find(m => m.model_id === selectedModel)?.provider;



  return (
    <div className="max-w-2xl mx-auto py-12 space-y-12 animate-in fade-in duration-500">
      <div className="space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Settings</h2>
        <p className="text-white/40">Manage your wiki configuration, models, and AI preferences.</p>
      </div>

      <div className="grid gap-6">
        {/* Model Selection */}
        <section className="glass p-6 rounded-2xl space-y-6">
          <div className="flex items-center space-x-3 text-primary">
            <Settings className="w-5 h-5" />
            <h3 className="font-semibold">Model Selection</h3>
          </div>
          <div className="space-y-3">
            <div className="flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-bold uppercase tracking-widest text-emerald-400/60">Local · Ollama</span>
            </div>
            {ollamaModels.map(m => (
              <button key={m.model_id} onClick={() => onModelChange(m.model_id)}
                className={`w-full flex items-center justify-between p-4 rounded-xl transition-all border ${
                  selectedModel === m.model_id ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-white/[0.02] border-white/5 hover:bg-white/5'
                }`}>
                <div className="text-left">
                  <p className="text-sm font-semibold text-white">{m.display_name}</p>
                  <p className="text-[11px] text-white/40 mt-0.5">{m.description}</p>
                </div>
                {selectedModel === m.model_id && <Check className="w-4 h-4 text-emerald-400" />}
              </button>
            ))}
          </div>
          <div className="space-y-3 pt-2">
            <div className="flex items-center space-x-2">
              <Cloud className="w-4 h-4 text-violet-400" />
              <span className="text-xs font-bold uppercase tracking-widest text-violet-400/60">Cloud · Groq</span>
              {groqConfigured
                ? <span className="text-[9px] bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded-full font-bold">✓ Active</span>
                : <span className="text-[9px] bg-amber-500/10 text-amber-400 px-2 py-0.5 rounded-full font-bold">No Key</span>}
            </div>
            {groqModels.map(m => (
              <button key={m.model_id} onClick={() => onModelChange(m.model_id)} disabled={!groqConfigured}
                className={`w-full flex items-center justify-between p-4 rounded-xl transition-all border ${
                  !groqConfigured ? 'opacity-40 cursor-not-allowed border-white/5'
                  : selectedModel === m.model_id ? 'bg-violet-500/10 border-violet-500/20' : 'bg-white/[0.02] border-white/5 hover:bg-white/5'
                }`}>
                <div className="text-left">
                  <p className="text-sm font-semibold text-white">{m.display_name}</p>
                  <p className="text-[11px] text-white/40 mt-0.5">{m.description}</p>
                </div>
                {selectedModel === m.model_id && <Check className="w-4 h-4 text-violet-400" />}
              </button>
            ))}
            {!groqConfigured && (
              <p className="text-xs text-amber-400/50 px-2">
                Set <code className="bg-white/5 px-1.5 py-0.5 rounded text-[10px]">GROQ_API_KEY</code> in your .env to enable cloud models.
              </p>
            )}
          </div>
        </section>

        {/* Wiki Stats */}
        <section className="glass p-6 rounded-2xl space-y-6">
          <div className="flex items-center space-x-3 text-primary">
            <Database className="w-5 h-5" />
            <h3 className="font-semibold">Knowledge Base</h3>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-white/[0.03] p-4 rounded-xl border border-white/5 text-center">
              <p className="text-2xl font-black text-white">{contentPages.length}</p>
              <p className="text-[10px] uppercase tracking-widest text-white/30 font-bold mt-1">Pages</p>
            </div>
            <div className="bg-white/[0.03] p-4 rounded-xl border border-white/5 text-center">
              <p className="text-2xl font-black text-white">{wikiPages.includes('log.md') ? '✓' : '—'}</p>
              <p className="text-[10px] uppercase tracking-widest text-white/30 font-bold mt-1">Log</p>
            </div>
            <div className="bg-white/[0.03] p-4 rounded-xl border border-white/5 text-center">
              <p className="text-2xl font-black text-white">{wikiPages.includes('SCHEMA.md') ? '✓' : '—'}</p>
              <p className="text-[10px] uppercase tracking-widest text-white/30 font-bold mt-1">Schema</p>
            </div>
          </div>
        </section>

        {/* Schema Viewer */}
        <section className="glass p-6 rounded-2xl space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3 text-primary">
              <BookOpen className="w-5 h-5" />
              <h3 className="font-semibold">Schema</h3>
            </div>
            <button onClick={() => setShowSchema(!showSchema)}
              className="text-xs font-bold uppercase tracking-widest text-white/30 hover:text-white/60 transition-colors">
              {showSchema ? 'Hide' : 'View'}
            </button>
          </div>
          {showSchema && schemaContent && (
            <div className="prose prose-invert prose-sm max-w-none bg-white/[0.02] p-6 rounded-xl border border-white/5 max-h-96 overflow-y-auto custom-scrollbar">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{schemaContent}</ReactMarkdown>
            </div>
          )}
        </section>

        {/* Privacy */}
        <section className="glass p-6 rounded-2xl space-y-4">
          <div className="flex items-center space-x-3 text-primary">
            <Shield className="w-5 h-5" />
            <h3 className="font-semibold">Privacy</h3>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Local Processing</p>
              <p className="text-xs text-white/40">Use Ollama to keep data on your machine.</p>
            </div>
            <div className={`w-10 h-5 rounded-full relative ${currentProvider === 'ollama' ? 'bg-emerald-500/30' : 'bg-white/10'}`}>
              <div className={`absolute top-1 w-3 h-3 rounded-full transition-all ${
                currentProvider === 'ollama' ? 'right-1 bg-emerald-400' : 'left-1 bg-white/30'
              }`}></div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default SettingsView;
