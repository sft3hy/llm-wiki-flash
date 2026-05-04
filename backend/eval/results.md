| Model | Accuracy | Grounding | Conciseness | Stability | Latency (s) | Final Score |
| --- | --- | --- | --- | --- | --- | --- |
| gemma4:e4b | 0.984 | 1.0 | 1.0 | 1.0 | 4.38 | 0.994 |
| gemma4:e2b | 0.979 | 1.0 | 1.0 | 1.0 | 2.83 | 0.992 |
| llama3.2:1b | 0.951 | 0.926 | 1.0 | 1.0 | 0.48 | 0.958 |
| qwen3.5:9b | 0.918 | 0.778 | 1.0 | 1.0 | 19.6 | 0.901 |
| ibm/granite4.1:8b | 0.897 | 1.0 | 0.333 | 1.0 | 2.79 | 0.892 |
| ministral-3:8b | 0.934 | 0.681 | 0.689 | 1.0 | 1.7 | 0.847 |

💡 RECOMMENDATIONS:
- Best Overall: gemma4:e4b (Highest final score based on weighted metrics)
- Best for Factual QA / Reasoning: gemma4:e4b (Highest accuracy and semantic similarity)
- Best for Speed: llama3.2:1b (Lowest latency)