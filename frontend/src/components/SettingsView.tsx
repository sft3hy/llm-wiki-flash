import React, { useEffect, useState } from 'react';
import { BookOpen, Check, Cpu, Database, FileText, RefreshCw, Settings, Shield, Trash } from 'lucide-react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = 'http://localhost:8000';

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
  selectedWikiId: string;
  selectedWikiName: string;
}

const SettingsView: React.FC<SettingsViewProps> = ({
  models,
  selectedModel,
  onModelChange,
  wikiPages,
  selectedWikiId,
  selectedWikiName,
}) => {
  const [schemaContent, setSchemaContent] = useState('');
  const [showSchema, setShowSchema] = useState(false);
  const [rawSources, setRawSources] = useState<string[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);

  useEffect(() => {
    if (!selectedWikiId) {
      setSchemaContent('');
      setRawSources([]);
      return;
    }
    void axios
      .get(`${API_BASE}/schema`, { params: { wiki_id: selectedWikiId } })
      .then((response) => setSchemaContent(response.data.content))
      .catch(() => setSchemaContent(''));
    void fetchRawSources();
  }, [selectedWikiId]);

  const fetchRawSources = async () => {
    if (!selectedWikiId) {
      return;
    }
    setLoadingSources(true);
    try {
      const response = await axios.get(`${API_BASE}/raw`, {
        params: { wiki_id: selectedWikiId },
      });
      setRawSources(response.data);
    } catch (error) {
      console.error('Error fetching raw sources:', error);
    } finally {
      setLoadingSources(false);
    }
  };

  const handleDeleteRawSource = async (filename: string) => {
    if (!window.confirm(`Delete raw source "${filename}" from ${selectedWikiName}? Existing wiki pages will remain until re-indexed.`)) {
      return;
    }
    try {
      await axios.delete(`${API_BASE}/raw/${filename}`, {
        params: { wiki_id: selectedWikiId },
      });
      await fetchRawSources();
    } catch (error) {
      console.error('Error deleting raw source:', error);
      alert('Failed to delete raw source.');
    }
  };

  const systemPages = ['index.md', 'log.md', 'SCHEMA.md'];
  const contentPages = wikiPages.filter((page) => !systemPages.includes(page));
  const currentProvider = models.find((model) => model.model_id === selectedModel)?.provider;

  return (
    <div className="mx-auto max-w-2xl space-y-12 py-12 animate-in fade-in duration-500">
      <div className="space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Settings</h2>
        <p className="text-white/40">Manage models and document storage for <span className="font-semibold text-white">{selectedWikiName}</span>.</p>
      </div>

      <div className="grid gap-6">
        <section className="glass space-y-6 rounded-2xl p-6">
          <div className="flex items-center space-x-3 text-primary">
            <Settings className="h-5 w-5" />
            <h3 className="font-semibold">Model Selection</h3>
          </div>
          <div className="space-y-3">
            <div className="flex items-center space-x-2">
              <Cpu className="h-4 w-4 text-emerald-400" />
              <span className="text-xs font-bold uppercase tracking-widest text-emerald-400/60">Local · Ollama</span>
            </div>
            {models.map((model) => (
              <button
                key={model.model_id}
                onClick={() => onModelChange(model.model_id)}
                className={`w-full rounded-xl border p-4 text-left transition-all ${
                  selectedModel === model.model_id
                    ? 'border-emerald-500/20 bg-emerald-500/10'
                    : 'border-white/5 bg-white/[0.02] hover:bg-white/5'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-white">{model.display_name}</p>
                    <p className="mt-0.5 text-[11px] text-white/40">{model.description}</p>
                  </div>
                  {selectedModel === model.model_id && <Check className="h-4 w-4 text-emerald-400" />}
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="glass space-y-6 rounded-2xl p-6">
          <div className="flex items-center space-x-3 text-primary">
            <Database className="h-5 w-5" />
            <h3 className="font-semibold">Wiki Footprint</h3>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-4 text-center">
              <p className="text-2xl font-black text-white">{contentPages.length}</p>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-white/30">Pages</p>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-4 text-center">
              <p className="text-2xl font-black text-white">{rawSources.length}</p>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-white/30">Sources</p>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.03] p-4 text-center">
              <p className="text-2xl font-black text-white">{wikiPages.includes('SCHEMA.md') ? '✓' : '—'}</p>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-white/30">Schema</p>
            </div>
          </div>
          <div className="rounded-xl border border-white/5 bg-black/20 px-4 py-3 text-xs text-white/45">
            This wiki is isolated under <code className="rounded bg-white/5 px-1.5 py-0.5 text-white/70">/data/wikis/{selectedWikiId}</code>.
          </div>
        </section>

        <section className="glass space-y-6 rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3 text-primary">
              <FileText className="h-5 w-5" />
              <h3 className="font-semibold">Raw Sources</h3>
            </div>
            <button
              onClick={() => void fetchRawSources()}
              className={`rounded-lg p-1.5 transition-colors hover:bg-white/5 ${loadingSources ? 'animate-spin' : ''}`}
            >
              <RefreshCw className="h-4 w-4 text-white/30" />
            </button>
          </div>
          <div className="max-h-60 space-y-2 overflow-y-auto pr-1 custom-scrollbar">
            {rawSources.length === 0 ? (
              <p className="py-4 text-center text-xs italic text-white/20">No local source files in this wiki yet.</p>
            ) : (
              rawSources.map((source) => (
                <div
                  key={source}
                  className="group flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-all hover:border-white/10"
                >
                  <div className="flex items-center space-x-3 overflow-hidden">
                    <div className="rounded-lg bg-primary/5 p-2 text-primary/60">
                      <FileText className="h-4 w-4" />
                    </div>
                    <span className="truncate text-sm text-white/70">{source}</span>
                  </div>
                  <button
                    onClick={() => void handleDeleteRawSource(source)}
                    className="rounded-lg p-2 text-white/20 opacity-0 transition-all hover:bg-red-500/10 hover:text-red-400 group-hover:opacity-100"
                    title="Delete Source"
                  >
                    <Trash className="h-4 w-4" />
                  </button>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="glass space-y-4 rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3 text-primary">
              <BookOpen className="h-5 w-5" />
              <h3 className="font-semibold">Schema</h3>
            </div>
            <button
              onClick={() => setShowSchema((previous) => !previous)}
              className="text-xs font-bold uppercase tracking-widest text-white/30 transition-colors hover:text-white/60"
            >
              {showSchema ? 'Hide' : 'View'}
            </button>
          </div>
          {showSchema && schemaContent && (
            <div className="prose prose-invert prose-sm max-h-96 max-w-none overflow-y-auto rounded-xl border border-white/5 bg-white/[0.02] p-6 custom-scrollbar">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{schemaContent}</ReactMarkdown>
            </div>
          )}
        </section>

        <section className="glass space-y-4 rounded-2xl p-6">
          <div className="flex items-center space-x-3 text-primary">
            <Shield className="h-5 w-5" />
            <h3 className="font-semibold">Privacy</h3>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Local Processing</p>
              <p className="text-xs text-white/40">Active models run locally and retrieval stays scoped to the selected wiki.</p>
            </div>
            <div className={`relative h-5 w-10 rounded-full ${currentProvider === 'ollama' ? 'bg-emerald-500/30' : 'bg-white/10'}`}>
              <div
                className={`absolute top-1 h-3 w-3 rounded-full transition-all ${
                  currentProvider === 'ollama' ? 'right-1 bg-emerald-400' : 'left-1 bg-white/30'
                }`}
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default SettingsView;
