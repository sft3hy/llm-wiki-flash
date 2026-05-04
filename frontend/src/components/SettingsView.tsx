import React, { useState, useEffect } from 'react';
import { Settings, Cpu, Cloud, Check, Database, Shield, BookOpen, Trash, FileText, RefreshCw } from 'lucide-react';
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
  wikiPages: string[];
}

const SettingsView: React.FC<SettingsViewProps> = ({ models, selectedModel, onModelChange, wikiPages }) => {
  const [schemaContent, setSchemaContent] = useState('');
  const [showSchema, setShowSchema] = useState(false);
  const [rawSources, setRawSources] = useState<string[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);

  useEffect(() => {
    axios.get(`${API_BASE}/schema`).then(r => setSchemaContent(r.data.content)).catch(() => {});
    fetchRawSources();
  }, []);

  const fetchRawSources = async () => {
    setLoadingSources(true);
    try {
      const response = await axios.get(`${API_BASE}/raw`);
      setRawSources(response.data);
    } catch (error) {
      console.error("Error fetching raw sources:", error);
    } finally {
      setLoadingSources(false);
    }
  };

  const handleDeleteRawSource = async (filename: string) => {
    if (!window.confirm(`Delete raw source "${filename}"? Wiki pages already compiled from this source will remain.`)) {
      return;
    }
    try {
      await axios.delete(`${API_BASE}/raw/${filename}`);
      fetchRawSources();
    } catch (error) {
      console.error("Error deleting raw source:", error);
      alert("Failed to delete raw source.");
    }
  };

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
            {models.map(m => (
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
              <p className="text-2xl font-black text-white">{wikiPages.length.toString() === '0' ? '0' : rawSources.length}</p>
              <p className="text-[10px] uppercase tracking-widest text-white/30 font-bold mt-1">Sources</p>
            </div>
            <div className="bg-white/[0.03] p-4 rounded-xl border border-white/5 text-center">
              <p className="text-2xl font-black text-white">{wikiPages.includes('SCHEMA.md') ? '✓' : '—'}</p>
              <p className="text-[10px] uppercase tracking-widest text-white/30 font-bold mt-1">Schema</p>
            </div>
          </div>
        </section>

        {/* Managed Sources */}
        <section className="glass p-6 rounded-2xl space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3 text-primary">
              <FileText className="w-5 h-5" />
              <h3 className="font-semibold">Raw Sources</h3>
            </div>
            <button onClick={fetchRawSources} className={`p-1.5 hover:bg-white/5 rounded-lg transition-colors ${loadingSources ? 'animate-spin' : ''}`}>
              <RefreshCw className="w-4 h-4 text-white/30" />
            </button>
          </div>
          <div className="space-y-2 max-h-60 overflow-y-auto custom-scrollbar pr-1">
            {rawSources.length === 0 ? (
              <p className="text-center py-4 text-xs text-white/20 italic">No raw sources uploaded yet.</p>
            ) : (
              rawSources.map((source) => (
                <div key={source} className="flex items-center justify-between p-3 bg-white/[0.02] border border-white/5 rounded-xl group hover:border-white/10 transition-all">
                  <div className="flex items-center space-x-3 overflow-hidden">
                    <div className="p-2 bg-primary/5 text-primary/60 rounded-lg">
                      <FileText className="w-4 h-4" />
                    </div>
                    <span className="text-sm text-white/70 truncate">{source}</span>
                  </div>
                  <button
                    onClick={() => handleDeleteRawSource(source)}
                    className="p-2 text-white/20 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                    title="Delete Source"
                  >
                    <Trash className="w-4 h-4" />
                  </button>
                </div>
              ))
            )}
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
