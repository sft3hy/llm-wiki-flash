import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Activity,
  BookOpen,
  Brain,
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  FolderKanban,
  GitBranch,
  Info,
  LayoutGrid,
  MessageSquare,
  Pencil,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  Settings,
  Trash,
  Upload,
  X,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import KnowledgeGraph from './components/KnowledgeGraph';
import ChatView from './components/ChatView';
import SettingsView from './components/SettingsView';
import MeditationView from './components/MeditationView';
import ModelSelector from './components/ModelSelector';
import IngestView from './components/IngestView';
import WikiBuilderView from './components/WikiBuilderView';

const API_BASE = 'http://localhost:8000';
const SELECTED_WIKI_KEY = 'llm-wiki-selected-wiki';
const ACTIVE_VIEW_KEY = 'llm-wiki-active-view';
const LAST_PAGE_KEY = 'llm-wiki-last-pages';
const SIDEBAR_COLLAPSED_KEY = 'llm-wiki-sidebar-collapsed';
const GOVERNANCE_PAGE_NAMES = new Set(['SCHEMA.md', 'index.md', 'log.md']);

type ViewType = 'wiki' | 'chat' | 'settings' | 'maintenance' | 'graph' | 'upload' | 'builder';
type WikiAction = 'create' | 'rename' | 'delete' | null;
type EntryKind = 'wiki' | 'source';

interface Model {
  model_id: string;
  display_name: string;
  provider: string;
  description: string;
}

interface WikiSummary {
  wiki_id: string;
  name: string;
  created_at: string;
  last_updated: string;
  page_count: number;
  source_count: number;
  models: Record<string, string>;
}

interface WikiPageSummary {
  name: string;
  title: string;
  links?: string[];
}

interface SourceSummary {
  name: string;
  title: string;
  snippet?: string;
}

interface ProgressState {
  message: string;
  progress: number;
  status: string;
  timestamp?: string;
  stage?: string;
  step?: string;
  topic?: string;
  document_name?: string;
  document_index?: number;
  total_documents?: number;
  concept_name?: string;
  concept_index?: number;
  total_concepts?: number;
  duration_ms?: number;
  active_model?: string | null;
}

interface ParsedRoute {
  wikiId: string;
  kind: EntryKind;
  name: string;
}

const DEFAULT_MODEL_ID = 'gemma4:e4b';

const VIEW_EXPLANATIONS: Record<ViewType, { title: string; description: string }> = {
  wiki: {
    title: 'Wiki',
    description: 'A wiki is the cleaned, cross-linked knowledge base for one topic or project.',
  },
  chat: {
    title: 'Knowledge Chat',
    description: 'Ask questions against only the selected wiki. Retrieval does not mix content across wikis.',
  },
  builder: {
    title: 'Wiki Builder',
    description: 'Run local research, fetch sources, generate pages, and store everything inside the selected wiki.',
  },
  maintenance: {
    title: 'Maintenance',
    description: 'Re-index documents, rebuild embeddings, and validate link or file integrity for this wiki.',
  },
  graph: {
    title: 'Graph View',
    description: 'Explore the selected wiki as a visual map of pages and their relationships.',
  },
  upload: {
    title: 'Upload',
    description: 'Add local documents directly into the selected wiki for ingestion.',
  },
  settings: {
    title: 'Settings',
    description: 'Inspect wiki storage, sources, schema, and model preferences for the current wiki.',
  },
};

const rewriteWikiLinks = (content: string) =>
  content.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_match, rawTarget: string, rawLabel?: string) => {
    const target = rawTarget.trim();
    const label = (rawLabel || rawTarget).trim();
    if (target.startsWith('sources/')) {
      return `[${label}](source://${target.split('/')[1]})`;
    }
    return `[${label}](wiki://${target})`;
  });

const stripFrontmatter = (content: string) => {
  if (!content.startsWith('---')) {
    return content;
  }
  const parts = content.split('---');
  if (parts.length < 3) {
    return content;
  }
  return parts.slice(2).join('---').trim();
};

const stripMarkdownCodeFence = (content: string) => {
  const trimmed = content.trim();
  const fencedMatch = trimmed.match(/^```(?:markdown|md)?\s*([\s\S]*?)\s*```$/i);
  return fencedMatch ? fencedMatch[1].trim() : content;
};

const parseWikiRoute = (pathname: string): ParsedRoute | null => {
  const parts = pathname.split('/').filter(Boolean);
  if (parts[0] !== 'wiki' || parts.length < 3) {
    return null;
  }
  const wikiId = decodeURIComponent(parts[1] || '');
  if (!wikiId) {
    return null;
  }
  if (parts[2] === 'source' && parts[3]) {
    const sourceName = decodeURIComponent(parts.slice(3).join('/'));
    return {
      wikiId,
      kind: 'source',
      name: sourceName.endsWith('.md') ? sourceName : `${sourceName}.md`,
    };
  }
  const pageName = decodeURIComponent(parts.slice(2).join('/'));
  return {
    wikiId,
    kind: 'wiki',
    name: pageName.endsWith('.md') ? pageName : `${pageName}.md`,
  };
};

