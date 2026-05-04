import React, { useState } from 'react';
import { Upload, Cpu, FileText, Activity, Folder, Database, Bookmark, BookOpen, Library } from 'lucide-react';
import axios from 'axios';

const API_BASE = "http://localhost:8000";

interface Model {
  model_id: string;
  display_name: string;
}

interface IngestViewProps {
  masterModel: string;
  models: Model[];
  onSuccess: () => void;
  isIngesting: boolean;
}

type IngestMode = 'folder' | 'vault' | 'clippings';

const IngestView: React.FC<IngestViewProps> = ({ masterModel, models, onSuccess, isIngesting }) => {
  const [topic, setTopic] = useState('');
  const [mode, setMode] = useState<IngestMode>('folder');

  // State for files
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);

  // State for Vault path
  const [vaultPath, setVaultPath] = useState('');

  const [overrideModel, setOverrideModel] = useState<string>('');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFiles(e.target.files);
    }
  };

  const handleUpload = async () => {
    if (!topic.trim()) {
      alert("Please enter a topic for this corpus.");
      return;
    }

    const modelToUse = overrideModel || masterModel;

    try {
      if (mode === 'vault') {
        if (!vaultPath.trim()) return;
        await axios.post(`${API_BASE}/ingest/vault`, {
          path: vaultPath.trim(),
          topic: topic.trim(),
          model: modelToUse
        });
      } else {
        if (!selectedFiles || selectedFiles.length === 0) return;
        const formData = new FormData();
        Array.from(selectedFiles).forEach(file => {
          formData.append('files', file);
        });

        await axios.post(`${API_BASE}/ingest?topic=${encodeURIComponent(topic.trim())}&model=${modelToUse}`, formData);
      }

      onSuccess();
      setSelectedFiles(null);
      setVaultPath('');
      setTopic('');
      setOverrideModel('');
    } catch (error) {
      console.error("Error ingesting corpus:", error);
      alert("Ingestion failed.");
    }
  };

  const masterModelName = models.find(m => m.model_id === masterModel)?.display_name || masterModel;

  const canSubmit = topic.trim() && (mode === 'vault' ? vaultPath.trim() : (selectedFiles && selectedFiles.length > 0));

  return (
    <div className="flex flex-col h-full max-w-2xl mx-auto p-10 animate-in fade-in duration-500">
      <div className="space-y-8">
        <div className="space-y-2">
          <h2 className="text-4xl font-black tracking-tight text-white">Knowledge Ingestion</h2>
          <p className="text-white/40">Build your wiki by clustering documents around a core topic.</p>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-6 space-y-6">

          {/* Topic Input */}
          <div className="space-y-3">
            <label className="text-sm font-semibold text-white/80 block">1. Corpus Topic</label>
            <input
              type="text"
              placeholder="e.g., Quantum Computing, Local LLMs, Roman History"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              disabled={isIngesting}
              className="w-full bg-[#0a0c12] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-primary/50 transition-colors"
            />
          </div>

          {/* Mode Selection */}
          <div className="space-y-3 pt-4 border-t border-white/10">
            <label className="text-sm font-semibold text-white/80 block">2. Source Mode</label>
            <div className="grid grid-cols-3 gap-3">
              <button
                onClick={() => setMode('folder')}
                className={`flex flex-col items-center justify-center p-4 rounded-xl border ${mode === 'folder' ? 'bg-primary/10 border-primary/30 text-primary' : 'bg-white/5 border-white/5 text-white/40 hover:bg-white/10'} transition-all`}
              >
                <Folder className="w-6 h-6 mb-2" />
                <span className="text-xs font-semibold">Folder Upload</span>
              </button>
              <button
                onClick={() => setMode('vault')}
                className={`flex flex-col items-center justify-center p-4 rounded-xl border ${mode === 'vault' ? 'bg-primary/10 border-primary/30 text-primary' : 'bg-white/5 border-white/5 text-white/40 hover:bg-white/10'} transition-all`}
              >
                <Database className="w-6 h-6 mb-2" />
                <span className="text-xs font-semibold">Local Vault</span>
              </button>
              <button
                onClick={() => setMode('clippings')}
                className={`flex flex-col items-center justify-center p-4 rounded-xl border ${mode === 'clippings' ? 'bg-primary/10 border-primary/30 text-primary' : 'bg-white/5 border-white/5 text-white/40 hover:bg-white/10'} transition-all`}
              >
                <Bookmark className="w-6 h-6 mb-2" />
                <span className="text-xs font-semibold">Web Clippings</span>
              </button>
            </div>
          </div>

          {/* Source Input */}
          <div className="space-y-3 pt-4 border-t border-white/10">
            <label className="text-sm font-semibold text-white/80 block">3. Select Source</label>

            {mode === 'vault' ? (
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder="/Users/username/Documents/ObsidianVault"
                  value={vaultPath}
                  onChange={(e) => setVaultPath(e.target.value)}
                  disabled={isIngesting}
                  className="w-full bg-[#0a0c12] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-primary/50 transition-colors"
                />
                <p className="text-[10px] text-amber-400/70">Enter the absolute local path to your vault. The system will recursively scan for .md and .txt files.</p>
              </div>
            ) : (
              <div className={`border-2 border-dashed ${selectedFiles && selectedFiles.length > 0 ? 'border-primary/50 bg-primary/5' : 'border-white/20 bg-white/5'} rounded-xl p-8 text-center hover:bg-white/10 transition-colors cursor-pointer relative`}>
                {mode === 'folder' ? (
                  <input
                    type="file"
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    onChange={handleFileChange}
                    disabled={isIngesting}
                    // @ts-ignore
                    webkitdirectory=""
                    directory=""
                    multiple
                  />
                ) : (
                  <input
                    type="file"
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    onChange={handleFileChange}
                    disabled={isIngesting}
                    multiple
                    accept=".md,.txt,.html"
                  />
                )}

                <div className="flex flex-col items-center space-y-3 pointer-events-none">
                  {selectedFiles && selectedFiles.length > 0 ? (
                    <>
                      <div className="p-3 bg-primary/20 rounded-full text-primary">
                        <FileText className="w-8 h-8" />
                      </div>
                      <span className="text-white font-medium">{selectedFiles.length} files selected</span>
                    </>
                  ) : (
                    <>
                      <div className="p-3 bg-white/10 rounded-full text-white/40">
                        <Upload className="w-8 h-8" />
                      </div>
                      <span className="text-white/60 font-medium">Click or drag {mode === 'folder' ? 'folder' : 'files'} to upload</span>
                      <span className="text-xs text-white/30">Markdown (.md), Text (.txt), or HTML</span>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-3 pt-4 border-t border-white/10">
            <label className="text-sm font-semibold text-white/80 block">4. Ingestion Model</label>
            <p className="text-xs text-white/40 mb-2">Select which LLM will parse and structure this corpus.</p>
            <select
              className="w-full bg-[#0a0c12] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-primary/50 transition-colors"
              value={overrideModel}
              onChange={(e) => setOverrideModel(e.target.value)}
              disabled={isIngesting}
            >
              <option value="">Use Master Model ({masterModelName})</option>
              {models.filter(m => m.model_id !== 'gemma4:e4b').map(m => (
                <option key={m.model_id} value={m.model_id}>{m.display_name}</option>
              ))}
            </select>
          </div>

          <div className="pt-6 border-t border-white/10">
            <button
              onClick={handleUpload}
              disabled={!canSubmit || isIngesting}
              className={`w-full flex items-center justify-center space-x-2 py-4 rounded-xl text-white font-bold transition-all ${!canSubmit || isIngesting
                  ? 'bg-white/5 text-white/30 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-500 shadow-[0_0_20px_rgba(59,130,246,0.4)] hover:scale-[1.02]'
                }`}
            >
              {isIngesting ? (
                <>
                  <BookOpen className="w-5 h-5 animate-page-turn" />
                  <span>Documenting Knowledge...</span>
                </>
              ) : (
                <>
                  <Library className="w-5 h-5" />
                  <span>Create Wiki Book</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default IngestView;
