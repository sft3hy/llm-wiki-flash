# LLM Wiki Flash - Project Features

## Overview
LLM Wiki Flash is a persistent, compounding personal knowledge base that transforms raw information into a durable, structured knowledge layer. Built for 100% local execution using Ollama and ChromaDB.

## Core Philosophy: Vector vs. Wiki

The system operates on two distinct layers to ensure knowledge is both searchable and durable:

### 1. The Vector Layer (Ephemeral & Fast)
Powered by **ChromaDB** and **nomic-embed-text**, this layer handles high-speed semantic retrieval.
- **Purpose**: To find needles in haystacks. It indexes raw uploads and compiled wiki pages.
- **Role**: Serves as the "short-term memory" for the LLM during synthesis and the engine for the Knowledge Chat.

### 2. The Wiki Layer (Durable & Structured)
The "Source of Truth" stored in `/data/wiki/` as a collection of interlinked Markdown files.
- **Purpose**: To provide a human-readable, version-controlled repository of synthesized knowledge.
- **Role**: Unlike raw vector chunks, the Wiki represents **Atomic Concepts**. The LLM synthesizes these articles by reading across multiple sources to resolve contradictions and build a cohesive narrative.

## System Architecture

### 📂 Backend (`/backend`)
A FastAPI service orchestrating the local intelligence pipeline.

#### **`core/ingest.py` (The Synthesis Engine)**
- **Deduplication**: Content-based hashing prevents redundant indexing.
- **Global Synthesis**: Instead of file-by-file processing, it looks at a whole corpus, extracts global concepts, and uses RAG to write comprehensive articles.

#### **`core/query.py` (The Search Engine)**
- **MMR Retrieval**: Uses Max Marginal Relevance to ensure context diversity, preventing redundant snippets from blocking relevant info.
- **Hallucination Guard**: A two-layer system (Prompt + Regex Post-processor) that ensures `[[links]]` in chat only point to real pages.

#### **`core/llm_provider.py`**: Standardized interface for local Ollama models. Default: `gemma4:e4b`.

#### **`utils/git_manager.py`**: Automatically commits every wiki change to a local Git repository.

### 🎨 Frontend (`/frontend`)
A premium React application built for exploration and ingestion.

- **Knowledge Chat**: Features full Markdown rendering and **Interactive Wikilinks**. Clicking a link in the chat instantly navigates you to that wiki page.
- **Unified Ingestion**: A streamlined native file/folder picker. Includes book-themed "page-turning" animations during the synthesis process.
- **Knowledge Graph**: A 2D force-directed graph visualizing the connections between your synthesized concepts.

## Governance (The Schema)

- **Atomic Decomposition**: Knowledge is broken into concept-specific `.md` files.
- **Wikilinks**: Mentions of other pages use `[[kebab-case-links]]`.
- **Conflicts**: Contradictory info is appended to `## Conflict` sections with dates and provenance.
- **Local First**: No data ever leaves your machine. All processing happens via Ollama.

## Key Features

### 1. Document Ingestion Pipeline
- **Flexible Input**: Accepts files, folders, or Obsidian-style vaults
- **Automatic Processing**: Content-based hashing prevents redundant indexing
- **Global Concept Extraction**: Analyzes entire corpus to identify key concepts
- **RAG-Based Synthesis**: Uses Retrieval-Augmented Generation to write comprehensive articles
- **Progress Tracking**: Real-time progress updates via Server-Sent Events (SSE)
- **Queue Management**: Document processing with retry mechanisms and failure handling

### 2. Knowledge Synthesis Engine
- **Multi-Phase Retrieval**: 4-phase hybrid retrieval pipeline:
  - Phase 1: TokenSearchService (fast lexical keyword search)
  - Phase 1.5: Chroma vector search (semantic boost via OllamaEmbedder)
  - Phase 2: GraphExpansionService (wiki-link graph expansion with 2-hop traversal)
  - Phase 3: BudgetAllocator (token-budget-controlled page selection)
  - Phase 4: ContextAssemblyService (citation-numbered context block)
- **Context-Aware Generation**: Synthesizes information while respecting wiki purpose and existing content
- **Conflict Detection**: Automatically identifies and documents contradictory information
- **Purpose Awareness**: Maintains and evolves wiki purpose based on synthesis context

### 3. Intelligent Query System
- **Semantic Search**: Combines keyword matching with vector similarity for accurate results
- **Graph-Based Expansion**: Traverses wiki-link connections to find related concepts
- **Budget-Controlled Retrieval**: Optimizes context length within token limits
- **Dynamic Context Assembly**: Builds coherent context with proper citations
- **Multi-Turn Chat**: Maintains conversation history for contextual responses
- **Purpose Updates**: Allows evolution of wiki purpose through explicit `<UPDATE_PURPOSE>` tags

### 4. Knowledge Graph Visualization
- **Interactive 2D Graph**: Force-directed layout showing concept relationships
- **Node Exploration**: Click nodes to view corresponding wiki pages
- **Edge Insights**: Visualize connections between related concepts
- **Layout Control**: Pan, zoom, and rearrange graph elements

