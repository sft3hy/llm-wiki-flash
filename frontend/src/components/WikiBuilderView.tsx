import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FolderOpen,
  Info,
  Library,
  Link2,
  LoaderCircle,
  Search,
} from 'lucide-react';


const API_BASE = 'http://localhost:8000';


interface Model {
  model_id: string;
  display_name: string;
}

interface WikiBuilderViewProps {
  selectedModel: string;
  models: Model[];
  selectedWikiId: string;
  selectedWikiName: string;
  onWikiUpdated: (wikiId?: string) => Promise<void> | void;
}

interface BuilderProgressEvent {
  message: string;
  progress: number;
  status: string;
  channel?: string;
  stage?: string;
  topic?: string;
  wiki_id?: string;
  error?: string;
}

interface BuilderRunResult {
  topic: string;
  topic_slug: string;
  wiki_id: string;
  wiki_name: string;
  discovered_sources: number;
  fetched_sources: number;
  failed_sources: number;
  source_notes_written: number;
  concept_pages_written: number;
  raw_sources_dir: string;
  obsidian_sources_dir: string;
  obsidian_wiki_dir: string;
  log_path: string;
  warnings: string[];
}

interface BuilderOutputItem {
  name: string;
  title: string;
  url?: string;
  snippet?: string;
  retrieved_at?: string;
  last_updated?: string | null;
}

interface BuilderTopicData {
  topic: string;
  wiki_id: string;
  topic_slug: string;
  raw_sources_dir: string;
  sources_dir: string;
  wiki_dir: string;
  log_path: string;
  source_notes: BuilderOutputItem[];
  wiki_pages: BuilderOutputItem[];
}

const STAGES = [
  { key: 'search', label: 'Discover', description: 'Generate queries and dedupe sources.' },
  { key: 'fetch', label: 'Fetch', description: 'Download pages and store raw content.' },
  { key: 'parse', label: 'Parse', description: 'Extract the article body and metadata.' },
  { key: 'ingest', label: 'Ingest', description: 'Write source notes into the wiki folder.' },
  { key: 'generate', label: 'Generate', description: 'LLM builds concept pages and the index.' },
] as const;

const rewriteObsidianLinks = (content: string) =>
  content.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_match, rawTarget: string, rawLabel?: string) => {
    const target = rawTarget.trim();
    const label = (rawLabel || rawTarget).trim();
    if (target.startsWith('sources/')) {
      return `[${label}](source://${target.split('/')[1]})`;
    }
    return `[${label}](wiki://${target})`;
  });

