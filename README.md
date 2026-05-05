# Wiki Agent (Local Edition)

A persistent, compounding personal knowledge base that transforms raw information into a durable, structured knowledge layer. Built for 100% local execution using Ollama and ChromaDB.

## 🧠 The Philosophy: Vector vs. Wiki

This system operates on two distinct layers to ensure knowledge is both searchable and durable:

### 1. The Vector Layer (Ephemeral & Fast)
Powered by **ChromaDB** and **nomic-embed-text**, this layer handles high-speed semantic retrieval.
- **Purpose**: To find needles in haystacks. It indexes raw uploads and compiled wiki pages.
- **Role**: Serves as the "short-term memory" for the LLM during synthesis and the engine for the Knowledge Chat.

### 2. The Wiki Layer (Durable & Structured)
The "Source of Truth" stored in `/data/wiki/` as a collection of interlinked Markdown files.
- **Purpose**: To provide a human-readable, version-controlled repository of synthesized knowledge.
- **Role**: Unlike raw vector chunks, the Wiki represents **Atomic Concepts**. The LLM synthesizes these articles by reading across multiple sources to resolve contradictions and build a cohesive narrative.

---

## 🏗️ System Architecture

### 📂 Backend (`/backend`)
A FastAPI service orchestrating the local intelligence pipeline.

*   **`core/ingest.py` (The Synthesis Engine)**: 
    - **Deduplication**: Content-based hashing prevents redundant indexing.
    - **Global Synthesis**: Instead of file-by-file processing, it looks at a whole corpus, extracts global concepts, and uses RAG to write comprehensive articles.
*   **`core/query.py` (The Search Engine)**: 
    - **MMR Retrieval**: Uses Max Marginal Relevance to ensure context diversity, preventing redundant snippets from blocking relevant info.
    - **Hallucination Guard**: A two-layer system (Prompt + Regex Post-processor) that ensures `[[links]]` in chat only point to real pages.
*   **`core/llm_provider.py`**: Standardized interface for local Ollama models. Default: `gemma4:e4b`.
*   **`utils/git_manager.py`**: Automatically commits every wiki change to a local Git repository.

### 🎨 Frontend (`/frontend`)
A premium React application built for exploration and ingestion.

*   **Knowledge Chat**: Features full Markdown rendering and **Interactive Wikilinks**. Clicking a link in the chat instantly navigates you to that wiki page.
*   **Unified Ingestion**: A streamlined native file/folder picker. Includes book-themed "page-turning" animations during the synthesis process.
*   **Knowledge Graph**: A 2D force-directed graph visualizing the connections between your synthesized concepts.

---

## 🚀 Getting Started

### Prerequisites
- **Docker & Docker Compose**
- **Ollama** installed on the host.
- Pull the required models:
  ```bash
  ollama pull gemma4:e4b
  ollama pull nomic-embed-text
  ```

### Launch
1.  **Launch**:
    ```bash
    docker compose up --build
    ```
2.  **Access**: `http://localhost:5173`
3.  **Ingest**: Click "Ingest" in the sidebar, select a folder (like an Obsidian Vault) or files, and watch the system synthesize your wiki.

---

## ⚖️ Governance (The Schema)
- **Atomic Decomposition**: Knowledge is broken into concept-specific `.md` files.
- **Wikilinks**: Mentions of other pages use `[[kebab-case-links]]`.
- **Conflicts**: Contradictory info is appended to `## Conflict` sections with dates and provenance.
- **Local First**: No data ever leaves your machine. All processing happens via Ollama.