### 5. Version Control & Audit Trail
- **Git Integration**: Automatic commits for all wiki changes
- **Compilation Log**: Detailed log.md tracking all synthesis operations
- **Change Tracking**: Shows created/updated pages in real-time
- **Rollback Capability**: Full history available through Git

### 6. Multi-Wiki Support
- **Isolated Knowledge Bases**: Maintain separate wikis for different topics
- **Cross-Wiki Querying**: Optional sharing of context between wikis
- **Independent Configuration**: Each wiki has its own purpose, schema, and settings
- **Selective Rebuilding**: Rebuild embeddings per wiki without affecting others

### 7. Local-First Privacy & Security
- **100% Local Execution**: No data leaves your machine
- **Ollama Integration**: All LLM processing through local Ollama instance
- **Embedding Privacy**: Vector embeddings stored locally in ChromaDB
- **No External Dependencies**: Self-contained with optional SearXNG for web search

### 8. Developer & Power User Features
- **RESTful API**: Comprehensive backend API for integration
- **CLI Interface**: Command-line tools for advanced operations
- **Extensible Architecture**: Modular design allows custom component integration
- **Docker Support**: Easy deployment with docker-compose
- **Configuration Management**: Environment-based configuration via `.env` files

## Technical Specifications

### Backend Technologies
- **Framework**: FastAPI (Python)
- **Vector Database**: ChromaDB
- **Embedding Model**: nomic-embed-text (via Ollama)
- **LLM Interface**: llama.cpp-compatible models via Ollama (default: gemma4:e4b)
- **Message Passing**: LangChain for LLM interactions
- **Real-Time Updates**: Server-Sent Events (SSE) for progress reporting
- **Database**: SQLite for task queues and chat history

### Frontend Technologies
- **Framework**: React with Vite
- **Styling**: Tailwind CSS
- **State Management**: React Context API
- **Graph Visualization**: D3.js-based force-directed layout
- **Markdown Rendering**: Remarkable or similar markdown parser
- **Routing**: React Router for SPA navigation

### Deployment Options
- **Docker Compose**: Single-command deployment with all dependencies
- **Manual Deployment**: Direct execution with Python and Node.js prerequisites
- **Development Mode**: Hot reloading for both backend and frontend

## Usage Workflows

### 1. Knowledge Base Creation
1. Start the system: `docker compose up --build`
2. Access frontend at `http://localhost:5173`
3. Create a new wiki or select default
4. Ingest documents via file/folder picker or vault import
5. Watch as the system synthesizes your knowledge base
6. Explore generated content through chat or knowledge graph

### 2. Knowledge Exploration
1. Use the chat interface to ask questions about your knowledge
2. Follow `[[wikilinks]]` to navigate between concepts
3. Explore relationships in the knowledge graph view
4. Update wiki purpose through conversational cues
5. Review compilation log for synthesis details

### 3. Knowledge Maintenance
1. Run periodic maintenance with `/meditate` endpoint
2. Review and resolve conflicts in `## Conflict` sections
3. Rebuild embeddings after major changes
4. Prune outdated information as needed
5. Export specific conversations to wiki pages

## Extensibility Points

### Custom Components
- **LLM Providers**: Extend `llm_provider.py` for alternative backends
- **Retrieval Algorithms**: Modify `query.py` retrieval phases
- **Synthesis Prompts**: Update prompts in `core/schema.py`
- **Storage Backends**: Replace ChromaDB with alternative vector stores
- **Frontend Widgets**: Add new visualization or interaction components

### API Endpoints
- **Wiki Management**: Create, read, update, delete wikis
- **Document Ingestion**: Upload files, process folders, ingest vaults
- **Query Operations**: Semantic search, graph exploration, Q&A
- **Builder Interface**: Research assistant with web search capabilities
- **Conversation Management**: Multi-turn chat with history tracking
- **Settings Control**: Retrieval parameters, model selection, purpose updates

## Quality Assurance Features

### Built-In Validation
- **Wiki Link Validation**: Ensures all `[[links]]` point to existing pages
- **Content Consistency**: Checks for contradictions during synthesis
- **Format Compliance**: Validates markdown structure and metadata
- **Reference Integrity**: Verifies all citations point to real sources

### Monitoring & Diagnostics
- **Progress Reporting**: Real-time updates via SSE channels
- **Logging**: Structured logging for all major operations
- **Error Handling**: Graceful degradation with informative error messages
- **Performance Metrics**: Timing and resource usage tracking

## Conclusion

LLM Wiki Flash represents a novel approach to personal knowledge management that combines the speed of vector search with the durability and structure of traditional wikis. By leveraging local LLMs and modern retrieval techniques, it creates a self-improving knowledge base that becomes more valuable with every document added, all while maintaining complete privacy and user control over their information.

The system is designed for both casual users seeking better organization of their personal knowledge and power users who need a sophisticated research assistant that can synthesize information across multiple sources while maintaining strict provenance and attribution.