const buildWikiRoute = (wikiId: string, filename: string) => `/wiki/${encodeURIComponent(wikiId)}/${encodeURIComponent(filename.replace(/\.md$/, ''))}`;
const buildSourceRoute = (wikiId: string, filename: string) => `/wiki/${encodeURIComponent(wikiId)}/source/${encodeURIComponent(filename.replace(/\.md$/, ''))}`;

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const autoLinkKnownPages = (content: string, pages: WikiPageSummary[], currentPage: string | null) => {
  const candidates = pages
    .filter((page) => !GOVERNANCE_PAGE_NAMES.has(page.name) && page.name !== currentPage)
    .flatMap((page) => {
      const slug = page.name.replace(/\.md$/, '');
      const humanized = slug.replace(/-/g, ' ');
      return [
        { phrase: page.title.trim(), target: slug },
        { phrase: humanized.trim(), target: slug },
      ];
    })
    .filter((candidate) => candidate.phrase.length > 2)
    .sort((left, right) => right.phrase.length - left.phrase.length);

  return content
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('```') || trimmed.startsWith('|') || line.includes('](') || line.includes('[[')) {
        return line;
      }

      let nextLine = line;
      for (const candidate of candidates) {
        const pattern = new RegExp(`(^|[^\\w])(${escapeRegExp(candidate.phrase)})(?=$|[^\\w])`, 'i');
        if (!pattern.test(nextLine)) {
          continue;
        }
        nextLine = nextLine.replace(pattern, (_match, prefix: string, phrase: string) => `${prefix}[${phrase}](wiki://${candidate.target})`);
      }
      return nextLine;
    })
    .join('\n');
};

