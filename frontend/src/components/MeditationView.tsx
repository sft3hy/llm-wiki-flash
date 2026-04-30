import React, { useState, useEffect } from 'react';
import { Activity, Wind, X, RefreshCw, BookOpen } from 'lucide-react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = "http://localhost:8000";

interface MeditationViewProps {
  pages: string[];
}

const MeditationView: React.FC<MeditationViewProps> = ({ pages }) => {
  const [isActive, setIsActive] = useState(false);
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const startMeditation = async () => {
    if (pages.length === 0) return;
    setLoading(true);
    const randomPage = pages[Math.floor(Math.random() * pages.length)];
    try {
      const response = await axios.get(`${API_BASE}/wiki/${randomPage}`);
      // Remove frontmatter for meditation
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

          <div className="prose prose-invert max-w-none 
            prose-p:text-xl prose-p:leading-relaxed prose-p:font-light prose-p:text-white/60
            prose-headings:text-white/80 prose-headings:font-light prose-headings:tracking-widest
            prose-strong:text-primary prose-strong:font-medium
            animate-in slide-in-from-bottom-8 duration-1000
            ">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
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
    <div className="h-full flex flex-col items-center justify-center space-y-12 animate-in fade-in duration-1000">
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
          Enter a minimalist environment designed for deep absorption. We'll present a random topic from your knowledge base in a distraction-free view.
        </p>
        <button 
          onClick={startMeditation}
          disabled={loading || pages.length === 0}
          className="group relative px-12 py-4 rounded-full overflow-hidden transition-all duration-500 hover:scale-105 active:scale-95 disabled:opacity-50"
        >
          <div className="absolute inset-0 bg-primary/10 group-hover:bg-primary/20 transition-colors"></div>
          <div className="absolute inset-0 border border-primary/30 rounded-full"></div>
          <span className="relative text-xs tracking-[0.3em] uppercase font-bold flex items-center justify-center">
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
  );
};

export default MeditationView;

