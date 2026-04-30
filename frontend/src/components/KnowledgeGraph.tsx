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

interface GraphProps {
  pages: string[];
  onNodeClick: (node: any) => void;
}

const KnowledgeGraph: React.FC<GraphProps> = ({ pages, onNodeClick }) => {
  const data = useMemo(() => {
    const nodes: Node[] = pages.map(p => ({ id: p, name: p.replace('.md', '') }));
    const links: Link[] = [];
    
    // Simple mock logic: connect everything to index.md if it exists
    if (pages.includes('index.md')) {
      pages.forEach(p => {
        if (p !== 'index.md') {
          links.push({ source: 'index.md', target: p });
        }
      });
    }

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