function App() {
  const [wikis, setWikis] = useState<WikiSummary[]>([]);
  const [wikiPageMeta, setWikiPageMeta] = useState<WikiPageSummary[]>([]);
  const [selectedWikiId, setSelectedWikiId] = useState('');
  const [wikiPages, setWikiPages] = useState<string[]>([]);
  const [sourceNotes, setSourceNotes] = useState<SourceSummary[]>([]);
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const [selectedEntryKind, setSelectedEntryKind] = useState<EntryKind>('wiki');
  const [pageContent, setPageContent] = useState('');
  const [isIngesting, setIsIngesting] = useState(false);
  const [activeView, setActiveView] = useState<ViewType>(() => (localStorage.getItem(ACTIVE_VIEW_KEY) as ViewType) || 'wiki');
  const [ingestProgress, setIngestProgress] = useState<ProgressState | null>(null);
  const [ingestionStartTime, setIngestionStartTime] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [models, setModels] = useState<Model[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [defaultModelId, setDefaultModelId] = useState(DEFAULT_MODEL_ID);
  const [wikiAction, setWikiAction] = useState<WikiAction>(null);
  const [wikiNameInput, setWikiNameInput] = useState('');
  const [isSavingWikiAction, setIsSavingWikiAction] = useState(false);
  const [deletePageName, setDeletePageName] = useState<string | null>(null);
  const [isWikiFolderExpanded, setIsWikiFolderExpanded] = useState(true);
  const [isGovernanceFolderExpanded, setIsGovernanceFolderExpanded] = useState(false);
  const [isSourceFolderExpanded, setIsSourceFolderExpanded] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true');
  const [pendingRoute, setPendingRoute] = useState<ParsedRoute | null>(() => parseWikiRoute(window.location.pathname));

  const currentWiki = useMemo(() => wikis.find((wiki) => wiki.wiki_id === selectedWikiId) || null, [wikis, selectedWikiId]);
  const markdown = useMemo(
    () => autoLinkKnownPages(rewriteWikiLinks(stripFrontmatter(stripMarkdownCodeFence(pageContent))), wikiPageMeta, selectedEntryKind === 'wiki' ? selectedPage : null),
    [pageContent, wikiPageMeta, selectedPage, selectedEntryKind],
  );
  const filteredPages = useMemo(() => {
    if (!searchQuery.trim()) {
      return wikiPageMeta;
    }
    const query = searchQuery.toLowerCase();
    return wikiPageMeta.filter((page) => page.name.toLowerCase().includes(query) || page.title.toLowerCase().includes(query));
  }, [wikiPageMeta, searchQuery]);
  const filteredSources = useMemo(() => {
    if (!searchQuery.trim()) {
      return sourceNotes;
    }
    const query = searchQuery.toLowerCase();
    return sourceNotes.filter(
      (source) =>
        source.name.toLowerCase().includes(query) ||
        source.title.toLowerCase().includes(query) ||
        (source.snippet || '').toLowerCase().includes(query),
    );
  }, [sourceNotes, searchQuery]);
  const governancePages = useMemo(
    () => filteredPages.filter((page) => GOVERNANCE_PAGE_NAMES.has(page.name)),
    [filteredPages],
  );
  const contentPages = useMemo(
    () => filteredPages.filter((page) => !GOVERNANCE_PAGE_NAMES.has(page.name)),
    [filteredPages],
  );
  const selectedItemTitle = useMemo(() => {
    if (!selectedPage) {
      return '';
    }
    if (selectedEntryKind === 'source') {
      return sourceNotes.find((source) => source.name === selectedPage)?.title || selectedPage.replace('.md', '');
    }
    return wikiPageMeta.find((page) => page.name === selectedPage)?.title || selectedPage.replace('.md', '');
  }, [selectedEntryKind, selectedPage, sourceNotes, wikiPageMeta]);
  const viewInfo = VIEW_EXPLANATIONS[activeView];

  useEffect(() => {
    if (!wikiAction) {
      return;
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setWikiAction(null);
        setWikiNameInput('');
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [wikiAction]);

  useEffect(() => {
    void fetchModels();
    void fetchWikis();
  }, []);

  useEffect(() => {
    const handlePopState = () => {
      const route = parseWikiRoute(window.location.pathname);
      if (!route) {
        return;
      }
      setPendingRoute(route);
      setSelectedWikiId(route.wikiId);
      setActiveView('wiki');
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  useEffect(() => {
    localStorage.setItem(ACTIVE_VIEW_KEY, activeView);
  }, [activeView]);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(isSidebarCollapsed));
  }, [isSidebarCollapsed]);

  useEffect(() => {
    if (!selectedWikiId) {
      setWikiPageMeta([]);
      setWikiPages([]);
      setSourceNotes([]);
      setSelectedPage(null);
      setPageContent('');
      return;
    }
    localStorage.setItem(SELECTED_WIKI_KEY, selectedWikiId);
    void fetchWikiPages(selectedWikiId);
    setIsWikiFolderExpanded(true);
    setIsGovernanceFolderExpanded(false);
    setIsSourceFolderExpanded(false);
  }, [selectedWikiId]);

  useEffect(() => {
    if (!pendingRoute || !selectedWikiId || pendingRoute.wikiId !== selectedWikiId) {
      return;
    }

    if (pendingRoute.kind === 'wiki') {
      if (wikiPages.includes(pendingRoute.name)) {
        void fetchPageContent(pendingRoute.name, selectedWikiId, true, false);
        setPendingRoute(null);
      }
      return;
    }

    if (sourceNotes.some((source) => source.name === pendingRoute.name)) {
      void fetchSourceContent(pendingRoute.name, selectedWikiId, true, false);
      setPendingRoute(null);
    }
  }, [pendingRoute, selectedWikiId, wikiPages, sourceNotes]);

  useEffect(() => {
    if (!selectedWikiId || models.length === 0) {
      return;
    }
    const preferred = models.find((model) => model.model_id === defaultModelId)?.model_id || models[0]?.model_id || '';
    setSelectedModel((current) => (models.some((model) => model.model_id === current) ? current : preferred));
  }, [selectedWikiId, models, defaultModelId]);

  useEffect(() => {
    if (!selectedWikiId) {
      return;
    }
    if (selectedEntryKind === 'source') {
      return;
    }
    const preferredPage = getLastOpenedPage(selectedWikiId);
    const nextPage =
      (preferredPage && wikiPages.includes(preferredPage) ? preferredPage : null) ||
      (wikiPages.includes('index.md') ? 'index.md' : wikiPages[0] || null);
    if (!nextPage) {
      setSelectedPage(null);
      setPageContent('');
      return;
    }
    if (selectedPage !== nextPage) {
      void fetchPageContent(nextPage, selectedWikiId, false);
    }
  }, [wikiPages, selectedWikiId, selectedPage, selectedEntryKind]);

  useEffect(() => {
    const eventSource = new EventSource(`${API_BASE}/progress`);
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.channel === 'wiki_builder') {
          return;
        }
        setIngestProgress(data);
        if (data.status === 'processing') {
          setIngestionStartTime((previous) => previous ?? Date.now());
          setIsIngesting(true);
        } else if (data.status === 'success') {
          setTimeout(() => {
            setIngestProgress(null);
            setIsIngesting(false);
            setIngestionStartTime(null);
          }, 3000);
        } else {
          setIsIngesting(false);
          setIngestionStartTime(null);
        }
      } catch (error) {
        console.error('Failed to parse progress data:', error);
      }
    };
    return () => eventSource.close();
  }, []);

  useEffect(() => {
    let interval: number | undefined;
    if (isIngesting && selectedWikiId) {
      interval = window.setInterval(() => {
        void fetchWikiPages(selectedWikiId);
      }, 5000);
    }
    return () => {
      if (interval) {
        window.clearInterval(interval);
      }
    };
  }, [isIngesting, selectedWikiId]);

  const getLastOpenedPage = (wikiId: string) => {
    try {
      const map = JSON.parse(localStorage.getItem(LAST_PAGE_KEY) || '{}') as Record<string, string>;
      return map[wikiId] || null;
    } catch {
      return null;
    }
  };

  const storeLastOpenedPage = (wikiId: string, page: string) => {
    try {
      const map = JSON.parse(localStorage.getItem(LAST_PAGE_KEY) || '{}') as Record<string, string>;
      map[wikiId] = page;
      localStorage.setItem(LAST_PAGE_KEY, JSON.stringify(map));
    } catch {
      localStorage.setItem(LAST_PAGE_KEY, JSON.stringify({ [wikiId]: page }));
    }
  };

  const fetchModels = async () => {
    try {
      const response = await axios.get(`${API_BASE}/models`);
      setModels(response.data.models);
      setDefaultModelId(response.data.default || DEFAULT_MODEL_ID);
    } catch (error) {
      console.error('Error fetching models:', error);
      setModels([
        {
          model_id: 'gemma4:e4b',
          display_name: 'Gemma 4 Medium',
          provider: 'ollama',
          description: "Google's Gemma 4",
        },
      ]);
      setDefaultModelId(DEFAULT_MODEL_ID);
    }
  };

  const fetchWikis = async (preferredWikiId?: string) => {
    try {
      const response = await axios.get(`${API_BASE}/wikis`);
      const items: WikiSummary[] = response.data.wikis;
      setWikis(items);
      const storedWikiId = localStorage.getItem(SELECTED_WIKI_KEY);
      const routeWikiId = pendingRoute?.wikiId;
      const desiredWikiId =
        (routeWikiId && items.some((wiki) => wiki.wiki_id === routeWikiId) ? routeWikiId : null) ||
        preferredWikiId ||
        (selectedWikiId && items.some((wiki) => wiki.wiki_id === selectedWikiId) ? selectedWikiId : null) ||
        (storedWikiId && items.some((wiki) => wiki.wiki_id === storedWikiId) ? storedWikiId : null) ||
        response.data.default_wiki_id ||
        items[0]?.wiki_id ||
        '';
      if (desiredWikiId !== selectedWikiId) {
        setSelectedWikiId(desiredWikiId);
      }
    } catch (error) {
      console.error('Error fetching wikis:', error);
    }
  };

  const fetchWikiPages = async (wikiId: string) => {
    try {
      const response = await axios.get(`${API_BASE}/wikis/${wikiId}`);
      const pages: WikiPageSummary[] = response.data.pages || [];
      const sources: SourceSummary[] = response.data.sources || [];
      setWikiPageMeta(pages);
      setWikiPages(pages.map((page) => page.name));
      setSourceNotes(sources);
    } catch (error) {
      console.error('Error fetching wiki pages:', error);
      setWikiPageMeta([]);
      setWikiPages([]);
      setSourceNotes([]);
    }
  };

  const updateHistory = (path: string, replace = false) => {
    if (window.location.pathname === path) {
      return;
    }
    window.history[replace ? 'replaceState' : 'pushState']({}, '', path);
  };

  const fetchPageContent = async (filename: string, wikiId = selectedWikiId, activateWikiView = true, pushHistory = true) => {
    if (!wikiId) {
      return;
    }
    try {
      const response = await axios.get(`${API_BASE}/wiki/${filename}`, {
        params: { wiki_id: wikiId },
      });
      setPageContent(response.data.content);
      setSelectedPage(filename);
      setSelectedEntryKind('wiki');
      storeLastOpenedPage(wikiId, filename);
      if (activateWikiView) {
        setActiveView('wiki');
      }
      if (pushHistory) {
        updateHistory(buildWikiRoute(wikiId, filename));
      }
    } catch (error) {
      console.error('Error fetching page content:', error);
    }
  };

  const fetchSourceContent = async (filename: string, wikiId = selectedWikiId, activateWikiView = true, pushHistory = true) => {
    if (!wikiId) {
      return;
    }
    try {
      const response = await axios.get(`${API_BASE}/builder/content`, {
        params: { wiki_id: wikiId, kind: 'source', name: filename },
      });
      setPageContent(response.data.content);
      setSelectedPage(filename);
      setSelectedEntryKind('source');
      if (activateWikiView) {
        setActiveView('wiki');
      }
      if (pushHistory) {
        updateHistory(buildSourceRoute(wikiId, filename));
      }
    } catch (error) {
      console.error('Error fetching source content:', error);
    }
  };

  const handleModelChange = (modelId: string) => {
    setSelectedModel(modelId);
  };

  const handleWikiUpdated = async (wikiId = selectedWikiId) => {
    await fetchWikis(wikiId);
    if (wikiId) {
      await fetchWikiPages(wikiId);
    }
  };

  const handleIngestSuccess = async () => {
    await handleWikiUpdated();
    setActiveView('wiki');
  };

  const calculateETE = () => {
    if (!ingestionStartTime || !ingestProgress || ingestProgress.progress === 0) {
      return null;
    }
    const elapsed = (Date.now() - ingestionStartTime) / 1000;
    const rate = ingestProgress.progress / elapsed;
    const remaining = (100 - ingestProgress.progress) / rate;
    if (remaining < 1) {
      return 'Few seconds...';
    }
    if (remaining > 3600) {
      return 'Over an hour...';
    }
    const mins = Math.floor(remaining / 60);
    const secs = Math.floor(remaining % 60);
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  };

  const openWikiAction = (action: WikiAction) => {
    if (action === 'rename' && currentWiki) {
      setWikiNameInput(currentWiki.name);
    } else {
      setWikiNameInput('');
    }
    setWikiAction(action);
  };

  const submitWikiAction = async () => {
    if (!wikiAction) {
      return;
    }
    setIsSavingWikiAction(true);
    try {
      if (wikiAction === 'create') {
        if (!wikiNameInput.trim()) {
          return;
        }
        const response = await axios.post(`${API_BASE}/wikis`, { name: wikiNameInput.trim() });
        await fetchWikis(response.data.wiki_id);
        setActiveView('builder');
      } else if (wikiAction === 'rename' && currentWiki) {
        if (!wikiNameInput.trim()) {
          return;
        }
        await axios.put(`${API_BASE}/wikis/${currentWiki.wiki_id}`, { name: wikiNameInput.trim() });
        await fetchWikis(currentWiki.wiki_id);
      } else if (wikiAction === 'delete' && currentWiki) {
        await axios.delete(`${API_BASE}/wikis/${currentWiki.wiki_id}`);
        setSelectedPage(null);
        setPageContent('');
        await fetchWikis();
      }
      setWikiAction(null);
      setWikiNameInput('');
    } catch (error) {
      console.error('Wiki action failed:', error);
      alert('That wiki action failed.');
    } finally {
      setIsSavingWikiAction(false);
    }
  };

  const handleDeletePage = async () => {
    if (!selectedWikiId || !deletePageName) {
      return;
    }
    try {
      await axios.delete(`${API_BASE}/wiki/${deletePageName}`, {
        params: { wiki_id: selectedWikiId },
      });
      setDeletePageName(null);
      setSelectedPage(null);
      setPageContent('');
      await handleWikiUpdated(selectedWikiId);
    } catch (error) {
      console.error('Error deleting page:', error);
      alert('Failed to delete page.');
    }
  };

  const openInternalWikiLink = (href: string | undefined) => {
    if (!href) {
      return;
    }
    if (href.startsWith('wiki://')) {
      const rawName = href.replace('wiki://', '');
      void fetchPageContent(rawName.endsWith('.md') ? rawName : `${rawName}.md`);
      return;
    }
    if (href.startsWith('source://')) {
      const rawName = href.replace('source://', '');
      void fetchSourceContent(rawName.endsWith('.md') ? rawName : `${rawName}.md`);
      return;
    }

    if (!href.startsWith('http://') && !href.startsWith('https://') && !href.startsWith('#') && !href.startsWith('mailto:') && !href.startsWith('tel:')) {
      void fetchPageContent(href.endsWith('.md') ? href : `${href}.md`);
      return;
    }

    window.open(href, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="flex h-screen overflow-hidden bg-[#05070a] font-sans text-[#e2e8f0]">
      <aside
        className={`z-20 flex h-full min-h-0 flex-col overflow-hidden border-r border-white/5 bg-[#0a0c12]/90 shadow-2xl backdrop-blur-xl transition-all duration-300 ${isSidebarCollapsed ? 'w-[4.75rem] p-3' : 'w-[18.5rem] p-4 lg:w-[20rem] xl:w-[22rem] xl:p-5'
          }`}
      >
        <div className={`mb-4 flex flex-none items-start ${isSidebarCollapsed ? 'justify-center' : 'justify-between gap-3'}`}>
          {!isSidebarCollapsed && (
            <div className="flex items-center space-x-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-blue-600">
                <Brain className="h-5 w-5 text-black" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-white">LLM Wiki</h1>
                <p className="text-xs text-white/40">Persistent local knowledge bases</p>
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={() => setIsSidebarCollapsed((value) => !value)}
            className={`inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-white/60 transition hover:bg-white/10 hover:text-white ${isSidebarCollapsed ? 'absolute right-3 top-3' : ''
              }`}
            aria-label={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isSidebarCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </div>

        {!isSidebarCollapsed && (
          <>
            <section className="mb-4 flex flex-none flex-col overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-2">
              <div className="px-3 pb-2 pt-2">
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-white/35">Workspace</p>
              </div>
              <div className="min-h-0 flex-1 space-y-1 overflow-y-auto px-2 pb-2 custom-scrollbar">
                {[
                  { key: 'chat', label: 'Knowledge Chat', description: 'Ask questions scoped to this wiki only.', icon: MessageSquare },
                  { key: 'builder', label: 'Wiki Builder', description: 'Research and generate this wiki locally.', icon: Search },
                  { key: 'maintenance', label: 'Maintenance', description: 'Repair, re-index, and validate this wiki.', icon: Brain },
                  { key: 'graph', label: 'Graph View', description: 'Visualize page relationships.', icon: LayoutGrid },
                ].map((item) => (
                  <button
                    key={item.key}
                    onClick={() => setActiveView(item.key as ViewType)}
                    className={`w-full rounded-2xl px-4 py-3 text-left transition ${activeView === item.key ? 'bg-white/10 text-white' : 'text-white/60 hover:bg-white/5 hover:text-white'
                      }`}
                  >
                    <div className="flex items-center gap-3">
                      <item.icon className="h-4 w-4" />
                      <div>
                        <p className="text-sm font-semibold">{item.label}</p>
                        <p className="text-xs text-white/35">{item.description}</p>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </section>

            <section className="min-h-0 flex flex-1 flex-col overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-4">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-white/35">{currentWiki?.name || 'Wiki'} Library</p>
                </div>
                <span className="rounded-full bg-white/5 px-2 py-1 text-[10px] text-white/45">{wikiPages.length + sourceNotes.length}</span>
              </div>
              <nav className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1 custom-scrollbar">
                <div className="space-y-1">
                  <button
                    onClick={() => setIsWikiFolderExpanded((value) => !value)}
                    className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-white/75 transition hover:bg-white/5 hover:text-white"
                  >
                    <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em]">
                      {isWikiFolderExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                      <span>Wiki</span>
                    </span>
                    <span className="rounded-full bg-white/5 px-2 py-1 text-[10px] text-white/45">{contentPages.length}</span>
                  </button>
                  {isWikiFolderExpanded && (
                    <div className="space-y-1 pl-3">
                      {contentPages.map((page) => (
                        <button
                          key={page.name}
                          onClick={() => void fetchPageContent(page.name)}
                          className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition ${selectedEntryKind === 'wiki' && selectedPage === page.name && activeView === 'wiki'
                              ? 'bg-white/10 text-white'
                              : 'text-white/45 hover:bg-white/5 hover:text-white'
                            }`}
                        >
                          <FileText className="h-3.5 w-3.5 opacity-50" />
                          <span className="truncate text-xs font-medium">{page.title}</span>
                        </button>
                      ))}
                      {!contentPages.length && <div className="rounded-xl border border-dashed border-white/10 px-4 py-4 text-center text-xs text-white/30">No wiki pages yet.</div>}
                    </div>
                  )}
                </div>

                <div className="space-y-1">
                  <button
                    onClick={() => setIsSourceFolderExpanded((value) => !value)}
                    className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-white/60 transition hover:bg-white/5 hover:text-white"
                  >
                    <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em]">
                      {isSourceFolderExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                      <span>Sources</span>
                    </span>
                    <span className="rounded-full bg-white/5 px-2 py-1 text-[10px] text-white/45">{sourceNotes.length}</span>
                  </button>
                  {isSourceFolderExpanded && (
                    <div className="space-y-1 pl-3">
                      {filteredSources.map((source) => (
                        <button
                          key={source.name}
                          onClick={() => void fetchSourceContent(source.name)}
                          className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition ${selectedEntryKind === 'source' && selectedPage === source.name && activeView === 'wiki'
                              ? 'bg-white/10 text-white'
                              : 'text-white/45 hover:bg-white/5 hover:text-white'
                            }`}
                        >
                          <FileText className="h-3.5 w-3.5 opacity-50" />
                          <span className="truncate text-xs font-medium">{source.title}</span>
                        </button>
                      ))}
                      {!filteredSources.length && <div className="rounded-xl border border-dashed border-white/10 px-4 py-4 text-center text-xs text-white/30">No source notes yet.</div>}
                    </div>
                  )}
                </div>

                <div className="space-y-1">
                  <button
                    onClick={() => setIsGovernanceFolderExpanded((value) => !value)}
                    className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-white/60 transition hover:bg-white/5 hover:text-white"
                  >
                    <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em]">
                      {isGovernanceFolderExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                      <span>Governance</span>
                    </span>
                    <span className="rounded-full bg-white/5 px-2 py-1 text-[10px] text-white/45">{governancePages.length}</span>
                  </button>
                  {isGovernanceFolderExpanded && (
                    <div className="space-y-1 pl-3">
                      {governancePages.map((page) => (
                        <button
                          key={page.name}
                          onClick={() => void fetchPageContent(page.name)}
                          className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition ${selectedEntryKind === 'wiki' && selectedPage === page.name && activeView === 'wiki'
                              ? 'bg-white/10 text-white'
                              : 'text-white/45 hover:bg-white/5 hover:text-white'
                            }`}
                        >
                          <FileText className="h-3.5 w-3.5 opacity-50" />
                          <span className="truncate text-xs font-medium">{page.title}</span>
                        </button>
                      ))}
                      {!governancePages.length && <div className="rounded-xl border border-dashed border-white/10 px-4 py-4 text-center text-xs text-white/30">No governance docs yet.</div>}
                    </div>
                  )}
                </div>
              </nav>
            </section>
          </>
        )}
      </aside>

      <main className="flex min-w-0 flex-1 flex-col bg-[#05070a]">
        <header className="z-10 flex flex-none flex-col border-b border-white/5 bg-[#05070a]/85 backdrop-blur-xl">
          <div className="px-4 py-4 lg:px-8">
            <div className="flex flex-wrap items-center gap-1.5 rounded-[1.35rem] border border-white/10 bg-white/[0.03] px-3 py-2.5">
              <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                <div className="relative w-[9.75rem] max-w-full shrink-0">
                  <select
                    value={selectedWikiId}
                    onChange={(event) => setSelectedWikiId(event.target.value)}
                    className="w-full appearance-none rounded-xl border border-white/10 bg-[#0a0c12] px-3 py-2 pr-8 text-xs font-semibold text-white outline-none transition focus:border-primary/40"
                  >
                    {wikis.map((wiki) => (
                      <option key={wiki.wiki_id} value={wiki.wiki_id}>
                        {wiki.name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/35" />
                </div>

                <div className="group relative hidden shrink-0 items-center gap-2 sm:flex">
                  <div className="flex items-center gap-2 text-white">
                    <FolderKanban className="h-4 w-4 text-white/45" />
                    <span className="truncate text-sm font-semibold">{viewInfo.title}</span>
                    <button
                      type="button"
                      className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-white/10 bg-white/5 text-white/50 transition hover:border-white/20 hover:text-white"
                      aria-label="View details"
                    >
                      <Info className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <div className="pointer-events-none absolute left-0 top-full z-30 mt-2 hidden w-80 rounded-2xl border border-white/10 bg-[#0a0c12]/95 p-4 text-left shadow-2xl group-hover:block">
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-white/35">About This View</p>
                    <p className="mt-2 text-sm leading-6 text-white/70">{viewInfo.description}</p>
                  </div>
                </div>
              </div>

              <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
                <button
                  onClick={() => openWikiAction('create')}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-2.5 py-2 text-xs font-semibold text-white/80 transition hover:bg-white/10 hover:text-white"
                >
                  <Plus className="h-4 w-4" />
                  <span>New Wiki</span>
                </button>
                <button
                  onClick={() => openWikiAction('rename')}
                  disabled={!currentWiki}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-2.5 py-2 text-xs font-semibold text-white/80 transition hover:bg-white/10 hover:text-white disabled:opacity-30"
                >
                  <Pencil className="h-4 w-4" />
                  <span>Rename</span>
                </button>
                <button
                  onClick={() => openWikiAction('delete')}
                  disabled={!currentWiki}
                  className="shrink-0 rounded-xl border border-red-500/20 bg-red-500/10 px-2.5 py-2 text-xs font-semibold text-red-200/85 transition hover:bg-red-500/15 disabled:opacity-30"
                >
                  Delete
                </button>
                <div className="w-[11rem] max-w-full shrink-0">
                  <ModelSelector models={models} selectedModel={selectedModel} onModelChange={handleModelChange} />
                </div>
                <button
                  onClick={() => setActiveView('upload')}
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl border px-2.5 py-2 text-xs font-semibold transition ${activeView === 'upload'
                      ? 'border-primary/40 bg-primary/12 text-white'
                      : 'border-white/10 bg-white/5 text-white/75 hover:bg-white/10 hover:text-white'
                    }`}
                >
                  <Upload className="h-4 w-4" />
                  <span>Upload</span>
                </button>
                <button
                  onClick={() => setActiveView('settings')}
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl border px-2.5 py-2 text-xs font-semibold transition ${activeView === 'settings'
                      ? 'border-primary/40 bg-primary/12 text-white'
                      : 'border-white/10 bg-white/5 text-white/75 hover:bg-white/10 hover:text-white'
                    }`}
                >
                  <Settings className="h-4 w-4" />
                  <span>Settings</span>
                </button>
              </div>
            </div>
          </div>

          {/* {activeView === 'wiki' && (
            <div className="border-t border-white/5 px-4 py-4 lg:px-8">
              <div className="flex items-center gap-3 rounded-[1.6rem] border border-white/10 bg-white/[0.03] px-4 py-3 shadow-[0_18px_50px_rgba(0,0,0,0.24)]">
                <Search className="h-4 w-4 text-white/30" />
                <input
                  type="text"
                  placeholder={`Search inside ${currentWiki?.name || 'this wiki'}...`}
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  className="w-full bg-transparent text-sm text-white outline-none placeholder:text-white/25"
                />
              </div>
            </div>
          )} */}
        </header>

        {ingestProgress && (
          <div className="w-full overflow-hidden border-b border-white/5 bg-[#0a0c12]/80 backdrop-blur-md">
            <div className="mx-auto flex max-w-6xl items-center justify-between px-8 py-3">
              <div className="flex flex-1 items-center gap-4">
                <div className={`rounded-lg bg-primary/10 p-2 text-primary ${ingestProgress.status === 'processing' ? 'animate-book-flip' : ''}`}>
                  <BookOpen className={`h-4 w-4 ${ingestProgress.status === 'processing' ? 'animate-page-turn' : ''}`} />
                </div>
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.2em] text-white/30">Compiling Knowledge</p>
                  <p className="text-sm text-white/80">{ingestProgress.message}</p>
                </div>
              </div>
              <div className="flex items-center gap-6">
                <div className="hidden text-right md:block">
                  <p className="text-[9px] font-bold uppercase tracking-widest text-white/20">Time Remaining</p>
                  <div className="flex items-center gap-1 text-primary/80">
                    <Clock className="h-3 w-3" />
                    <span className="text-xs font-mono font-bold">{calculateETE() || '--:--'}</span>
                  </div>
                </div>
                <div className="flex items-center gap-4 rounded-full border border-white/5 bg-white/5 py-1 pl-4 pr-1">
                  <span className="text-sm font-mono font-black text-primary">{ingestProgress.progress}%</span>
                  <div className="h-2 w-32 overflow-hidden rounded-full border border-white/5 bg-white/5 p-0.5">
                    <div className="h-full rounded-full bg-gradient-to-r from-primary to-blue-400 transition-all duration-700" style={{ width: `${ingestProgress.progress}%` }} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-hidden p-4 lg:p-8">
          {!selectedWikiId ? (
            <div className="flex h-full flex-col items-center justify-center space-y-5 text-center">
              <FolderKanban className="h-16 w-16 text-white/20" />
              <div>
                <p className="text-2xl font-bold text-white">No wiki selected</p>
                <p className="mt-2 max-w-md text-white/35">Create a wiki from the top bar to start a separate local knowledge base.</p>
              </div>
            </div>
          ) : activeView === 'graph' ? (
            <div className="h-full overflow-hidden rounded-3xl border border-white/5 bg-[#0a0c12]/50">
              <KnowledgeGraph pages={wikiPageMeta} onNodeClick={(node) => void fetchPageContent(node.id)} />
            </div>
          ) : activeView === 'builder' ? (
            <div className="h-full overflow-y-auto pr-2 custom-scrollbar">
              <WikiBuilderView selectedModel={selectedModel} models={models} selectedWikiId={selectedWikiId} selectedWikiName={currentWiki?.name || 'Untitled Wiki'} onWikiUpdated={handleWikiUpdated} />
            </div>
          ) : activeView === 'chat' ? (
            <ChatView
              selectedModel={selectedModel}
              models={models}
              selectedWikiId={selectedWikiId}
              selectedWikiName={currentWiki?.name || 'Untitled Wiki'}
              onNavigate={(page) => void fetchPageContent(page, selectedWikiId, true)}
              onNavigateSource={(source) => void fetchSourceContent(source, selectedWikiId, true)}
            />
          ) : activeView === 'settings' ? (
            <div className="h-full overflow-y-auto pr-2 custom-scrollbar">
              <SettingsView models={models} selectedModel={selectedModel} onModelChange={handleModelChange} wikiPages={wikiPages} selectedWikiId={selectedWikiId} selectedWikiName={currentWiki?.name || 'Untitled Wiki'} />
            </div>
          ) : activeView === 'upload' ? (
            <div className="h-full overflow-y-auto pr-2 custom-scrollbar">
              <IngestView masterModel={selectedModel} models={models} selectedWikiId={selectedWikiId} selectedWikiName={currentWiki?.name || 'Untitled Wiki'} onSuccess={handleIngestSuccess} isIngesting={isIngesting} progress={ingestProgress} />
            </div>
          ) : activeView === 'maintenance' ? (
            <div className="h-full overflow-y-auto pr-2 custom-scrollbar">
              <MeditationView selectedWikiId={selectedWikiId} selectedWikiName={currentWiki?.name || 'Untitled Wiki'} selectedModel={selectedModel} />
            </div>
          ) : selectedPage ? (
            <div className="mx-auto h-full max-w-4xl overflow-y-auto pr-2 custom-scrollbar">
              <div className="mb-8 flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-white/35">
                    <GitBranch className="h-3.5 w-3.5" />
                    <span>{currentWiki?.name}</span>
                  </div>
                  <h2 className="mt-2 text-4xl font-black tracking-tight text-white">{selectedItemTitle}</h2>
                  <div className="mt-3 flex items-center gap-4 text-xs font-bold uppercase tracking-widest text-white/30">
                    <span className="flex items-center gap-1.5">
                      <Activity className="h-3 w-3" />
                      <span>{selectedEntryKind === 'source' ? 'Source Note' : 'Generated Wiki Page'}</span>
                    </span>
                    <span className="h-1 w-1 rounded-full bg-white/20" />
                    <span className="flex items-center gap-1.5 text-primary/80">
                      <Info className="h-3 w-3" />
                      <span>Rendered Markdown</span>
                    </span>
                  </div>
                </div>
                {selectedEntryKind === 'wiki' && selectedPage && !['index.md', 'log.md', 'SCHEMA.md'].includes(selectedPage) && (
                  <button onClick={() => setDeletePageName(selectedPage)} className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-red-300 transition hover:bg-red-500/20">
                    <Trash className="h-5 w-5" />
                  </button>
                )}
              </div>

              {deletePageName && (
                <div className="mb-6 rounded-2xl border border-red-500/20 bg-red-500/10 p-4">
                  <p className="text-sm font-semibold text-white">Delete {deletePageName}?</p>
                  <p className="mt-1 text-xs text-white/50">This removes the page from the current wiki only.</p>
                  <div className="mt-3 flex gap-2">
                    <button onClick={() => setDeletePageName(null)} className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-xs font-semibold text-white/70">Cancel</button>
                    <button onClick={() => void handleDeletePage()} className="rounded-xl bg-red-400 px-4 py-2 text-xs font-bold text-black">Delete Page</button>
                  </div>
                </div>
              )}

              <div className="prose prose-invert max-w-none py-8 px-2 prose-headings:mb-4 prose-headings:font-black prose-headings:tracking-tight prose-headings:text-white prose-h1:text-4xl prose-h2:mt-10 prose-h2:text-2xl prose-h3:mt-8 prose-h3:text-xl prose-p:my-5 prose-p:text-[17px] prose-p:leading-8 prose-p:text-white/75 prose-ul:my-6 prose-ul:list-disc prose-ul:pl-6 prose-ol:my-6 prose-ol:list-decimal prose-ol:pl-6 prose-li:my-2 prose-li:text-white/75 prose-strong:text-white prose-a:text-sky-300 prose-blockquote:border-l prose-blockquote:border-white/15 prose-blockquote:pl-4 prose-blockquote:text-white/60 prose-hr:my-10 prose-hr:border-white/10 prose-table:my-8 prose-table:w-full prose-thead:border-b prose-thead:border-white/10 prose-th:p-3 prose-th:text-left prose-th:text-white prose-td:border-b prose-td:border-white/5 prose-td:p-3 prose-code:rounded-md prose-code:bg-white/5 prose-code:px-1.5 prose-code:py-0.5 prose-code:text-primary prose-code:before:content-none prose-code:after:content-none prose-pre:rounded-2xl prose-pre:border prose-pre:border-white/10 prose-pre:bg-[#0a0c12]">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  urlTransform={(value: string) => value}
                  components={{
                    a: ({ href, children }) => {
                      const isInternalWikiLink = href && !href.startsWith('http://') && !href.startsWith('https://') && !href.startsWith('#') && !href.startsWith('mailto:') && !href.startsWith('tel:');
                      if (isInternalWikiLink) {
                        return (
                          <button
                            type="button"
                            onClick={() => openInternalWikiLink(href)}
                            className="cursor-pointer text-left text-sky-300 underline underline-offset-4 transition hover:text-sky-200"
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
                          className="cursor-pointer text-sky-300 underline underline-offset-4 transition hover:text-sky-200"
                        >
                          {children}
                        </a>
                      );
                    },
                  }}
                >
                  {markdown}
                </ReactMarkdown>
              </div>
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center space-y-6 text-center">
              <BookOpen className="h-16 w-16 text-white/20" />
              <div>
                <p className="text-2xl font-bold text-white">Select a page</p>
                <p className="mt-2 max-w-md text-white/35">{currentWiki?.name} is loaded. Pick a page from the left, or use Knowledge Chat, Wiki Builder, Graph View, Upload, Maintenance, or Settings.</p>
              </div>
            </div>
          )}
        </div>
      </main>

      {wikiAction && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm"
          onClick={() => {
            setWikiAction(null);
            setWikiNameInput('');
          }}
        >
          <div
            className="w-full max-w-xl rounded-[2rem] border border-white/10 bg-[#0a0c12] p-6 shadow-[0_30px_100px_rgba(0,0,0,0.6)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-bold uppercase tracking-[0.18em] text-white/35">Wiki Action</p>
                <h3 className="mt-2 text-2xl font-black text-white">
                  {wikiAction === 'create' && 'Create a New Wiki'}
                  {wikiAction === 'rename' && `Rename ${currentWiki?.name}`}
                  {wikiAction === 'delete' && `Delete ${currentWiki?.name}?`}
                </h3>
                <p className="mt-3 text-sm leading-6 text-white/55">
                  {wikiAction === 'delete'
                    ? 'This removes the selected wiki, including its pages, sources, and embeddings. This only affects the current wiki.'
                    : 'Give the wiki a clear name. It will stay fully isolated from your other knowledge bases.'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setWikiAction(null);
                  setWikiNameInput('');
                }}
                className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-white/60 transition hover:bg-white/10 hover:text-white"
                aria-label="Close wiki action"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {wikiAction !== 'delete' && (
              <input
                type="text"
                value={wikiNameInput}
                onChange={(event) => setWikiNameInput(event.target.value)}
                placeholder="Wiki name"
                className="mt-6 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none focus:border-primary/40"
                autoFocus
              />
            )}

            <div className="mt-6 flex flex-wrap justify-end gap-2">
              <button
                onClick={() => {
                  setWikiAction(null);
                  setWikiNameInput('');
                }}
                className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-white/70 transition hover:bg-white/10"
              >
                Cancel
              </button>
              <button
                onClick={() => void submitWikiAction()}
                disabled={isSavingWikiAction || (wikiAction !== 'delete' && !wikiNameInput.trim())}
                className="rounded-2xl bg-primary px-4 py-3 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
              >
                {isSavingWikiAction ? 'Saving...' : wikiAction === 'delete' ? 'Delete Wiki' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
