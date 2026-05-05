# AI Wiki Builder

## Architecture

The local pipeline is implemented as a modular backend package in `backend/wiki_builder/`.

- `config.py`: runtime configuration for vault paths, local storage, and search backends
- `search.py`: query generation, SearXNG integration, fallback JSON search API client, and URL deduplication
- `fetch.py`: live HTTP fetch + HTML main-content extraction + raw/cleaned source persistence
- `obsidian.py`: Markdown note generation for `vault/{topic}/sources/`
- `wiki.py`: deterministic concept extraction and concept-page generation with Obsidian wikilinks
- `pipeline.py`: orchestration entrypoint exposing `PipelineRunner.run_pipeline(topic)`
- `logging_utils.py`: structured JSONL logging to `logs/{topic}.log`

## Data Flow

1. Generate multiple search queries from the topic.
2. Call SearXNG first, then a configurable JSON API fallback if needed.
3. Deduplicate source URLs and fetch each page over HTTP.
4. Store raw content, cleaned text, metadata JSON, and a source manifest in `data/raw_sources/{topic}/`.
5. Convert each fetched source into an Obsidian note in `vault/{topic}/sources/`.
6. Build concept-based wiki pages plus `index.md` in `vault/{topic}/wiki/`.
7. Log each stage as structured JSON lines in `logs/{topic}.log`.

## Setup

You must provide an absolute Obsidian vault path. Automatic vault discovery is intentionally not used.

### SearXNG

If you want local-first search, run a SearXNG instance and pass its base URL:

```bash
python3 -m wiki_builder.cli \
  --topic "Edge AI" \
  --vault /absolute/path/to/obsidian_vault \
  --searxng-url http://localhost:8080
```

### Fallback Search API

If SearXNG is unavailable, point the pipeline at a compatible JSON endpoint:

```bash
python3 -m wiki_builder.cli \
  --topic "Edge AI" \
  --vault /absolute/path/to/obsidian_vault \
  --search-api-url http://localhost:9000/search
```

The fallback endpoint is expected to return JSON with a top-level `results` list containing `title`, `url`, and `snippet`-like fields, unless you customize the client configuration in code.

## Running Tests

The tests use only local fixtures and in-process HTTP servers, so they do not require external network access.

```bash
python3 -m unittest discover -s tests -v
```

## Example Result

`PipelineRunner.run_pipeline("Edge AI")` returns a structured summary with:

- discovered source count
- successful and failed fetch counts
- output directories for raw sources, Obsidian source notes, and wiki pages
- log file location
