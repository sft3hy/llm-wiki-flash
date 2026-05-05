import React, { useState, useEffect } from 'react';
import { RefreshCw, Link2, FileX, Search, Brain, Terminal, ShieldCheck, Zap } from 'lucide-react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = "http://localhost:8000";

interface MeditationViewProps {
  selectedWikiId: string;
  selectedWikiName: string;
  selectedModel: string;
}

interface LintResults {
  total_pages: number;
  broken_links: Array<{ source: string; target: string; suggestion: string }>;
  orphan_pages: string[];
  conflicting_pages: string[];
  stub_pages: string[];
  missing_frontmatter: string[];
  oversized_pages: Array<{ page: string; word_count: number; suggestion: string }>;
  duplicate_candidates: Array<{ title: string; pages: string[]; suggestion: string }>;
  suggestions: string[];
}

const MeditationView: React.FC<MeditationViewProps> = ({ selectedWikiId, selectedWikiName, selectedModel }) => {
  const [lintResults, setLintResults] = useState<LintResults | null>(null);
  const [lintLoading, setLintLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'curate' | 'lint'>('curate');
  const [maintenanceLog, setMaintenanceLog] = useState<string>('');
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);
  const [rebuildLoading, setRebuildLoading] = useState(false);
  const [integrityResult, setIntegrityResult] = useState<any | null>(null);

  useEffect(() => {
    if (activeTab === 'curate') {
      fetchLog();
    }
  }, [activeTab, selectedWikiId]);

  const fetchLog = async () => {
    try {
      const response = await axios.get(`${API_BASE}/log?wiki_id=${encodeURIComponent(selectedWikiId)}`);
      setMaintenanceLog(response.data.content);
    } catch (error) {
      console.error("Log error:", error);
    }
  };

  const runMaintenance = async () => {
    setMaintenanceLoading(true);
    try {
      await axios.post(`${API_BASE}/meditate?model=${selectedModel}&wiki_id=${encodeURIComponent(selectedWikiId)}`);
      await fetchLog();
    } catch (error) {
      console.error("Maintenance error:", error);
      alert("Maintenance loop failed.");
    } finally {
      setMaintenanceLoading(false);
    }
  };

  const runLint = async () => {
    setLintLoading(true);
    try {
      const response = await axios.post(`${API_BASE}/lint?model=${selectedModel}&wiki_id=${encodeURIComponent(selectedWikiId)}`);
      setLintResults(response.data);
    } catch (error) {
      console.error("Lint error:", error);
    } finally {
      setLintLoading(false);
    }
  };

  const rebuildEmbeddings = async () => {
    setRebuildLoading(true);
    try {
      await axios.post(`${API_BASE}/wikis/${selectedWikiId}/rebuild-embeddings`);
      const integrity = await axios.get(`${API_BASE}/wikis/${selectedWikiId}/validate`);
      setIntegrityResult(integrity.data);
    } catch (error) {
      console.error("Rebuild error:", error);
      alert("Failed to rebuild embeddings.");
    } finally {
      setRebuildLoading(false);
    }
  };

  const reindexDocuments = async () => {
    setMaintenanceLoading(true);
    try {
      await axios.post(`${API_BASE}/wikis/${selectedWikiId}/reindex?model=${encodeURIComponent(selectedModel)}`);
      await fetchLog();
      const integrity = await axios.get(`${API_BASE}/wikis/${selectedWikiId}/validate`);
      setIntegrityResult(integrity.data);
    } catch (error) {
      console.error("Reindex error:", error);
      alert("Failed to re-index wiki documents.");
    } finally {
      setMaintenanceLoading(false);
    }
  };

  const validateIntegrity = async () => {
    try {
      const response = await axios.get(`${API_BASE}/wikis/${selectedWikiId}/validate`);
      setIntegrityResult(response.data);
    } catch (error) {
      console.error("Integrity error:", error);
      alert("Failed to validate wiki integrity.");
    }
  };

  return (
    <div className="max-w-4xl mx-auto animate-in fade-in duration-500 pb-20">
      {/* Tab Bar */}
      <div className="flex items-center space-x-1 mb-10 bg-white/[0.03] p-1 rounded-2xl border border-white/5 w-fit">
        <button onClick={() => setActiveTab('curate')}
          className={`px-6 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all ${activeTab === 'curate' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/60'
            }`}>
          Maintenance
        </button>
        <button onClick={() => setActiveTab('lint')}
          className={`px-6 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all ${activeTab === 'lint' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/60'
            }`}>
          Librarian
        </button>
      </div>

      {activeTab === 'curate' ? (
        /* Agentic Maintenance Tab */
        <div className="space-y-12">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <h2 className="text-3xl font-bold tracking-tight">Agentic Maintenance</h2>
              <p className="text-white/40 max-w-lg">Maintain <span className="text-white font-semibold">{selectedWikiName}</span> with re-indexing, integrity checks, and synthesis passes.</p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={runMaintenance}
                disabled={maintenanceLoading}
                className="group relative px-8 py-4 bg-primary text-black rounded-2xl font-bold overflow-hidden transition-all hover:scale-105 active:scale-95 disabled:opacity-50 shadow-xl shadow-primary/20"
              >
                <div className="flex items-center space-x-3 relative z-10">
                  {maintenanceLoading ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Zap className="w-5 h-5" />}
                  <span>{maintenanceLoading ? "Maintaining..." : "Run Maintenance"}</span>
                </div>
              </button>
              <button
                onClick={rebuildEmbeddings}
                disabled={rebuildLoading}
                className="px-6 py-4 bg-white/5 border border-white/10 text-white rounded-2xl font-bold transition-all hover:bg-white/10 disabled:opacity-50"
              >
                {rebuildLoading ? 'Rebuilding...' : 'Rebuild Embeddings'}
              </button>
              <button
                onClick={reindexDocuments}
                disabled={maintenanceLoading}
                className="px-6 py-4 bg-white/5 border border-white/10 text-white rounded-2xl font-bold transition-all hover:bg-white/10 disabled:opacity-50"
              >
                {maintenanceLoading ? 'Re-indexing...' : 'Re-index Documents'}
              </button>
              <button
                onClick={validateIntegrity}
                className="px-6 py-4 bg-white/5 border border-white/10 text-white rounded-2xl font-bold transition-all hover:bg-white/10"
              >
                Validate Integrity
              </button>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-6">
            <div className="glass p-6 rounded-2xl space-y-4">
              <div className="p-3 bg-blue-500/10 text-blue-400 rounded-xl w-fit">
                <Brain className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <h4 className="font-bold text-sm uppercase tracking-widest text-white/80">Synthesis</h4>
                <p className="text-xs text-white/30 leading-relaxed">Extracting core concepts from raw sources into structured markdown.</p>
              </div>
            </div>
            <div className="glass p-6 rounded-2xl space-y-4">
              <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-xl w-fit">
                <RefreshCw className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <h4 className="font-bold text-sm uppercase tracking-widest text-white/80">Evolution</h4>
                <p className="text-xs text-white/30 leading-relaxed">Updating existing pages as new information arrives. No amnesia.</p>
              </div>
            </div>
            <div className="glass p-6 rounded-2xl space-y-4">
              <div className="p-3 bg-violet-500/10 text-violet-400 rounded-xl w-fit">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <h4 className="font-bold text-sm uppercase tracking-widest text-white/80">Governance</h4>
                <p className="text-xs text-white/30 leading-relaxed">Maintaining schema integrity and knowledge persistence over time.</p>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center space-x-3 text-white/40">
              <Terminal className="w-4 h-4" />
              <h3 className="text-xs font-bold uppercase tracking-widest">Compilation Log</h3>
            </div>
            <div className="bg-[#0a0c12] border border-white/5 rounded-2xl p-6 font-mono text-xs text-white/50 h-[400px] overflow-y-auto custom-scrollbar leading-loose">
              {maintenanceLog ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{maintenanceLog}</ReactMarkdown>
              ) : (
                <p className="italic opacity-30">No maintenance runs recorded yet.</p>
              )}
            </div>
          </div>

          {integrityResult && (
            <div className="glass p-5 rounded-2xl space-y-3">
              <h4 className="text-sm font-bold text-white">Integrity Snapshot</h4>
              <p className="text-xs text-white/50">Missing: {integrityResult.missing?.length || 0} • Broken Links: {integrityResult.broken_links?.length || 0} • Embeddings Present: {integrityResult.embeddings_present ? 'Yes' : 'No'}</p>
            </div>
          )}
        </div>
      ) : (
        /* Librarian / Lint Tab */
        <div className="space-y-8">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-3xl font-bold tracking-tight">The Librarian</h2>
              <p className="text-white/40 mt-1">Wiki health check — find broken links, orphans, conflicts, and more.</p>
            </div>
            <button onClick={runLint} disabled={lintLoading}
              className="px-6 py-3 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 rounded-xl text-sm font-bold transition-all disabled:opacity-50 flex items-center space-x-2">
              {lintLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              <span>{lintLoading ? 'Scanning...' : 'Run Lint'}</span>
            </button>
          </div>

          {lintResults && (
            <div className="space-y-6 animate-in slide-in-from-bottom-4 duration-500">
              {/* Summary */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'Total Pages', value: lintResults.total_pages, color: 'text-white' },
                  { label: 'Broken Links', value: lintResults.broken_links.length, color: lintResults.broken_links.length > 0 ? 'text-red-400' : 'text-emerald-400' },
                  { label: 'Orphans', value: lintResults.orphan_pages.length, color: lintResults.orphan_pages.length > 0 ? 'text-amber-400' : 'text-emerald-400' },
                  { label: 'Conflicts', value: lintResults.conflicting_pages.length, color: lintResults.conflicting_pages.length > 0 ? 'text-red-400' : 'text-emerald-400' },
                ].map((stat, i) => (
                  <div key={i} className="bg-white/[0.03] p-4 rounded-xl border border-white/5 text-center">
                    <p className={`text-2xl font-black ${stat.color}`}>{stat.value}</p>
                    <p className="text-[10px] uppercase tracking-widest text-white/30 font-bold mt-1">{stat.label}</p>
                  </div>
                ))}
              </div>

              {/* Broken Links */}
              {lintResults.broken_links.length > 0 && (
                <div className="glass p-5 rounded-2xl space-y-3">
                  <div className="flex items-center space-x-2 text-red-400">
                    <Link2 className="w-4 h-4" />
                    <h4 className="text-sm font-bold">Broken Links</h4>
                  </div>
                  {lintResults.broken_links.map((bl, i) => (
                    <div key={i} className="flex items-center justify-between py-2 px-3 bg-white/[0.02] rounded-lg text-sm">
                      <span className="text-white/60">{bl.source} → <span className="text-red-400/80">[[{bl.target}]]</span></span>
                      <span className="text-[10px] text-white/30">{bl.suggestion}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Orphan Pages */}
              {lintResults.orphan_pages.length > 0 && (
                <div className="glass p-5 rounded-2xl space-y-3">
                  <div className="flex items-center space-x-2 text-amber-400">
                    <FileX className="w-4 h-4" />
                    <h4 className="text-sm font-bold">Orphan Pages</h4>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {lintResults.orphan_pages.map((p, i) => (
                      <span key={i} className="px-3 py-1.5 bg-amber-500/10 text-amber-400 rounded-lg text-xs font-medium">{p}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* All clear */}
              {lintResults.broken_links.length === 0 && lintResults.orphan_pages.length === 0 && lintResults.conflicting_pages.length === 0 && (
                <div className="text-center py-16 space-y-4">
                  <div className="text-6xl">✨</div>
                  <p className="text-white/60 text-lg font-medium">Wiki is healthy — no issues found.</p>
                </div>
              )}
            </div>
          )}

          {!lintResults && !lintLoading && (
            <div className="text-center py-24 space-y-4 opacity-40">
              <Search className="w-12 h-12 mx-auto text-white/30" />
              <p className="text-white/40">Run a lint check to analyze your wiki's health.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default MeditationView;
