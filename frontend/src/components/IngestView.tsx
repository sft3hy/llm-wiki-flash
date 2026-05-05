import React, { useState } from 'react';
import { Upload, FileText, BookOpen, Library } from 'lucide-react';
import axios from 'axios';

const API_BASE = "http://localhost:8000";

interface Model {
  model_id: string;
  display_name: string;
}

interface IngestProgress {
  message: string;
  progress: number;
  status: string;
  stage?: string;
  step?: string;
  document_name?: string;
  document_index?: number;
  total_documents?: number;
  concept_name?: string;
  concept_index?: number;
  total_concepts?: number;
  duration_ms?: number;
  active_model?: string | null;
}

interface IngestViewProps {
  masterModel: string;
  models: Model[];
  selectedWikiId: string;
  selectedWikiName: string;
  onSuccess: () => void;
  isIngesting: boolean;
  progress: IngestProgress | null;
}

const IngestView: React.FC<IngestViewProps> = ({ masterModel, models, selectedWikiId, selectedWikiName, onSuccess, isIngesting, progress }) => {
  const [topic, setTopic] = useState('');
  
  // State for files
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  
  const [overrideModel, setOverrideModel] = useState<string>('');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const validExtensions = ['.md', '.txt', '.html'];
      const filtered = Array.from(e.target.files).filter(file => {
        const path = file.webkitRelativePath || file.name;
        if (path.includes('/.')) return false; // Skip hidden folders
        if (file.name.startsWith('.')) return false; // Skip hidden files
        return validExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
      });
      setSelectedFiles(filtered);
    }
  };

  const handleUpload = async () => {
    if (!topic.trim()) {
      alert("Please enter a topic for this corpus.");
      return;
    }

    const modelToUse = overrideModel || masterModel;

    try {
      if (!selectedFiles || selectedFiles.length === 0) return;
      const formData = new FormData();
      
      selectedFiles.forEach(file => {
        formData.append('files', file);
      });

      await axios.post(`${API_BASE}/ingest?topic=${encodeURIComponent(topic.trim())}&model=${modelToUse}&wiki_id=${encodeURIComponent(selectedWikiId)}`, formData);

      onSuccess();
      setSelectedFiles([]);
      setTopic('');
      setOverrideModel('');
    } catch (error) {
      console.error("Error ingesting corpus:", error);
      alert("Ingestion failed.");
    }
  };

  const masterModelName = models.find(m => m.model_id === masterModel)?.display_name || masterModel;
  const modelInUse = progress?.active_model || overrideModel || masterModel;

  const canSubmit = topic.trim() && selectedFiles && selectedFiles.length > 0;

  return (
    <div className="flex flex-col h-full max-w-2xl mx-auto p-10 animate-in fade-in duration-500">
      <div className="space-y-8">
        <div className="space-y-2">
          <h2 className="text-4xl font-black tracking-tight text-white">Knowledge Ingestion</h2>
          <p className="text-white/40">Build <span className="text-white font-semibold">{selectedWikiName}</span> by clustering documents around a core topic.</p>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-6 space-y-6">
          {(isIngesting || progress) && (
            <div className="space-y-4 rounded-2xl border border-primary/20 bg-primary/5 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.2em] text-primary/70">Live Pipeline</p>
                  <p className="mt-2 text-sm font-semibold text-white">{progress?.message || 'Preparing ingestion pipeline...'}</p>
                  <p className="mt-1 text-xs text-white/45">
                    {progress?.stage ? `${progress.stage} / ${progress.step || 'working'}` : 'Waiting for the next step...'}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-black text-primary">{progress?.progress ?? 0}%</p>
                  <p className="text-[10px] uppercase tracking-[0.18em] text-white/35">{modelInUse}</p>
                </div>
              </div>

              <div className="h-2 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-primary to-blue-400 transition-all duration-500"
                  style={{ width: `${progress?.progress ?? 0}%` }}
                />
              </div>

              <div className="grid gap-3 text-xs text-white/60 md:grid-cols-3">
                <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
                  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/35">Document</p>
                  <p className="mt-2 text-sm text-white/85">
                    {progress?.document_index && progress?.total_documents
                      ? `${progress.document_index} of ${progress.total_documents}`
                      : 'Waiting'}
                  </p>
                  <p className="mt-1 truncate">{progress?.document_name || 'No document active'}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
                  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/35">Concepts</p>
                  <p className="mt-2 text-sm text-white/85">
                    {progress?.concept_index && progress?.total_concepts
                      ? `${progress.concept_index} of ${progress.total_concepts}`
                      : 'Not started'}
                  </p>
                  <p className="mt-1 truncate">{progress?.concept_name || 'No concept active'}</p>
                </div>
                <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
                  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/35">Duration</p>
                  <p className="mt-2 text-sm text-white/85">
                    {progress?.duration_ms ? `${(progress.duration_ms / 1000).toFixed(1)}s` : 'In progress'}
                  </p>
                  <p className="mt-1">{progress?.status === 'success' ? 'Latest completed step' : 'Current active step'}</p>
                </div>
              </div>
            </div>
          )}

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

          {/* Source Input */}
          <div className="space-y-3 pt-4 border-t border-white/10">
            <label className="text-sm font-semibold text-white/80 block">2. Select Source Documents</label>

            <div className={`border-2 border-dashed ${selectedFiles && selectedFiles.length > 0 ? 'border-primary/50 bg-primary/5' : 'border-white/20 bg-white/5'} rounded-xl p-8 text-center hover:bg-white/10 transition-colors cursor-pointer relative`}>
              <input
                type="file"
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                onChange={handleFileChange}
                disabled={isIngesting}
                multiple
                // @ts-ignore
                webkitdirectory=""
                directory=""
              />

              <div className="flex flex-col items-center space-y-3 pointer-events-none">
                {selectedFiles && selectedFiles.length > 0 ? (
                  <>
                    <div className="p-3 bg-primary/20 rounded-full text-primary">
                      <FileText className="w-8 h-8" />
                    </div>
                    <span className="text-white font-medium">{selectedFiles.length} valid documents selected</span>
                  </>
                ) : (
                  <>
                    <div className="p-3 bg-white/10 rounded-full text-white/40">
                      <Upload className="w-8 h-8" />
                    </div>
                    <span className="text-white/60 font-medium">Click to select folder or files</span>
                    <span className="text-xs text-white/30">Select your vault or corpus directory</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-3 pt-4 border-t border-white/10">
            <label className="text-sm font-semibold text-white/80 block">3. Ingestion Model</label>
            <p className="text-xs text-white/40 mb-2">Select which LLM will parse and structure this corpus.</p>
            <select
              className="w-full bg-[#0a0c12] border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-primary/50 transition-colors"
              value={overrideModel}
              onChange={(e) => setOverrideModel(e.target.value)}
              disabled={isIngesting}
            >
              <option value="">Use Master Model ({masterModelName})</option>
              {models.map(m => (
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
