import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { Book, FileText, Search, Settings, Share2, Upload, MessageSquare, Activity, LayoutGrid, Info } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import matter from 'gray-matter';
import KnowledgeGraph from './components/KnowledgeGraph';
import ChatView from './components/ChatView';
import SettingsView from './components/SettingsView';
import MeditationView from './components/MeditationView';

const API_BASE = "http://localhost:8000";

type ViewType = 'wiki' | 'chat' | 'settings' | 'meditation' | 'graph' | 'comparison';

function App() {
  const [wikiPages, setWikiPages] = useState<string[]>([]);
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const [pageContent, setPageContent] = useState<string>("");
  const [isIngesting, setIsIngesting] = useState(false);
  const [activeView, setActiveView] = useState<ViewType>('wiki');
  const [comparisonResults, setComparisonResults] = useState<any[]>([]);
  const [ingestProgress, setIngestProgress] = useState<{message: string, progress: number, status: string} | null>(null);

  useEffect(() => {
    fetchWikiPages();
  }, []);

  const fetchWikiPages = async () => {
    try {
      const response = await axios.get(`${API_BASE}/wiki`);
      setWikiPages(response.data);
    } catch (error) {
      console.error("Error fetching wiki pages:", error);
    }
  };

  const fetchPageContent = async (filename: string) => {
    try {
      const response = await axios.get(`${API_BASE}/wiki/${filename}`);
      setPageContent(response.data.content);
      setSelectedPage(filename);
      setActiveView('wiki');
    } catch (error) {
      console.error("Error fetching page content:", error);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsIngesting(true);
    const formData = new FormData();
    formData.append('file', file);

    // Start SSE listener
    const eventSource = new EventSource(`${API_BASE}/progress`);
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setIngestProgress(data);
      if (data.status === 'success') {
        eventSource.close();
        setTimeout(() => setIngestProgress(null), 2000);
      }
    };

    try {
      await axios.post(`${API_BASE}/ingest`, formData);
      await fetchWikiPages();
    } catch (error) {
      console.error("Error uploading file:", error);
      alert("Ingestion failed.");
      eventSource.close();
      setIngestProgress(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const handleCompare = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setIsIngesting(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${API_BASE}/compare`, formData);
      setComparisonResults(response.data.results);
      setActiveView('comparison');
    } catch (error) {
      console.error("Error comparing models:", error);
      alert("Comparison failed.");
    } finally {
      setIsIngesting(false);
    }
  };

  // Parse frontmatter and content
  const { data: metadata, content: markdown } = useMemo(() => {
    try {
      // gray-matter might need some polyfills or a browser build. 
      // If it fails, we fallback to simple extraction
      if (pageContent.startsWith('---')) {
        const parts = pageContent.split('---');
        if (parts.length >= 3) {
          // Simple mock parsing for demonstration if matter fails
          // In a real app we'd use a robust browser parser
          return { data: {}, content: parts.slice(2).join('---').trim() };
        }
      }
      return { data: {}, content: pageContent };
    } catch (e) {
      return { data: {}, content: pageContent };
    }
  }, [pageContent]);

  return (
    <div className="flex h-screen bg-[#05070a] text-[#e2e8f0] font-sans overflow-hidden">
      {/* Sidebar */}
      <aside className="w-72 bg-[#0a0c12]/80 backdrop-blur-xl border-r border-white/5 flex flex-col p-6 space-y-6 z-20 shadow-2xl">
        <div className="flex items-center space-x-3 px-2">
          <div className="w-10 h-10 bg-gradient-to-br from-primary to-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-primary/20">
            <Book className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent">LLM Wiki</h1>
        </div>
        
        <div className="flex-1 space-y-8 overflow-y-auto custom-scrollbar pr-2">
          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/30 px-3">Knowledge base</p>
            <nav className="space-y-1">
              {wikiPages.map((page) => (
                <button
                  key={page}
                  onClick={() => fetchPageContent(page)}
                  className={`w-full text-left px-3 py-2.5 rounded-xl transition-all duration-300 flex items-center space-x-3 group ${
                    selectedPage === page && activeView === 'wiki'
                    ? "bg-primary/10 text-primary border border-primary/20 shadow-[0_0_20px_rgba(var(--primary),0.1)]" 
                    : "hover:bg-white/5 text-white/60 hover:text-white"
                  }`}
                >
                  <FileText className={`w-4 h-4 transition-transform duration-300 ${selectedPage === page ? "scale-110" : "group-hover:scale-110"}`} />
                  <span className="truncate text-sm font-medium">{page.replace('.md', '')}</span>
                </button>
              ))}
            </nav>
          </div>

          <div className="space-y-2 pt-4 border-t border-white/5">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/30 px-3">Exploration</p>
            <div className="space-y-1">
              <button 
                onClick={() => setActiveView('graph')}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl transition-all ${activeView === 'graph' ? "bg-primary/10 text-primary border border-primary/20" : "hover:bg-white/5 text-white/60"}`}
              >
                <LayoutGrid className="w-4 h-4" />
                <span className="text-sm font-medium">Graph View</span>
              </button>
              <button 
                onClick={() => setActiveView('meditation')}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl transition-all ${activeView === 'meditation' ? "bg-primary/10 text-primary border border-primary/20" : "hover:bg-white/5 text-white/60"}`}
              >
                <Activity className="w-4 h-4" />
                <span className="text-sm font-medium">Meditation</span>
              </button>
            </div>
          </div>
        </div>

        <div className="pt-6 border-t border-white/5 space-y-3">
          <label className="flex items-center space-x-3 px-3 py-3 rounded-xl bg-white/5 hover:bg-white/10 cursor-pointer transition-all border border-white/5 group">
            <div className={`p-1.5 rounded-lg bg-primary/10 text-primary group-hover:scale-110 transition-transform ${isIngesting ? "animate-pulse" : ""}`}>
              <Upload className="w-4 h-4" />
            </div>
            <span className="text-xs font-semibold tracking-wide">Upload Source</span>
            <input type="file" className="hidden" onChange={handleFileUpload} disabled={isIngesting} />
          </label>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 bg-[#05070a] relative">
        <header className="h-20 flex items-center justify-between px-10 border-b border-white/5 bg-[#05070a]/50 backdrop-blur-md z-10">
          <div className="flex items-center space-x-4 bg-white/5 px-4 py-2 rounded-2xl border border-white/5 w-full max-w-xl group focus-within:border-primary/30 transition-all">
            <Search className="w-4 h-4 text-white/30 group-focus-within:text-primary transition-colors" />
            <input 
              type="text" 
              placeholder="Search through knowledge..." 
              className="bg-transparent border-none focus:ring-0 text-sm w-full outline-none placeholder:text-white/20"
            />
          </div>
          <div className="flex items-center space-x-3">
             <button 
               onClick={() => setActiveView('chat')}
               className={`p-3 rounded-xl transition-all ${activeView === 'chat' ? "bg-primary text-white shadow-lg shadow-primary/20" : "bg-white/5 hover:bg-white/10 text-white/60"}`}
             >
               <MessageSquare className="w-5 h-5" />
             </button>
             <button 
               onClick={() => setActiveView('settings')}
               className={`p-3 rounded-xl transition-all ${activeView === 'settings' ? "bg-primary text-white shadow-lg shadow-primary/20" : "bg-white/5 hover:bg-white/10 text-white/60"}`}
             >
               <Settings className="w-5 h-5" />
             </button>
             <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 to-blue-600 flex items-center justify-center text-white text-xs font-black shadow-xl border border-white/10 ml-2 cursor-pointer hover:scale-105 transition-transform">
               ST
             </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-10 relative custom-scrollbar">
          {activeView === 'graph' ? (
            <div className="h-full rounded-3xl overflow-hidden border border-white/5 bg-[#0a0c12]/50">
              <KnowledgeGraph pages={wikiPages} onNodeClick={(node) => { fetchPageContent(node.id); }} />
            </div>
          ) : activeView === 'chat' ? (
            <ChatView />
          ) : activeView === 'settings' ? (
            <SettingsView />
          ) : activeView === 'meditation' ? (
            <MeditationView pages={wikiPages} />
          ) : activeView === 'comparison' ? (
            <div className="max-w-4xl mx-auto space-y-8 animate-in slide-in-from-bottom-4 duration-500">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-3xl font-bold tracking-tight">Model Comparison</h2>
                  <p className="text-white/40 mt-1">Analyzing ingestion performance across providers.</p>
                </div>
                <button 
                  onClick={() => setActiveView('wiki')}
                  className="px-6 py-2.5 bg-white/5 hover:bg-white/10 text-white border border-white/10 rounded-xl text-sm font-medium transition-all"
                >
                  Back to Wiki
                </button>
              </div>
              <div className="grid gap-4">
                {comparisonResults.map((result, i) => (
                  <div key={i} className="bg-[#0a0c12] p-6 rounded-2xl flex items-center justify-between border border-white/5 hover:border-primary/30 transition-all group">
                    <div className="flex items-center space-x-4">
                      <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center text-primary group-hover:scale-110 transition-transform">
                        <Share2 className="w-6 h-6" />
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold text-white">{result.model}</h3>
                        <p className="text-sm text-white/40">{result.provider} • <span className="text-green-500/80">{result.status}</span></p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-3xl font-mono font-bold text-white tracking-tighter">{result.latency}s</p>
                      <p className="text-[10px] uppercase tracking-[0.2em] text-white/30 font-black">Latency</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : selectedPage ? (
            <div className="max-w-4xl mx-auto animate-in fade-in duration-700">
              <div className="flex items-start justify-between mb-12">
                <div className="space-y-2">
                  <h2 className="text-5xl font-black tracking-tight bg-gradient-to-b from-white to-white/40 bg-clip-text text-transparent py-1">
                    {selectedPage.replace('.md', '')}
                  </h2>
                  <div className="flex items-center space-x-4 text-xs font-bold uppercase tracking-widest text-white/30">
                    <span className="flex items-center space-x-1.5">
                      <Activity className="w-3 h-3" />
                      <span>Updated 2026-04-29</span>
                    </span>
                    <span className="w-1 h-1 rounded-full bg-white/20"></span>
                    <span className="flex items-center space-x-1.5 text-primary/80">
                      <Info className="w-3 h-3" />
                      <span>High Confidence</span>
                    </span>
                  </div>
                </div>
              </div>
              
              <div className="prose prose-invert max-w-none 
                prose-headings:font-black prose-headings:tracking-tight prose-headings:text-white
                prose-p:text-white/70 prose-p:leading-relaxed prose-p:text-lg
                prose-li:text-white/70 prose-li:text-lg
                prose-strong:text-white prose-strong:font-bold
                prose-code:text-primary prose-code:bg-primary/5 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:before:content-none prose-code:after:content-none
                prose-pre:bg-[#0a0c12] prose-pre:border prose-pre:border-white/5 prose-pre:rounded-2xl
                prose-blockquote:border-l-primary prose-blockquote:bg-primary/5 prose-blockquote:py-1 prose-blockquote:px-6 prose-blockquote:rounded-r-2xl prose-blockquote:italic
                ">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {markdown}
                </ReactMarkdown>
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center space-y-8 animate-in fade-in zoom-in duration-1000">
              <div className="relative">
                <div className="absolute inset-0 bg-primary/20 rounded-full blur-[100px] animate-pulse"></div>
                <Book className="w-24 h-24 text-primary/40 relative" />
              </div>
              <div className="space-y-2">
                <p className="text-2xl font-bold tracking-tight text-white">Select a page to begin</p>
                <p className="text-white/30 max-w-xs mx-auto">Your personal knowledge graph is ready for exploration.</p>
              </div>
              <div className="flex space-x-3 pt-4">
                <div className="px-4 py-2 rounded-full bg-white/5 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-white/40">Markdown Support</div>
                <div className="px-4 py-2 rounded-full bg-white/5 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-white/40">AI Powered</div>
                <div className="px-4 py-2 rounded-full bg-white/5 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-white/40">Local First</div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Progress Modal */}
      {ingestProgress && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[#05070a]/80 backdrop-blur-xl">
          <div className="bg-[#0a0c12] p-10 rounded-[2.5rem] w-[450px] shadow-[0_0_100px_rgba(0,0,0,0.5)] border border-white/10 animate-in fade-in zoom-in duration-500">
            <div className="flex flex-col items-center space-y-8">
              <div className="relative">
                <div className="absolute inset-0 bg-primary/20 rounded-full blur-2xl animate-pulse"></div>
                <div className="w-20 h-20 rounded-[2rem] bg-gradient-to-br from-primary to-blue-600 flex items-center justify-center shadow-2xl relative">
                  <Activity className={`w-10 h-10 text-white ${ingestProgress.status === 'processing' ? 'animate-spin' : ''}`} />
                </div>
              </div>
              <div className="text-center space-y-3">
                <h3 className="text-2xl font-black tracking-tight text-white">Ingesting Knowledge</h3>
                <p className="text-sm text-white/40 leading-relaxed font-medium">{ingestProgress.message}</p>
              </div>
              <div className="w-full space-y-4">
                <div className="w-full bg-white/5 rounded-full h-3 overflow-hidden border border-white/5 p-0.5">
                  <div 
                    className="bg-gradient-to-r from-primary to-blue-400 h-full rounded-full transition-all duration-700 ease-out shadow-[0_0_15px_rgba(var(--primary),0.5)]" 
                    style={{ width: `${ingestProgress.progress}%` }}
                  />
                </div>
                <div className="flex justify-between items-center px-1">
                  <span className="text-[10px] font-black uppercase tracking-widest text-white/20">Progress</span>
                  <span className="text-xs font-mono font-bold text-primary">{ingestProgress.progress}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;

