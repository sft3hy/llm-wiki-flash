# LLM Wiki (Flash)

A persistent, compounding personal knowledge base built with LLMs.

## Features
- **Write-on-Ingest**: Knowledge is compiled once into markdown and kept current.
- **Compounding Artifact**: The wiki gets richer with every source added.
- **Meditation Loop**: Automated linting for contradictions and link health.
- **Hybrid Search**: Traverses the wiki with fallback to raw source RAG.
- **Git-Backed**: Every update is committed to a local git repository for full auditability.

## Tech Stack
- **Frontend**: React 19, Vite, Tailwind CSS, Shadcn UI.
- **Backend**: Python 3.13, FastAPI.
- **Infrastructure**: Docker & Docker Compose.

## Getting Started

### Prerequisites
- Docker & Docker Compose
- LLM API Keys (OpenAI/Anthropic)

### Setup
1. Clone the repository.
2. Create a `.env` file based on `.env.example`:
   ```env
   OPENAI_API_KEY=your_key_here
   ANTHROPIC_API_KEY=your_key_here
   ```
3. Start the system:
   ```bash
   docker-compose up --build
   ```
4. Access the UI at `http://localhost:3000`.

## Architecture
See the [Development Guide](file:///Users/samueltownsend/.gemini/antigravity/brain/960466c7-5d75-4888-9b65-84ef0a2a6bd4/development_guide.md.resolved) for a deep dive into the system design.