The LLM-Wiki Pattern: A Comprehensive Overview
The LLM-Wiki pattern is an architectural shift from "Retrieve-and-Generate" (RAG) to "Compile-and-Maintain." Instead of searching through thousands of disconnected text chunks at query time, the system proactively builds and manages a structured, human-readable markdown encyclopedia.
________________________________________
1. What does it do?
It transforms messy, high-volume raw data into a distilled knowledge graph.
•    Contextual Persistence: Knowledge is integrated into existing pages rather than stored as isolated snippets.
•    Human-in-the-loop: Because the output is a folder of Markdown files, a human can open the wiki, edit it, and the LLM will respect those manual edits in future cycles.
•    Relationship First: It prioritizes [[wikilinks]], allowing the LLM to navigate the knowledge base by following logical paths rather than just math-based vector similarity.
________________________________________
2. How the LLM Organizes Things
The system follows a Three-Layer Architecture:
1.    The Raw Layer (/raw): Immutable storage for every document, transcript, or note you ingest. These are never edited.
2.    The Wiki Layer (/wiki): A directory of "Atomic Notes." Each file represents a single concept, person, project, or entity.
3.    The Schema Layer (SCHEMA.md): The "Constitution." It defines the naming conventions, required YAML frontmatter, and linking rules the LLM must follow.
________________________________________
3. Core Processes to Support
A. The Ingestion/Compilation Loop
When a new document arrives:
1.    Analyze: The LLM reads the raw text and identifies which existing wiki pages need updates.
2.    Synthesize: It integrates the new facts into those pages or creates new ones if the concept is missing.
3.    Cross-Link: It scans for keywords to link to other existing pages using [[bracket syntax]].
B. The "Librarian" (Maintenance)
Periodically or triggered by growth:
•    De-duplication: Merging two pages that are actually about the same topic.
•    Indexing: Updating a central index.md or Map of Content (MOC).
•    Conflict Resolution: Flagging when new data contradicts a "settled" wiki page.
________________________________________
4. Key System Prompts
The "Compiler" Prompt (For Creating/Updating Pages)
"You are a Knowledge Engineer. Your task is to integrate the provided Raw Document into the existing Wiki.
1.    Identify Entities: Extract key concepts, projects, and people.
2.    Check Existence: If a page for a concept exists, append the new information in a logical section.
3.    Atomic Writing: If it doesn't exist, create a new Kebab-case .md file.
4.    Wikilinks: Wrap all recognized concepts in [[wikilinks]].
5.    Provenance: End every update with a reference: Source: [[raw-doc-id]]."
The "Clean-up" Prompt (For De-duplication)
"Scan the provided file list. Identify any pages that overlap by more than 70% in content.
Propose a Merge Plan:
1.    Which page should be the primary?
2.    What information from the secondary page should be preserved?
3.    Provide the updated content for the primary page and mark the secondary for deletion."
The "Filtering" Prompt (For Noise Reduction)
"Analyze the incoming text. Determine if it contains 'Durable Knowledge' (facts, processes, decisions) or 'Ephemeral Noise' (casual chat, scheduling, greetings).
ONLY proceed to compilation if the content contains Durable Knowledge. If it is noise, summarize it in the log.md and do not update the Wiki."
________________________________________
5. Why this beats standard RAG
•    Transparency: You can browse your "database" with any text editor.
•    No Cold Start: RAG often fails on "What happened last month?" because it grabs the wrong chunks. The Wiki has a "History" or "Timeline" page that is always updated.
•    Cost: You process the data once during compilation, rather than paying for high-token retrieval every time a user asks a question.
Would you like a sample SCHEMA.md file that defines the exact structure for your LLM to follow?


