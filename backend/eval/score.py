import os
import sys
import json
import math
from typing import List, Dict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from langchain_ollama import OllamaEmbeddings

# Pure python cosine similarity to avoid external dependencies
def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot_product = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot_product / (mag1 * mag2)

def calculate_conciseness(answer: str, ground_truth: str) -> float:
    # Penalize if answer is much longer than ground truth
    len_ans = len(answer.split())
    len_gt = len(ground_truth.split())
    
    if len_ans == 0:
        return 0.0
    
    # If it's less than or equal to 1.5x the length, perfect conciseness
    if len_ans <= len_gt * 1.5:
        return 1.0
        
    # Otherwise linearly penalize
    penalty = (len_ans - (len_gt * 1.5)) / (len_gt * 1.5)
    return max(0.0, 1.0 - penalty)

def calculate_stability(iterations: List[Dict]) -> float:
    answers = [it["answer"].lower().strip() for it in iterations]
    if not answers:
        return 0.0
    
    # Simple metric: percentage of answers that match the most common answer
    from collections import Counter
    counts = Counter(answers)
    most_common_count = counts.most_common(1)[0][1]
    
    return most_common_count / len(answers)

def calculate_grounding(answer: str, ground_truth: str) -> float:
    # A proxy for grounding without a complex LLM-as-a-judge: 
    # Check if key tokens in ground truth exist in the answer.
    # It penalizes answers that miss the core concepts (hallucinations/unrelated).
    gt_tokens = set(ground_truth.lower().replace('.', '').replace(',', '').split())
    ans_tokens = set(answer.lower().replace('.', '').replace(',', '').split())
    
    # Remove common stop words for better overlap check
    stop_words = {"the", "a", "an", "is", "in", "and", "of", "to", "what", "how", "according"}
    gt_core = gt_tokens - stop_words
    
    if not gt_core:
        return 1.0
        
    overlap = gt_core.intersection(ans_tokens)
    return len(overlap) / len(gt_core)

def format_markdown_table(headers: List[str], rows: List[List[str]]) -> str:
    header_str = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join(["---"] * len(headers)) + " |"
    
    row_strs = []
    for row in rows:
        row_strs.append("| " + " | ".join(str(item) for item in row) + " |")
        
    return "\n".join([header_str, separator] + row_strs)

def score_models():
    results_path = os.path.join(os.path.dirname(__file__), "eval_results.json")
    if not os.path.exists(results_path):
        print(f"Error: Could not find {results_path}. Run evaluate.py first.")
        return

    with open(results_path, "r") as f:
        results = json.load(f)
        
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    
    final_scores = []
    
    print("Scoring models... This may take a moment to compute embeddings.")
    
    for model, queries in results.items():
        total_accuracy = 0
        total_grounding = 0
        total_conciseness = 0
        total_stability = 0
        total_latency = 0
        valid_queries = 0
        
        for q in queries:
            gt_text = q["ground_truth"]
            gt_emb = embeddings.embed_query(gt_text)
            
            # Use the first iteration's answer for main metrics
            if not q["iterations"]:
                continue
                
            ans_text = q["iterations"][0]["answer"]
            if ans_text.startswith("ERROR:"):
                continue
                
            ans_emb = embeddings.embed_query(ans_text)
            
            acc = cosine_similarity(gt_emb, ans_emb)
            grnd = calculate_grounding(ans_text, gt_text)
            conc = calculate_conciseness(ans_text, gt_text)
            stab = calculate_stability(q["iterations"])
            
            avg_lat = sum(it["latency"] for it in q["iterations"]) / len(q["iterations"])
            
            total_accuracy += acc
            total_grounding += grnd
            total_conciseness += conc
            total_stability += stab
            total_latency += avg_lat
            valid_queries += 1
            
        if valid_queries > 0:
            avg_acc = total_accuracy / valid_queries
            avg_grnd = total_grounding / valid_queries
            avg_conc = total_conciseness / valid_queries
            avg_stab = total_stability / valid_queries
            avg_lat = total_latency / valid_queries
            
            # Weighted final score
            # 40% accuracy, 30% grounding, 20% stability, 10% conciseness
            final = (avg_acc * 0.4) + (avg_grnd * 0.3) + (avg_stab * 0.2) + (avg_conc * 0.1)
            
            final_scores.append({
                "Model": model,
                "Accuracy": round(avg_acc, 3),
                "Grounding": round(avg_grnd, 3),
                "Conciseness": round(avg_conc, 3),
                "Stability": round(avg_stab, 3),
                "Latency (s)": round(avg_lat, 2),
                "Final Score": round(final, 3)
            })

    # Sort by final score descending
    final_scores.sort(key=lambda x: x["Final Score"], reverse=True)
    
    headers = ["Model", "Accuracy", "Grounding", "Conciseness", "Stability", "Latency (s)", "Final Score"]
    rows = [[s[h] for h in headers] for s in final_scores]
    
    print("\n" + "="*50)
    print("🏆 FINAL EVALUATION RESULTS")
    print("="*50 + "\n")
    print(format_markdown_table(headers, rows))
    
    print("\n💡 RECOMMENDATIONS:")
    if final_scores:
        best_overall = final_scores[0]["Model"]
        best_speed = min(final_scores, key=lambda x: x["Latency (s)"])["Model"]
        best_factual = max(final_scores, key=lambda x: x["Accuracy"])["Model"]
        
        print(f"- Best Overall: {best_overall} (Highest final score based on weighted metrics)")
        print(f"- Best for Factual QA / Reasoning: {best_factual} (Highest accuracy and semantic similarity)")
        print(f"- Best for Speed: {best_speed} (Lowest latency)")

if __name__ == "__main__":
    score_models()