const WikiBuilderView: React.FC<WikiBuilderViewProps> = ({
  selectedModel,
  models,
  selectedWikiId,
  selectedWikiName,
  onWikiUpdated,
}) => {
  const [topic, setTopic] = useState('');

  const [isRunning, setIsRunning] = useState(false);
  const [progressEvent, setProgressEvent] = useState<BuilderProgressEvent | null>(null);
  const [events, setEvents] = useState<Array<BuilderProgressEvent & { id: string }>>([]);
  const [result, setResult] = useState<BuilderRunResult | null>(null);
  const [topicData, setTopicData] = useState<BuilderTopicData | null>(null);
  const [selectedKind, setSelectedKind] = useState<'wiki' | 'source' | 'log'>('wiki');
  const [selectedName, setSelectedName] = useState('index.md');
  const [previewContent, setPreviewContent] = useState('');
  const [loadingTopic, setLoadingTopic] = useState(false);


  useEffect(() => {
    if (selectedWikiName) {
      setTopic(selectedWikiName);
    }
    setResult(null);
    setProgressEvent(null);
    setEvents([]);
    setPreviewContent('');
    setTopicData(null);
    if (selectedWikiId) {
      void loadTopicData(selectedWikiId, true);
    }
  }, [selectedWikiId, selectedWikiName]);

  useEffect(() => {
    const eventSource = new EventSource(`${API_BASE}/progress`);
    eventSource.onmessage = (event) => {
      try {
        const data: BuilderProgressEvent = JSON.parse(event.data);
        if (data.channel !== 'wiki_builder' || data.wiki_id !== selectedWikiId) {
          return;
        }
        setProgressEvent(data);
        setEvents((previous) => [...previous, { ...data, id: `${Date.now()}-${previous.length}` }].slice(-24));
        if (data.status === 'success' || data.status === 'error') {
          setIsRunning(false);
        }
      } catch (error) {
        console.error('Failed to parse builder progress event:', error);
      }
    };
    return () => eventSource.close();
  }, [selectedWikiId]);

  const loadContent = async (kind: 'wiki' | 'source' | 'log', name: string, wikiId = selectedWikiId) => {
    const response = await axios.get(`${API_BASE}/builder/content`, {
      params: {
        wiki_id: wikiId,
        kind,
        name,
      },
    });
    setSelectedKind(kind);
    setSelectedName(name);
    setPreviewContent(response.data.content);
  };

  const loadTopicData = async (wikiId = selectedWikiId, quiet = false) => {
    if (!wikiId) {
      return;
    }
    setLoadingTopic(true);
    try {
      const response = await axios.get(`${API_BASE}/builder/topic`, {
        params: { wiki_id: wikiId },
      });
      const data: BuilderTopicData = response.data;
      setTopicData(data);
      setTopic(data.topic);
      const defaultPage = data.wiki_pages.find((item) => item.name === 'index.md') || data.wiki_pages[0];
      if (defaultPage) {
        await loadContent('wiki', defaultPage.name, wikiId);
      } else if (data.source_notes[0]) {
        await loadContent('source', data.source_notes[0].name, wikiId);
      } else {
        setPreviewContent('');
      }
    } catch (error: any) {
      setTopicData(null);
      setPreviewContent('');
      if (!quiet && error?.response?.status !== 404) {
        console.error('Failed to load builder topic:', error);
        alert('Could not load the selected wiki builder workspace.');
      }
    } finally {
      setLoadingTopic(false);
    }
  };

  const handleRun = async () => {
    const trimmedTopic = topic.trim();
    if (!trimmedTopic) {
      alert('Please enter a research topic.');
      return;
    }

    setIsRunning(true);
    setProgressEvent(null);
    setEvents([]);
    setResult(null);
    setTopicData(null);
    setPreviewContent('');

    try {
      const response = await axios.post(`${API_BASE}/builder/run`, {
        topic: trimmedTopic,
        wiki_id: selectedWikiId,
        model: selectedModel,
      });
      const nextResult: BuilderRunResult = response.data;
      setResult(nextResult);
      await onWikiUpdated(selectedWikiId);
      await loadTopicData(selectedWikiId);
    } catch (error) {
      console.error('Wiki builder run failed:', error);
      alert('The wiki builder run failed. Check the live activity panel or pipeline log for details.');
      setIsRunning(false);
    }
  };

  const openInternalLink = async (href: string | undefined) => {
    if (!href) {
      return;
    }
    if (href.startsWith('wiki://')) {
      const rawName = href.replace('wiki://', '');
      await loadContent('wiki', rawName.endsWith('.md') ? rawName : `${rawName}.md`);
    } else if (href.startsWith('source://')) {
      const rawName = href.replace('source://', '');
      await loadContent('source', rawName.endsWith('.md') ? rawName : `${rawName}.md`);
    } else if (!href.startsWith('http://') && !href.startsWith('https://') && !href.startsWith('#') && !href.startsWith('mailto:') && !href.startsWith('tel:')) {
      await loadContent('wiki', href.endsWith('.md') ? href : `${href}.md`);
    } else {
      window.open(href, '_blank', 'noopener,noreferrer');
    }
  };

  const previewMarkdown = useMemo(() => rewriteObsidianLinks(previewContent), [previewContent]);
  const currentStageIndex = progressEvent?.stage ? STAGES.findIndex((stage) => stage.key === progressEvent.stage) : -1;

  const previewTitle = useMemo(() => {
    if (selectedKind === 'log') {
      return 'Pipeline Log';
    }
    const collection = selectedKind === 'wiki' ? topicData?.wiki_pages : topicData?.source_notes;
    return collection?.find((item) => item.name === selectedName)?.title || selectedName;
  }, [selectedKind, selectedName, topicData]);

  return (
    <div className="mx-auto max-w-7xl space-y-8 animate-in fade-in duration-500">
      <section className="relative overflow-hidden rounded-[2rem] border border-white/10 bg-[radial-gradient(circle_at_top_left,_rgba(148,163,184,0.12),_transparent_35%),linear-gradient(145deg,rgba(10,12,18,0.92),rgba(7,10,16,0.96))] p-8 shadow-2xl">
        <div className="absolute inset-y-0 right-0 w-1/3 bg-[radial-gradient(circle_at_center,_rgba(96,165,250,0.12),_transparent_60%)]" />
        <div className="relative grid gap-8 xl:grid-cols-[1.15fr_0.85fr]">
          <div className="space-y-6">
            <div className="space-y-3">
              <div className="inline-flex items-center space-x-2 rounded-full border border-sky-400/20 bg-sky-400/10 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.24em] text-sky-200/80">
                <Activity className="h-3 w-3" />
                <span>Wiki Builder</span>
              </div>
              <h2 className="text-4xl font-black tracking-tight text-white">Research a specific topic, then review what the system builds.</h2>
              <p className="max-w-2xl text-sm leading-7 text-white/55">
                This pipeline writes sources, concept pages, and embeddings into the <span className="font-semibold text-white">{selectedWikiName}</span> Wiki. Nothing spills into other wikis.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-2">
                <span className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/35">Research Topic</span>
                <input
                  type="text"
                  value={topic}
                  onChange={(event) => setTopic(event.target.value)}
                  placeholder="Roman aqueducts, Oahu travel, local-first CRDTs..."
                  className="w-full rounded-2xl border border-white/10 bg-black/30 px-4 py-3 text-sm text-white outline-none transition-colors focus:border-sky-400/40"
                  disabled={isRunning}
                />
              </label>
              <div className="space-y-2">
                <span className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/35">Target Wiki</span>
                <div className="rounded-2xl border border-white/10 bg-black/30 px-4 py-3 text-sm text-white/85">
                  {selectedWikiName}
                  <div className="mt-1 text-[11px] uppercase tracking-[0.16em] text-white/30">{selectedWikiId}</div>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={handleRun}
                disabled={isRunning}
                className={`inline-flex items-center space-x-2 rounded-2xl px-5 py-3 text-sm font-bold transition-all ${isRunning
                  ? 'cursor-not-allowed bg-white/10 text-white/30'
                  : 'bg-sky-400 text-slate-950 shadow-[0_10px_40px_rgba(56,189,248,0.25)] hover:-translate-y-0.5'
                  }`}
              >
                {isRunning ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                <span>{isRunning ? 'Researching Topic...' : 'Run Wiki Builder'}</span>
              </button>
              <button
                onClick={() => void loadTopicData(selectedWikiId)}
                disabled={loadingTopic || isRunning}
                className="inline-flex items-center space-x-2 rounded-2xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-semibold text-white/75 transition-all hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <FolderOpen className="h-4 w-4" />
                <span>{loadingTopic ? 'Loading...' : 'Load Existing Wiki'}</span>
              </button>
              {topicData && (
                <button
                  onClick={() => void loadContent('log', 'pipeline.log')}
                  className="inline-flex items-center space-x-2 rounded-2xl border border-amber-400/15 bg-amber-400/10 px-5 py-3 text-sm font-semibold text-amber-100/80 transition-all hover:bg-amber-400/15"
                >
                  <Clock3 className="h-4 w-4" />
                  <span>Open Pipeline Log</span>
                </button>
              )}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
            <div className="rounded-[1.75rem] border border-white/10 bg-black/25 p-5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/35">Live Run</span>
                <span className="text-lg font-black text-sky-300">{progressEvent?.progress ?? 0}%</span>
              </div>
              <div className="mt-4 h-3 overflow-hidden rounded-full bg-white/5">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-sky-300 via-cyan-300 to-emerald-300 transition-all duration-700"
                  style={{ width: `${progressEvent?.progress ?? 0}%` }}
                />
              </div>
              <p className="mt-4 text-sm leading-6 text-white/70">
                {progressEvent?.message || `No active run yet. Start a topic or load the saved builder workspace for ${selectedWikiName}.`}
              </p>
              {progressEvent?.status === 'error' && (
                <div className="mt-4 rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-xs text-red-100/80">
                  {progressEvent.error || 'The pipeline reported an error.'}
                </div>
              )}
            </div>

            <div className="rounded-[1.75rem] border border-white/10 bg-black/25 p-5">
              <span className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/35">Output Snapshot</span>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-2xl border border-white/5 bg-white/5 p-4">
                  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/30">Sources</p>
                  <p className="mt-2 text-2xl font-black text-white">{result?.fetched_sources ?? topicData?.source_notes.length ?? 0}</p>
                </div>
                <div className="rounded-2xl border border-white/5 bg-white/5 p-4">
                  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/30">Concept Pages</p>
                  <p className="mt-2 text-2xl font-black text-white">{result?.concept_pages_written ?? Math.max((topicData?.wiki_pages.length || 1) - 1, 0)}</p>
                </div>
                <div className="rounded-2xl border border-white/5 bg-white/5 p-4">
                  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/30">Failures</p>
                  <p className="mt-2 text-2xl font-black text-white">{result?.failed_sources ?? 0}</p>
                </div>
                <div className="rounded-2xl border border-white/5 bg-white/5 p-4">
                  <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-white/30">Builder Model</p>
                  <p className="mt-2 text-sm font-bold text-white/85">
                    {models.find((model) => model.model_id === selectedModel)?.display_name || selectedModel}
                  </p>
                </div>
              </div>
              {result?.warnings?.length ? (
                <div className="mt-4 space-y-2">
                  {result.warnings.map((warning) => (
                    <div key={warning} className="flex items-start space-x-2 rounded-2xl border border-amber-300/15 bg-amber-300/10 px-4 py-3 text-xs text-amber-100/80">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-none" />
                      <span>{warning}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-6">
        <div>
          <div className="rounded-[1.75rem] border border-white/10 bg-[#0a0c12]/85 p-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">Pipeline Status</h3>
                {/* <p className="text-sm text-white/40">Watch each stage lock into place as this wiki materializes.</p> */}
              </div>
              {isRunning ? <LoaderCircle className="h-5 w-5 animate-spin text-sky-300" /> : <CheckCircle2 className="h-0 w-0 text-emerald-300/80" />}
            </div>
            <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-5">
              {STAGES.map((stage, index) => {
                const state =
                  progressEvent?.status === 'success'
                    ? 'done'
                    : index < currentStageIndex
                      ? 'done'
                      : index === currentStageIndex
                        ? 'active'
                        : 'idle';

                return (
                  <div
                    key={stage.key}
                    className={`group relative rounded-xl border px-3 py-3 transition-all ${state === 'done'
                      ? 'border-emerald-300/15 bg-emerald-300/10'
                      : state === 'active'
                        ? 'border-sky-300/20 bg-sky-300/10'
                        : 'border-white/5 bg-white/[0.03]'
                      }`}
                  >
                    <div className="flex items-center space-x-3">
                      <div
                        className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-[10px] font-black ${state === 'done'
                          ? 'bg-emerald-300/20 text-emerald-100'
                          : state === 'active'
                            ? 'bg-sky-300/20 text-sky-100'
                            : 'bg-white/10 text-white/35'
                          }`}
                      >
                        {index + 1}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-1">
                          <p className="truncate text-xs font-bold text-white">{stage.label}</p>
                          <button
                            type="button"
                            className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/5 text-white/40 transition hover:border-white/20 hover:text-white"
                            aria-label={`About ${stage.label}`}
                          >
                            <Info className="h-2.5 w-2.5" />
                          </button>
                        </div>
                        <p className={`text-[9px] font-bold uppercase tracking-wider ${state === 'done' ? 'text-emerald-400/60' : state === 'active' ? 'text-sky-400/60' : 'text-white/20'}`}>
                          {state === 'done' ? 'Done' : state === 'active' ? 'Active' : ''}
                        </p>
                      </div>
                    </div>
                    {/* Floating tooltip panel — same pattern as "About this view" */}
                    <div className="pointer-events-none absolute bottom-full left-0 z-50 mb-2 hidden w-56 rounded-2xl border border-white/10 bg-[#0a0c12]/95 p-4 text-left shadow-2xl group-hover:block">
                      <p className="text-xs font-bold uppercase tracking-[0.18em] text-white/35">Stage {index + 1}</p>
                      <p className="mt-2 text-sm leading-6 text-white/70">{stage.description}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-[1.75rem] border border-white/10 bg-[#0a0c12]/85 p-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">Activity Feed</h3>
                <p className="text-sm text-white/40">Recent events for {selectedWikiName}.</p>
              </div>
              <Library className="h-5 w-5 text-white/30" />
            </div>
            <div className="mt-5 space-y-3">
              {events.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-white/30">
                  No builder events yet for this wiki.
                </div>
              ) : (
                events.map((event) => (
                  <div key={event.id} className="rounded-2xl border border-white/5 bg-white/[0.03] px-4 py-3">
                    <div className="flex items-start justify-between space-x-4">
                      <div>
                        <p className="text-sm text-white/80">{event.message}</p>
                        <p className="mt-1 text-[10px] uppercase tracking-[0.16em] text-white/30">{event.stage || 'activity'}</p>
                      </div>
                      <span className="text-xs font-bold text-white/40">{event.progress}%</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div>
          <div className="rounded-[1.75rem] border border-white/10 bg-[#0a0c12]/85 p-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">Workspace Browser</h3>
                <p className="text-sm text-white/40">Inspect generated concept pages, source notes, and logs for this wiki.</p>
              </div>
              <div className="flex items-center space-x-2 text-[10px] font-bold uppercase tracking-[0.18em] text-white/30">
                <Link2 className="h-3.5 w-3.5" />
                <span>{selectedWikiName}</span>
              </div>
            </div>

            <div className="mt-6 grid gap-4 lg:grid-cols-[280px_1fr] min-w-0">
              <div className="space-y-4">
                <div className="rounded-2xl border border-white/5 bg-white/[0.03] p-3">
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    {[
                      { key: 'wiki', label: 'Wiki' },
                      { key: 'source', label: 'Sources' },
                      { key: 'log', label: 'Log' },
                    ].map((tab) => (
                      <button
                        key={tab.key}
                        onClick={() => {
                          if (tab.key === 'log') {
                            void loadContent('log', 'pipeline.log');
                            return;
                          }
                          setSelectedKind(tab.key as 'wiki' | 'source');
                        }}
                        className={`rounded-xl px-3 py-2 font-semibold transition-all ${selectedKind === tab.key ? 'bg-white/10 text-white' : 'text-white/40 hover:bg-white/5 hover:text-white/70'
                          }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="max-h-[500px] space-y-2 overflow-y-auto pr-1 custom-scrollbar">
                  {selectedKind === 'wiki' &&
                    topicData?.wiki_pages.map((item) => (
                      <button
                        key={item.name}
                        onClick={() => void loadContent('wiki', item.name)}
                        className={`w-full rounded-2xl border px-4 py-3 text-left transition-all ${selectedName === item.name && selectedKind === 'wiki'
                          ? 'border-sky-300/20 bg-sky-300/10 text-white'
                          : 'border-white/5 bg-white/[0.03] text-white/65 hover:bg-white/5 hover:text-white'
                          }`}
                      >
                        <p className="text-sm font-semibold">{item.title}</p>
                        <p className="mt-1 truncate text-xs text-white/30">{item.name}</p>
                      </button>
                    ))}
                  {selectedKind === 'source' &&
                    topicData?.source_notes.map((item) => (
                      <button
                        key={item.name}
                        onClick={() => void loadContent('source', item.name)}
                        className={`w-full rounded-2xl border px-4 py-3 text-left transition-all ${selectedName === item.name && selectedKind === 'source'
                          ? 'border-sky-300/20 bg-sky-300/10 text-white'
                          : 'border-white/5 bg-white/[0.03] text-white/65 hover:bg-white/5 hover:text-white'
                          }`}
                      >
                        <p className="text-sm font-semibold">{item.title}</p>
                        <p className="mt-1 line-clamp-2 text-xs text-white/35">{item.snippet}</p>
                      </button>
                    ))}
                  {!topicData && (
                    <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-white/30">
                      Run the builder or load this wiki to browse its research workspace.
                    </div>
                  )}
                </div>
              </div>

              <div className="min-h-[500px] min-w-0 overflow-hidden rounded-[1.5rem] border border-white/10 bg-black/20 p-6">
                <div className="mb-5 flex items-center justify-between">
                  <div>
                    <h4 className="text-lg font-bold text-white">{previewTitle}</h4>
                    <p className="text-xs text-white/35">{selectedKind === 'source' ? 'Source Note' : selectedKind === 'wiki' ? 'Concept Page' : 'Pipeline Output'}</p>
                  </div>
                </div>
                <div className="prose prose-invert max-w-none min-w-0 overflow-x-hidden text-sm prose-p:text-white/75 prose-a:text-sky-300 prose-headings:text-white">
                  {previewContent ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      urlTransform={(value: string) => value}
                      components={{
                        a: ({ href, children }) => {
                          const isInternalWikiLink = href && !href.startsWith('http://') && !href.startsWith('https://') && !href.startsWith('#') && !href.startsWith('mailto:') && !href.startsWith('tel:');
                          if (isInternalWikiLink) {
                            return (
                              <button
                                onClick={() => void openInternalLink(href)}
                                className="cursor-pointer text-left text-sky-300 underline underline-offset-4 transition-colors hover:text-sky-200"
                              >
                                {children}
                              </button>
                            );
                          }
                          return (
                            <a
                              href={href}
                              target={href?.startsWith('#') ? undefined : "_blank"}
                              rel="noopener noreferrer"
                              className="cursor-pointer text-sky-300 underline underline-offset-4 transition-colors hover:text-sky-200"
                            >
                              {children}
                            </a>
                          );
                        },
                      }}
                    >
                      {previewMarkdown}
                    </ReactMarkdown>
                  ) : (
                    <div className="flex h-[360px] items-center justify-center text-center text-white/30">
                      Pick a generated file to preview.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

        </div>
      </section>
    </div>
  );
};

export default WikiBuilderView;