This SCHEMA.md is the "Source of Truth" for your LLM. In an LLM-Wiki setup, you provide this file in the system prompt to ensure the agent acts as a disciplined librarian rather than a creative writer.
________________________________________
SCHEMA.md: Wiki Governance & Compilation Rules
1. Goal
To maintain a high-density, interlinked knowledge base where information is atomic, persistent, and discoverable.
2. Directory Structure
•    /raw/: Immutable source JSON/Text files. Filename format: YYYYMMDD-HHMM-[source-slug].json.
•    /wiki/: The live knowledge layer. All files must be .md.
•    /wiki/index.md: The central "Map of Content" updated during every ingestion.
•    /wiki/log.md: Chronological log of every "Compilation Run."
3. File Standards
Filenaming
•    Use kebab-case-only.md.
•    No spaces or special characters.
•    Example: quantum-computing-architecture.md instead of Quantum Computing Architecture.md.
Metadata (Frontmatter)
Every wiki file must start with this YAML block:
---
title: "Human Readable Title"
tags: [tag1, tag2]
last_updated: YYYY-MM-DD
sources: [raw-file-id-1, raw-file-id-2]
status: [stub | stable | conflicting]
---
4. Compilation Rules
When the LLM receives new text, it must follow these steps:
1.    Atomic Decomposition: Break the raw text into distinct concepts.
o    Rule: If a concept doesn't have a file, create one.
o    Rule: If it does, merge the new info. Do not overwrite; integrate.
2.    The 1000-Word Limit: If a single wiki page exceeds 1000 words, it must be refactored. The LLM must split it into sub-concepts (e.g., project-x-specs.md and project-x-timeline.md) and link them from a parent page.
3.    Mandatory Wikilinks:
o    Use [[page-name]] for all mentions of existing or highly probable wiki entities.
o    If unsure if a page exists, check index.md first.
5. Conflict & Cleanup Rules
•    Contradictions: If new information contradicts existing text in /wiki/, do not delete the old text. Instead, create a ## Conflict section, date it, and describe the discrepancy between the sources.
•    De-duplication: If the LLM realizes two pages (e.g., llm-rag.md and retrieval-augmented-generation.md) are the same, it must perform a Merge:
1.    Combine content into the most descriptive title.
2.    Replace the deleted file's content with: REDIRECT: [[target-page-name]].
•    Formatting: Use standard Markdown (headers, bullet points, code blocks). No bolding for emphasis; use headers for structure.
6. Log Entry Format
For every ingestion, append to log.md:
[YYYY-MM-DD HH:MM] - Ingested [[raw-file-id]]. Created: [[new-page-1]]. Updated: [[existing-page-1]].
________________________________________
How to use this:
Include this text in your API's system prompt: "Act as a Wiki Compiler. You must strictly adhere to the rules defined in the provided SCHEMA.md for all file operations."
Do you want to see the Python class that would parse this schema to trigger the LLM's file updates?


To code a complete LLM-Wiki solution, you need to move beyond simple prompts and implement an event-driven architecture that handles the "compilation" of raw data into persistent knowledge. [1] 
1. The Core Implementation Logic
Unlike a standard chat API, the LLM-Wiki must manage state across three layers: [1] 
•    Layer 1: Raw Storage (Immutable): Every POST to /ingest saves a permanent record in s3://base/raw/. This allows you to "re-compile" the entire wiki if your schema or model changes.
•    Layer 2: The Wiki (Mutable): This is a live directory of markdown files. The agent must have "write" permissions here to update, merge, or create files.
•    Layer 3: The Schema (The Rules): A configuration file (e.g., SCHEMA.md) that acts as the "system instructions" for the agent. [1, 2, 3, 4, 5] 
2. Functional Requirements for the Code
To make the system autonomous, your solution must support these specific processes:
•    Multi-Page Synthesis: A single raw document should trigger updates to 5–15 different wiki pages (e.g., updating a person's page, a project's timeline, and a concept definition simultaneously).
•    Incremental Compiling: Instead of re-writing a file, the code must prompt the LLM to integrate new facts into existing content, maintaining a "provenance" footer that links back to the raw source ID.
•    Navigation & Discovery: The system must maintain an index.md (content-oriented catalog) and a log.md (chronological record). The LLM reads the index.md first to understand what it already knows before it begins writing. [5, 6, 7, 8, 9] 
3. Technical Stack & Integration
•    Standardized Communication: Use the Model Context Protocol (MCP) if you want your LLM (like Claude) to treat your S3 bucket as a native filesystem it can explore and edit.
•    Search Infrastructure: As the wiki grows beyond ~100 pages, the LLM may struggle to read the entire index. Implement a hybrid search (like BM25) to help the agent find relevant wiki pages to update.
•    Docker Orchestration: Use a multi-container setup where your FastAPI backend handles the API/S3 logic and a separate LLM worker handles the heavy synthesis tasks. [10, 11, 12, 13, 14] 
4. Human-in-the-Loop Safeguards [10] 
While the LLM is the "writer," you remain the "editor-in-chief." Your code should support:
•    Conflict Sections: If new data contradicts existing wiki content, the schema should force the LLM to create a ## Conflict header rather than deleting old information.
•    Verification: Budget time to spot-check the generated wiki, as LLMs may synthesize without citing unless strictly forced by your schema. [7, 8] 
How should we handle conflicts? Should the system flag them for your review or should it automatically create a "discussion" section within the wiki page?




