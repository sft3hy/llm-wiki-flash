import React, { useMemo, useCallback, useRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

interface Node {
  id: string;
  name: string;
  links?: string[];
  x?: number;
  y?: number;
  __bckgDimensions?: [number, number];
}

interface Link {
  source: string;
  target: string;
}

interface WikiPageSummary {
  name: string;
  title: string;
  links?: string[];
}

interface GraphProps {
  pages: WikiPageSummary[];
  onNodeClick: (node: any) => void;
}

const GOVERNANCE_PAGE_NAMES = new Set(['SCHEMA.md', 'index.md', 'log.md']);

/**
 * Build graph edges from both explicit link arrays AND implicit slug-based
 * cross-references. The backend extracts [[wikilinks]], but many LLM-generated
 * pages use bare-text mentions (e.g. "* republic-china") or inline prose that
 * references sibling concepts without link syntax. We detect those here.
 */
const buildLinks = (contentPages: WikiPageSummary[]): Link[] => {
  const pageNameSet = new Set(contentPages.map((p) => p.name));
  const seen = new Set<string>();
  const links: Link[] = [];

  const addLink = (source: string, target: string) => {
    if (source === target) return;
    const key = `${source}→${target}`;
    if (seen.has(key)) return;
    seen.add(key);
    links.push({ source, target });
  };

  for (const page of contentPages) {
    // 1. Explicit links from the backend (regex-extracted [[wikilinks]])
    if (page.links) {
      for (const target of page.links) {
        const slug = target.toLowerCase().replace(/ /g, '-');
        const matchedName =
          pageNameSet.has(target) ? target :
          pageNameSet.has(`${slug}.md`) ? `${slug}.md` :
          [...pageNameSet].find(
            (n) => n.toLowerCase().replace(/ /g, '-') === slug ||
                   n.toLowerCase().replace(/ /g, '-') === `${slug}.md`
          );
        if (matchedName) {
          addLink(page.name, matchedName);
        }
      }
    }

    // 2. Implicit: scan the page title for mentions of other page slugs
    //    This catches the common case where "Related Concepts" lists bare slugs
    //    or the title/body naturally mentions sibling concepts.
    const ownSlug = page.name.replace(/\.md$/, '');
    for (const other of contentPages) {
      if (other.name === page.name) continue;
      const otherSlug = other.name.replace(/\.md$/, '');
      const otherHuman = otherSlug.replace(/-/g, ' ');

      // If this page's title contains the other concept's humanized name
      // OR the other page's title contains this concept — create a link.
      const myTitle = page.title.toLowerCase();
      const mySlugHuman = ownSlug.replace(/-/g, ' ').toLowerCase();

      if (
        myTitle.includes(otherHuman.toLowerCase()) ||
        other.title.toLowerCase().includes(mySlugHuman)
      ) {
        addLink(page.name, other.name);
      }
    }
  }

  return links;
};

const KnowledgeGraph: React.FC<GraphProps> = ({ pages, onNodeClick }) => {
  const fgRef = useRef<any>(null);

  const data = useMemo(() => {
    const contentPages = pages.filter((p) => !GOVERNANCE_PAGE_NAMES.has(p.name));

    const nodes: Node[] = contentPages.map((p) => ({
      id: p.name,
      name: p.title || p.name.replace('.md', '').replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      links: p.links,
    }));
    const links = buildLinks(contentPages);

    return { nodes, links };
  }, [pages]);

  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const x: number = node.x ?? 0;
    const y: number = node.y ?? 0;
    const label: string = node.name || '';
    const radius = 5;

    // Outer glow
    ctx.beginPath();
    ctx.arc(x, y, radius + 2, 0, 2 * Math.PI, false);
    ctx.fillStyle = 'rgba(99, 102, 241, 0.25)';
    ctx.fill();

    // Solid node circle
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, 2 * Math.PI, false);
    ctx.fillStyle = '#6366f1';
    ctx.fill();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.lineWidth = 0.5;
    ctx.stroke();

    // Label
    const fontSize = Math.max(11 / globalScale, 3.5);
    ctx.font = `600 ${fontSize}px Inter, system-ui, sans-serif`;
    const textWidth = ctx.measureText(label).width;
    const padding = fontSize * 0.35;
    const bw = textWidth + padding * 2;
    const bh = fontSize + padding * 2;
    const labelY = y + radius + fontSize * 0.8;

    // Label background pill
    ctx.fillStyle = 'rgba(10, 12, 18, 0.85)';
    ctx.beginPath();
    const pillRadius = bh / 2;
    ctx.roundRect(x - bw / 2, labelY - bh / 2, bw, bh, pillRadius);
    ctx.fill();

    // Label text
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#cbd5e1';
    ctx.fillText(label, x, labelY);

    // Store dimensions for pointer area
    node.__bckgDimensions = [Math.max(bw, radius * 2), bh + radius * 2 + fontSize * 0.8];
  }, []);

  const paintPointerArea = useCallback((node: any, color: string, ctx: CanvasRenderingContext2D) => {
    const x: number = node.x ?? 0;
    const y: number = node.y ?? 0;
    const dims = node.__bckgDimensions;
    if (!dims) return;
    ctx.fillStyle = color;
    ctx.fillRect(x - dims[0] / 2, y - 5, dims[0], dims[1]);
  }, []);

  return (
    <div className="w-full h-full glass rounded-xl overflow-hidden border border-border">
      <ForceGraph2D
        ref={fgRef}
        graphData={data}
        linkColor={() => 'rgba(148, 163, 184, 0.45)'}
        linkWidth={1.5}
        linkDirectionalParticles={2}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleSpeed={0.004}
        linkDirectionalParticleColor={() => 'rgba(99, 102, 241, 0.7)'}
        backgroundColor="rgba(0,0,0,0)"
        onNodeClick={onNodeClick}
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={paintPointerArea}
        cooldownTicks={80}
        d3AlphaDecay={0.04}
        d3VelocityDecay={0.25}
      />
    </div>
  );
};

export default KnowledgeGraph;
