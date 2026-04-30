import React, { useState } from 'react';
import { Activity, Wind, X, RefreshCw, BookOpen, AlertTriangle, Link2, FileX, FileWarning, Search } from 'lucide-react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = "http://localhost:8000";

interface MeditationViewProps {
  pages: string[];
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

const MeditationView: React.FC<MeditationViewProps> = ({ pages, selectedModel }) => {
  const [isActive, setIsActive] = useState(false);
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [lintResults, setLintResults] = useState<LintResults | null>(null);
  const [lintLoading, setLintLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'focus' | 'lint'>('focus');

  const startMeditation = async () => {
    if (pages.length === 0) return;
    setLoading(true);
    const randomPage = pages[Math.floor(Math.random() * pages.length)];
    try {
      const response = await axios.get(`${API_BASE}/wiki/${randomPage}`);
      const cleanContent = response.data.content.replace(/^---[\s\S]*?---/, '').trim();
      setContent(cleanContent);
      setSelectedPage(randomPage);
      setIsActive(true);
    } catch (error) {
      console.error("Meditation error:", error);
    } finally {
      setLoading(false);
    }
  };

  const endMeditation = () => {
    setIsActive(false);
    setSelectedPage(null);
    setContent('');
  };

  const runLint = async () => {
    setLintLoading(true);
    try {
      const response = await axios.post(`${API_BASE}/lint?model=${selectedModel}`);
      setLintResults(response.data);
    } catch (error) {
      console.error("Lint error:", error);
    } finally {
      setLintLoading(false);
    }
  };

  // Full-screen meditation mode
  if (isActive && selectedPage) {
    return (
      <div className="fixed inset-0 z-[100] bg-[#05070a] flex flex-col items-center animate-in fade-in duration-1000">
        <div className="w-full h-1 bg-primary/20">
          <div className="h-full bg-primary animate-[meditation-progress_60s_linear_infinite]"></div>
        </div>
        <header className="w-full max-w-4xl flex justify-between items-center p-8 opacity-40 hover:opacity-100 transition-opacity">
          <div className="flex items-center space-x-2">
            <RefreshCw className={`w-4 h-4 cursor-pointer hover:rotate-180 transition-transform duration-500 ${loading ? 'animate-spin' : ''}`} onClick={startMeditation} />
            <span className="text-[10px] uppercase tracking-widest font-bold">Deep Focus: {selectedPage.replace('.md', '')}</span>
          </div>
          <button onClick={endMeditation} className="p-2 hover:bg-white/5 rounded-full transition-colors">
            <X className="w-5 h-5" />
          </button>
        </header>
        <main className="flex-1 w-full max-w-2xl overflow-y-auto custom-scrollbar p-12 space-y-12 pb-32">
          <div className="flex flex-col items-center space-y-8 py-12">
            <div className="w-1 bg-gradient-to-b from-primary/50 to-transparent h-16 rounded-full"></div>
            <h2 className="text-4xl font-light tracking-widest uppercase text-center text-white/80">
              {selectedPage.replace('.md', '')}
            </h2>
          </div>
          <div className="prose prose-invert max-w-none prose-p:text-xl prose-p:leading-relaxed prose-p:font-light prose-p:text-white/60 prose-headings:text-white/80 prose-headings:font-light prose-headings:tracking-widest prose-strong:text-primary prose-strong:font-medium animate-in slide-in-from-bottom-8 duration-1000">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        </main>
        <footer className="fixed bottom-0 left-0 right-0 p-12 flex flex-col items-center space-y-6 bg-gradient-to-t from-[#05070a] to-transparent">
          <div className="flex items-center space-x-4">
            <div className="w-3 h-3 rounded-full bg-primary animate-ping"></div>
            <span className="text-[10px] uppercase tracking-[0.4em] font-bold text-white/30">Just Breathe</span>
          </div>
        </footer>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto animate-in fade-in duration-500">
      {/* Tab Bar */}
      <div className="flex items-center space-x-1 mb-10 bg-white/[0.03] p-1 rounded-2xl border border-white/5 w-fit">
        <button onClick={() => setActiveTab('focus')}
          className={`px-6 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all ${
            activeTab === 'focus' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/60'
          }`}>
          Deep Focus
        </button>
        <button onClick={() => setActiveTab('lint')}
          className={`px-6 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all ${
            activeTab === 'lint' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/60'
          }`}>
          Librarian
        </button>
      </div>

      {activeTab === 'focus' ? (
        /* Deep Focus Tab */
        <div className="flex flex-col items-center justify-center space-y-12 min-h-[60vh]">
          <div className="relative group">
            <div className="absolute inset-0 bg-primary/20 rounded-full blur-[80px] animate-pulse group-hover:bg-primary/40 transition-colors"></div>
            <div className="relative w-56 h-56 rounded-full border border-primary/20 flex items-center justify-center backdrop-blur-3xl">
              <Activity className="w-16 h-16 text-primary animate-pulse" />
            </div>
          </div>
          <div className="text-center space-y-6 max-w-md">
            <div className="space-y-2">
              <h2 className="text-3xl font-light tracking-[0.3em] uppercase text-white/90">Deep Focus</h2>
              <div className="h-0.5 w-12 bg-primary/40 mx-auto rounded-full"></div>
            </div>
            <p className="text-white/40 leading-relaxed text-sm tracking-wide">
              Enter a minimalist environment for deep absorption. A random topic from your knowledge base in a distraction-free view.
            </p>
            <button onClick={startMeditation} disabled={loading || pages.length === 0}
              className="group relative px-12 py-4 rounded-full overflow-hidden transition-all duration-500 hover:scale-105 active:scale-95 disabled:opacity-50">
              <div className="absolute inset-0 bg-primary/10 group-hover:bg-primary/20 transition-colors"></div>
              <div className="absolute inset-0 border border-primary/30 rounded-full"></div>
              <span className="relative text-xs tracking-[0.3em] uppercase font-bold">
                {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : "Begin Session"}
              </span>
            </button>
          </div>
          <div className="grid grid-cols-3 gap-8 opacity-20">
            <div className="flex flex-col items-center space-y-2">
              <Wind className="w-5 h-5" />
              <span className="text-[8px] uppercase tracking-widest">Minimalist</span>
            </div>
            <div className="flex flex-col items-center space-y-2">
              <BookOpen className="w-5 h-5" />
              <span className="text-[8px] uppercase tracking-widest">Focused</span>
            </div>
            <div className="flex flex-col items-center space-y-2">
              <Activity className="w-5 h-5" />
              <span className="text-[8px] uppercase tracking-widest">Absorb</span>
            </div>
          </div>
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

              {/* Oversized */}
              {lintResults.oversized_pages.length > 0 && (
                <div className="glass p-5 rounded-2xl space-y-3">
                  <div className="flex items-center space-x-2 text-violet-400">
                    <FileWarning className="w-4 h-4" />
                    <h4 className="text-sm font-bold">Oversized Pages (&gt;1000 words)</h4>
                  </div>
                  {lintResults.oversized_pages.map((p, i) => (
                    <div key={i} className="flex items-center justify-between py-2 px-3 bg-white/[0.02] rounded-lg text-sm">
                      <span className="text-white/60">{p.page}</span>
                      <span className="text-violet-400/60 text-xs font-mono">{p.word_count} words</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Suggestions */}
              {lintResults.suggestions.length > 0 && (
                <div className="glass p-5 rounded-2xl space-y-3">
                  <div className="flex items-center space-x-2 text-primary">
                    <AlertTriangle className="w-4 h-4" />
                    <h4 className="text-sm font-bold">Suggestions</h4>
                  </div>
                  <ul className="space-y-2">
                    {lintResults.suggestions.map((s, i) => (
                      <li key={i} className="text-sm text-white/50 flex items-start space-x-2">
                        <span className="text-primary/60 mt-1">•</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* All clear */}
              {lintResults.broken_links.length === 0 && lintResults.orphan_pages.length === 0 && lintResults.conflicting_pages.length === 0 && lintResults.suggestions.length === 0 && (
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
