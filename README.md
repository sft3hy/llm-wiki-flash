# Wiki Agent (Karpathy Edition)

A persistent, compounding personal knowledge base built with an agentic LLM compilation engine. Inspired by the "LLM Wiki" concept, this system transforms raw information into a durable, structured knowledge layer.

## 🧠 The Philosophy
Unlike traditional RAG which searches raw chunks every time, **Wiki Agent** compiles knowledge *on-ingest*. It acts as a digital "second brain" that:
1.  **Synthesizes**: Reads raw documents and extracts atomic concepts.
2.  **Evolves**: Integrates new info into existing pages without overwriting.
3.  **Governs**: Maintains strict schema integrity and link health.
4.  **Compensates**: Intelligently tiers tasks between fast local models and powerful cloud models.

---

## 🏗️ System Architecture

### 📂 Backend (`/backend`)
The backend is a FastAPI service that drives the agentic maintenance loop.

*   **`main.py`**: The API entry point. Handles chat, ingestion, and global maintenance (meditate) triggers.
*   **`core/ingest.py`**: The **Ingest Engine**. Orchestrates the multi-step compilation process: filtering noise, extracting entities, finding relevance, and synthesizing markdown.
*   **`core/llm_provider.py`**: The **Intelligence Tiering Layer**.
    *   **Intelligent Tiering**: Routes small tasks (filtering) to `gemma4:e2b`, medium tasks (extraction) to `gemma4:e4b`, and hard synthesis to **Groq**.
    *   **Resilience**: Automatically falls back to local models if Groq hits rate limits (429).
    *   **Speed**: Suppresses "thinking" monologues for faster inference.
*   **`core/schema.py`**: The **Constitution**. Defines the system prompts and governance rules that constrain the AI's behavior.
*   **`core/lint.py`**: The **Librarian**. Performs non-LLM checks for broken wikilinks, orphan pages, and content conflicts.
*   **`core/git_manager.py`**: The **Persistence Layer**. Automatically commits every wiki change to a local Git repository for full auditability and version control.
*   **`config.py`**: Central configuration for model IDs, providers, and storage paths.

### 🎨 Frontend (`/frontend`)
A modern, dark-mode React application built with Vite and Tailwind CSS.

*   **`App.tsx`**: The main layout. Implements a **Chat-centric** interface where exploration is the default focus.
*   **`components/ChatView.tsx`**: The primary interaction point. Features a "Wiki Assistant" that knows your entire indexed knowledge. Includes quick actions for empty states.
*   **`components/MeditationView.tsx`**: The **Maintenance Center**.
    *   **Maintenance Tab**: Trigger the global "Meditation" loop and view live compilation logs.
    *   **Librarian Tab**: View health reports and fix broken knowledge connections.
*   **`components/KnowledgeGraph.tsx`**: A d3-based visualization of your knowledge nodes and their relationships.
*   **`components/ModelSelector.tsx`**: Allows switching between specific models or enabling "Smart (Auto Tiering)" mode.

---

## 🚀 Getting Started

### Prerequisites
- **Docker & Docker Compose**
- **Ollama** (Running locally with `gemma4:e2b` and `gemma4:e4b` pulled)
- **Groq API Key** (Optional, but recommended for high-quality synthesis)

### Quick Start
1.  **Environment**: Create a `.env` file in the root:
    ```bash
    GROQ_API_KEY=your_key_here
    OLLAMA_BASE_URL=http://host.docker.internal:11434
    ```
2.  **Launch**:
    ```bash
    docker compose up --build
    ```
3.  **Access**: Open `http://localhost:5173`
4.  **Ingest**: Upload a raw source (PDF, TXT) and trigger the **Maintenance Loop**.

---

## ⚖️ Governance Rules (The Schema)
- **Atomic Decomposition**: Concepts are broken into distinct `.md` files.
- **Kebab-Case**: All filenames must be `kebab-case-only.md`.
- **Wikilinks**: Mentions of other pages use `[[page-name]]`.
- **Conflicts**: Conflicting information is never deleted; it's appended to a `## Conflict` section.
- **Provenance**: Every page ends with a reference to its source document: `Source: [[raw-doc-id]]`.