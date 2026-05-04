import os
import sys
import json
import time
import asyncio
from typing import List, Dict

# Add the backend path to sys.path so we can import core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Use a temporary Chroma directory for evaluation
EVAL_CHROMA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".eval_chroma"))

MODELS_TO_TEST = [
    "qwen3.5:9b",
    "ministral-3:8b",
    "ibm/granite4.1:8b",
    "llama3.2:1b",
    "gemma4:e2b",
    "gemma4:e4b"
]

# Benchmark queries targeting different capabilities based on computational-intelligence.md
QUERIES = [
    {
        "id": "factual",
        "type": "Factual QA",
        "query": "What year was Artificial intelligence founded as an academic discipline?",
        "ground_truth": "Artificial intelligence was founded as an academic discipline in 1956."
    },
    {
        "id": "multi_hop",
        "type": "Multi-hop Reasoning",
        "query": "What architectural development further accelerated the growth of AI that had initially increased due to the use of graphics processing units?",
        "ground_truth": "The transformer architecture in 2017 further accelerated the growth."
    },
    {
        "id": "retrieval",
        "type": "Retrieval-dependent",
        "query": "According to the rules provided in the text, what should you do if updating an existing page?",
        "ground_truth": "If updating an existing page, INTEGRATE the new information into the existing structure."
    }
]

async def setup_eval_vectorstore(doc_path: str):
    print(f"Setting up evaluation vector store from {doc_path}...")
    if not os.path.exists(doc_path):
        raise FileNotFoundError(f"Cannot find document at {doc_path}")

    with open(doc_path, "r") as f:
        content = f.read()

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_text(content)

    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    vectorstore = Chroma(
        collection_name="eval_wiki",
        embedding_function=embeddings,
        persist_directory=EVAL_CHROMA_DIR
    )
    
    vectorstore.add_texts(texts=chunks, metadatas=[{"source": doc_path} for _ in chunks])
    return vectorstore

async def run_evaluation():
    doc_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'wiki', 'computational-intelligence.md'))
    vectorstore = await setup_eval_vectorstore(doc_path)
    
    results = {}

    for model in MODELS_TO_TEST:
        print(f"\n🚀 Evaluating model: {model}")
        llm = ChatOllama(model=model, temperature=0.0)
        
        model_results = []
        
        for query_obj in QUERIES:
            print(f"  📝 Query: {query_obj['query']}")
            
            # Retrieve context once per query
            search_results = vectorstore.similarity_search(query_obj['query'], k=2)
            context = "\n\n".join([doc.page_content for doc in search_results])
            
            system_instr = f"""You are a concise answering system. Answer the user's question based strictly on the WIKI CONTEXT below.
WIKI CONTEXT:
{context}"""
            messages = [
                SystemMessage(content=system_instr),
                HumanMessage(content=query_obj['query'])
            ]
            
            query_iterations = []
            
            # Run 3 times to measure stability and average latency
            for i in range(3):
                start_time = time.perf_counter()
                try:
                    response = await llm.ainvoke(messages)
                    latency = time.perf_counter() - start_time
                    answer = response.content.strip()
                    
                    query_iterations.append({
                        "iteration": i + 1,
                        "latency": latency,
                        "answer": answer
                    })
                    print(f"    - Iteration {i+1}: {latency:.2f}s")
                except Exception as e:
                    print(f"    - Iteration {i+1} Failed: {e}")
                    query_iterations.append({
                        "iteration": i + 1,
                        "latency": 0,
                        "answer": f"ERROR: {str(e)}"
                    })
            
            model_results.append({
                "query_id": query_obj["id"],
                "query": query_obj["query"],
                "ground_truth": query_obj["ground_truth"],
                "iterations": query_iterations
            })
            
        results[model] = model_results
        
    # Save results
    output_path = os.path.join(os.path.dirname(__file__), "eval_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
        
    print(f"\n✅ Evaluation complete! Results saved to {output_path}")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
