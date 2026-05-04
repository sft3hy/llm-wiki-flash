import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { Book, FileText, Search, Settings, Upload, MessageSquare, Activity, LayoutGrid, Info, Cpu, Cloud, Trash, Clock, Brain } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import KnowledgeGraph from './components/KnowledgeGraph';
import ChatView from './components/ChatView';
import SettingsView from './components/SettingsView';
import MeditationView from './components/MeditationView';
import ModelSelector from './components/ModelSelector';

const API_BASE = "http://localhost:8000";

type ViewType = 'wiki' | 'chat' | 'settings' | 'maintenance' | 'graph';

interface Model {
  model_id: string;
  display_name: string;
  provider: string;
  description: string;
}

function App() {
  const [wikiPages, setWikiPages] = useState<string[]>([]);
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const [pageContent, setPageContent] = useState<string>("");
  const [isIngesting, setIsIngesting] = useState(false);
  const [activeView, setActiveView] = useState<ViewType>('wiki');

  const [ingestProgress, setIngestProgress] = useState<{message: string, progress: number, status: string} | null>(null);
  const [ingestionStartTime, setIngestionStartTime] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Model state
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [groqConfigured, setGroqConfigured] = useState(false);

  useEffect(() => {
    fetchWikiPages();
    fetchModels();
  }, []);

  const fetchModels = async () => {
    try {
      const response = await axios.get(`${API_BASE}/models`);
      setModels(response.data.models);
      setGroqConfigured(response.data.groq_configured);
      // Restore from localStorage or use default
      const stored = localStorage.getItem('llm-wiki-model');
      if (stored && response.data.models.find((m: Model) => m.model_id === stored)) {
        setSelectedModel(stored);
      } else {
        setSelectedModel(response.data.default);
      }
    } catch (error) {
      console.error("Error fetching models:", error);
      // Fallback defaults
      setSelectedModel('gemma4:e4b');
    }
  };

  const handleModelChange = (modelId: string) => {
    setSelectedModel(modelId);
    localStorage.setItem('llm-wiki-model', modelId);
  };

  useEffect(() => {
    // Persistent Progress Listener
    const eventSource = new EventSource(`${API_BASE}/progress`);
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setIngestProgress(data);
        
        if (data.status === 'processing') {
          setIsIngesting(true);
        } else if (data.status === 'success') {
          // Success! Keep progress visible for 3s then hide
          setTimeout(() => {
            setIngestProgress(null);
            setIsIngesting(false);
          }, 3000);
        } else {
          setIsIngesting(false);
        }
      } catch (err) {
        console.error("Failed to parse progress data:", err);
      }
    };

    return () => eventSource.close();
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

    const formData = new FormData();
    formData.append('file', file);

    try {
      await axios.post(`${API_BASE}/ingest?model=${selectedModel}`, formData);
      await fetchWikiPages();
    } catch (error) {
      console.error("Error uploading file:", error);
      alert("Ingestion failed.");
    }
  };

  // Poll for new pages during ingestion so the sidebar stays current
  useEffect(() => {
    let interval: any;
    if (isIngesting) {
      interval = setInterval(() => {
        fetchWikiPages();
      }, 5000);
    }
    return () => clearInterval(interval);
  }, [isIngesting]);

  const calculateETE = () => {
    if (!ingestionStartTime || !ingestProgress || ingestProgress.progress === 0) return null;
    const elapsed = (Date.now() - ingestionStartTime) / 1000;
    const rate = ingestProgress.progress / elapsed;
    const remaining = (100 - ingestProgress.progress) / rate;
    
    if (remaining < 1) return "Few seconds...";
    if (remaining > 3600) return "Over an hour...";
    
    const mins = Math.floor(remaining / 60);
    const secs = Math.floor(remaining % 60);
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  };

  const handleDeletePage = async (filename: string) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}"? This action cannot be undone.`)) {
      return;
    }

    try {
      await axios.delete(`${API_BASE}/wiki/${filename}`);
      await fetchWikiPages();
      setSelectedPage(null);
      setPageContent("");
    } catch (error) {
      console.error("Error deleting page:", error);
      alert("Failed to delete page.");
    }
  };


  // Parse frontmatter and content
  const { content: markdown } = useMemo(() => {
    try {
      if (pageContent.startsWith('---')) {
        const parts = pageContent.split('---');
        if (parts.length >= 3) {
          return { data: {}, content: parts.slice(2).join('---').trim() };
        }
      }
      return { data: {}, content: pageContent };
    } catch (e) {
      return { data: {}, content: pageContent };
    }
  }, [pageContent]);

  // Filter wiki pages by search
  const filteredPages = useMemo(() => {
    if (!searchQuery.trim()) return wikiPages;
    const q = searchQuery.toLowerCase();
    return wikiPages.filter(p => p.toLowerCase().includes(q));
  }, [wikiPages, searchQuery]);

  // Get current model info
  const currentModel = models.find(m => m.model_id === selectedModel);

  return (
    <div className="flex h-screen bg-[#05070a] text-[#e2e8f0] font-sans overflow-hidden">
      {/* Sidebar */}
      <aside className="w-72 bg-[#0a0c12]/80 backdrop-blur-xl border-r border-white/5 flex flex-col p-6 space-y-6 z-20 shadow-2xl">
        <div className="flex items-center space-x-3 px-2">
          <div className="w-10 h-10 bg-gradient-to-br from-primary to-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-primary/20">
            <Brain className="w-6 h-6 text-white" />
          </div>
          <div className="flex flex-col">
            <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent">Wiki Agent</h1>
            <span className="text-[8px] font-black uppercase tracking-[0.3em] text-primary/60">Karpathy Edition</span>
          </div>
        </div>
        
        <div className="flex-1 space-y-8 overflow-y-auto custom-scrollbar pr-2">
          <div className="space-y-2">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/30 px-3">Primary Focus</p>
            <nav className="space-y-1">
              <button 
                onClick={() => setActiveView('chat')}
                className={`w-full flex items-center space-x-3 px-3 py-3 rounded-xl transition-all duration-300 ${activeView === 'chat' ? "bg-primary text-black font-bold shadow-[0_0_20px_rgba(var(--primary),0.3)]" : "hover:bg-white/5 text-white/60"}`}
              >
                <MessageSquare className="w-4 h-4" />
                <span className="text-sm">Knowledge Chat</span>
              </button>
              <button 
                onClick={() => setActiveView('maintenance')}
                className={`w-full flex items-center space-x-3 px-3 py-3 rounded-xl transition-all duration-300 ${activeView === 'maintenance' ? "bg-primary text-black font-bold shadow-[0_0_20px_rgba(var(--primary),0.3)]" : "hover:bg-white/5 text-white/60"}`}
              >
                <Brain className="w-4 h-4" />
                <span className="text-sm">Maintenance</span>
              </button>
              <button 
                onClick={() => setActiveView('graph')}
                className={`w-full flex items-center space-x-3 px-3 py-3 rounded-xl transition-all duration-300 ${activeView === 'graph' ? "bg-primary text-black font-bold shadow-[0_0_20px_rgba(var(--primary),0.3)]" : "hover:bg-white/5 text-white/60"}`}
              >
                <LayoutGrid className="w-4 h-4" />
                <span className="text-sm">Graph View</span>
              </button>
            </nav>
          </div>

          <div className="space-y-2 pt-4 border-t border-white/5">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/30 px-3 flex justify-between items-center">
              <span>Knowledge Base</span>
              <span className="bg-white/5 px-1.5 py-0.5 rounded text-[8px]">{wikiPages.length}</span>
            </p>
            <nav className="space-y-1 max-h-[300px] overflow-y-auto custom-scrollbar">
              {filteredPages.map((page) => (
                <button
                  key={page}
                  onClick={() => fetchPageContent(page)}
                  className={`w-full text-left px-3 py-2 rounded-lg transition-all duration-300 flex items-center space-x-3 group ${
                    selectedPage === page && activeView === 'wiki'
                    ? "bg-white/10 text-white" 
                    : "hover:bg-white/5 text-white/40 hover:text-white"
                  }`}
                >
                  <FileText className={`w-3.5 h-3.5 opacity-40`} />
                  <span className="truncate text-xs font-medium">{page.replace('.md', '')}</span>
                </button>
              ))}
            </nav>
          </div>
        </div>

        <div className="pt-6 border-t border-white/5 space-y-3">
          <button 
            onClick={() => setActiveView('settings')}
            className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl transition-all ${activeView === 'settings' ? "bg-white/10 text-white border border-white/10" : "hover:bg-white/5 text-white/60"}`}
          >
            <Settings className="w-4 h-4" />
            <span className="text-sm font-medium">Settings</span>
          </button>
          
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
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent border-none focus:ring-0 text-sm w-full outline-none placeholder:text-white/20"
            />
          </div>
          <div className="flex items-center space-x-3">
             {/* Model Selector */}
             <ModelSelector
               models={models}
               selectedModel={selectedModel}
               onModelChange={handleModelChange}
               groqConfigured={groqConfigured}
             />
             <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 to-blue-600 flex items-center justify-center text-white text-xs font-black shadow-xl border border-white/10 ml-2 cursor-pointer hover:scale-105 transition-transform">
               ST
             </div>
          </div>
        </header>

        {/* Ingestion Bar (Non-blocking) */}
        {ingestProgress && (
          <div className="w-full bg-[#0a0c12]/80 backdrop-blur-md border-b border-white/5 overflow-hidden animate-in slide-in-from-top duration-500">
            <div className="max-w-6xl mx-auto px-10 py-3 flex items-center justify-between">
              <div className="flex items-center space-x-4 flex-1">
                <div className="relative">
                  <div className="absolute inset-0 bg-primary/20 rounded-full blur-md animate-pulse"></div>
                  <div className={`p-2 rounded-lg bg-primary/10 text-primary ${ingestProgress.status === 'processing' ? 'animate-spin' : ''}`}>
                    <Activity className="w-4 h-4" />
                  </div>
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-black uppercase tracking-[0.2em] text-white/30">Compiling Knowledge</span>
                  <span className="text-sm font-medium text-white/80 truncate max-w-[400px]">{ingestProgress.message}</span>
                </div>
              </div>

              <div className="flex items-center space-x-8">
                {/* Stats */}
                <div className="hidden md:flex items-center space-x-6">
                  {currentModel && (
                    <div className="flex flex-col items-end">
                      <span className="text-[9px] font-bold uppercase tracking-widest text-white/20">Engine</span>
                      <div className="flex items-center space-x-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full ${currentModel.provider === 'ollama' ? 'bg-emerald-500' : 'bg-violet-500'}`}></div>
                        <span className="text-xs font-semibold text-white/60">{currentModel.display_name}</span>
                      </div>
                    </div>
                  )}
                  <div className="flex flex-col items-end">
                    <span className="text-[9px] font-bold uppercase tracking-widest text-white/20">Time Remaining</span>
                    <div className="flex items-center space-x-1.5 text-primary/80">
                      <Clock className="w-3 h-3" />
                      <span className="text-xs font-mono font-bold">{calculateETE() || '--:--'}</span>
                    </div>
                  </div>
                </div>

                {/* Progress Circle/Percent */}
                <div className="flex items-center space-x-4 bg-white/5 pl-4 pr-1 py-1 rounded-full border border-white/5">
                  <span className="text-sm font-mono font-black text-primary">{ingestProgress.progress}%</span>
                  <div className="w-32 h-2 bg-white/5 rounded-full overflow-hidden p-0.5 border border-white/5">
                    <div 
                      className="h-full bg-gradient-to-r from-primary to-blue-400 rounded-full transition-all duration-1000 ease-out shadow-[0_0_10px_rgba(var(--primary),0.5)]"
                      style={{ width: `${ingestProgress.progress}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
            {/* Infinite loading line animation */}
            <div className="h-[1px] w-full bg-white/5 relative">
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-primary/50 to-transparent w-1/2 animate-[loading-shimmer_2s_infinite]"></div>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-10 relative custom-scrollbar">
          {activeView === 'graph' ? (
            <div className="h-full rounded-3xl overflow-hidden border border-white/5 bg-[#0a0c12]/50">
              <KnowledgeGraph pages={wikiPages} onNodeClick={(node) => { fetchPageContent(node.id); }} />
            </div>
          ) : activeView === 'chat' ? (
            <ChatView selectedModel={selectedModel} />
          ) : activeView === 'settings' ? (
            <SettingsView 
              models={models}
              selectedModel={selectedModel}
              onModelChange={handleModelChange}
              groqConfigured={groqConfigured}
              wikiPages={wikiPages}
            />
          ) : activeView === 'maintenance' ? (
            <MeditationView pages={wikiPages} selectedModel={selectedModel} />
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
                      <span>Wiki Page</span>
                    </span>
                    <span className="w-1 h-1 rounded-full bg-white/20"></span>
                    <span className="flex items-center space-x-1.5 text-primary/80">
                      <Info className="w-3 h-3" />
                      <span>Compiled</span>
                    </span>
                  </div>
                </div>
                {selectedPage && !['index.md', 'log.md', 'SCHEMA.md'].includes(selectedPage) && (
                  <button
                    onClick={() => handleDeletePage(selectedPage)}
                    className="p-3 bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20 rounded-xl transition-all group"
                    title="Delete Page"
                  >
                    <Trash className="w-5 h-5 group-hover:scale-110 transition-transform" />
                  </button>
                )}
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

    </div>
  );
}

export default App;
