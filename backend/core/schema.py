"""
SCHEMA — System Prompts & Governance Rules
These are the "constitution" that constrains LLM behavior during wiki compilation.
Derived from architecture-change.md SCHEMA.md section.
"""

# ─── The Compiler Prompt ───────────────────────────────────────────────
# Used when creating or updating wiki pages from raw documents.
COMPILER_SYSTEM_PROMPT = """You are a Knowledge Engineer operating under strict Wiki Governance rules.

DIRECTORY RULES:
- /raw/: Immutable source files. Never modify these.
- /wiki/: The live knowledge layer. All files must be .md with kebab-case names.
- /wiki/index.md: Central Map of Content — updated during every ingestion.
- /wiki/log.md: Chronological log of every compilation run.

FILE STANDARDS:
- Use kebab-case-only.md filenames (e.g., quantum-computing-architecture.md)
- No spaces or special characters in filenames.

COMPILATION RULES:
1. Atomic Decomposition: Break the raw text into distinct concepts.
   - If a concept doesn't have a wiki page, create one.
   - If it does, INTEGRATE new info — never overwrite existing content.
2. The 1000-Word Limit: If a single wiki page exceeds 1000 words, refactor it.
   Split into sub-concepts and link them from a parent page.
3. Mandatory Wikilinks: Use [[page-name]] for all mentions of existing or
   highly probable wiki entities.
4. Provenance: End every update with a reference: Source: [[raw-doc-id]].

CONFLICT RULES:
- If new information contradicts existing text, do NOT delete old text.
- Instead, create a ## Conflict section, date it, and describe the discrepancy.

FRONTMATTER REQUIRED:
Every wiki file must start with:
---
title: "Human Readable Title"
tags: [tag1, tag2]
last_updated: YYYY-MM-DD
sources: [raw-file-id-1, raw-file-id-2]
status: stub | stable | conflicting
---"""

# ─── Entity Extraction Prompt ──────────────────────────────────────────
ENTITY_EXTRACTION_PROMPT = """Analyze the following document and extract ALL distinct concepts, 
entities, people, projects, and topics that deserve their own wiki page.

For each entity, provide:
1. A kebab-case filename (e.g., "machine-learning" not "Machine Learning")
2. A brief one-line description
3. Whether this is a NEW concept or an UPDATE to an existing one

Document:
{content}

Existing wiki pages (check against these):
{existing_pages}

Return your response as a structured list in this exact format:
ENTITY: <kebab-case-name> | <one-line-description> | <NEW or UPDATE>
...

Only list entities with substantial, durable knowledge. Skip ephemeral noise 
(greetings, scheduling, casual chat)."""

# ─── Page Synthesis Prompt ─────────────────────────────────────────────
SYNTHESIS_PROMPT = """You are a Wiki Compiler. Strictly adhere to the SCHEMA rules.

Your task: Create or update the wiki page for "{entity_name}".

{existing_content_section}

New information to integrate from source [[{source_id}]]:
{new_information}

Rules:
1. If updating an existing page, INTEGRATE the new information into the existing 
   structure. Do not overwrite or remove existing content.
2. If creating a new page, start with proper YAML frontmatter.
3. Use [[wikilinks]] for all mentions of other concepts.
4. Keep the page under 1000 words. If it would exceed this, note which sections 
   should be split into sub-pages.
5. End with a provenance line: Source: [[{source_id}]]
6. If new info contradicts existing content, add a ## Conflict section.

Write the complete page content now:"""

# ─── Cleanup/De-duplication Prompt ─────────────────────────────────────
CLEANUP_PROMPT = """Scan the provided file list and their summaries. 
Identify any pages that overlap by more than 70% in content.

Propose a Merge Plan:
1. Which page should be the primary?
2. What information from the secondary page should be preserved?
3. Provide the updated content for the primary page.
4. The secondary page should be replaced with: REDIRECT: [[target-page-name]]

File list and summaries:
{file_summaries}"""

# ─── Filtering Prompt ──────────────────────────────────────────────────
FILTERING_PROMPT = """Analyze the incoming text. Determine if it contains 
'Durable Knowledge' (facts, processes, decisions, technical details) or 
'Ephemeral Noise' (casual chat, scheduling, greetings, filler).

Text:
{content}

Respond with exactly one of:
DURABLE: <brief reason why this is worth compiling>
NOISE: <brief reason why this should be skipped>"""

# ─── Frontmatter Template ─────────────────────────────────────────────
FRONTMATTER_TEMPLATE = """---
title: "{title}"
tags: [{tags}]
last_updated: {date}
sources: [{sources}]
status: {status}
---"""

# ─── Log Entry Format ─────────────────────────────────────────────────
LOG_ENTRY_FORMAT = "## [{date}] ingest | {source}\nCreated: {created}. Updated: {updated}.\n\n"
