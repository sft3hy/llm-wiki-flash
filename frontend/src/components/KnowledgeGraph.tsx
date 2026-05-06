import React, { useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

interface Node {
  id: string;
  name: string;
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

const KnowledgeGraph: React.FC<GraphProps> = ({ pages, onNodeClick }) => {
  const data = useMemo(() => {
    const contentPages = pages.filter(p => !GOVERNANCE_PAGE_NAMES.has(p.name));
    
    const nodes: Node[] = contentPages.map(p => ({ id: p.name, name: p.title || p.name.replace('.md', '') }));
    const links: Link[] = [];
    
    // Connect actual extracted links
    contentPages.forEach(p => {
      if (p.links) {
        p.links.forEach(target => {
          // Verify target node exists and is not a governance page
          if (contentPages.some(page => page.name === target)) {
            links.push({ source: p.name, target: target });
          }
        });
      }
    });

    return { nodes, links };
  }, [pages]);

  return (
    <div className="w-full h-full glass rounded-xl overflow-hidden border border-border">
      <ForceGraph2D
        graphData={data}
        nodeLabel="name"
        nodeColor={() => "#6366f1"}
        linkColor={() => "rgba(255, 255, 255, 0.1)"}
        backgroundColor="rgba(0,0,0,0)"
        onNodeClick={onNodeClick}
        nodeRelSize={6}
      />
    </div>
  );
};

export default KnowledgeGraph;
