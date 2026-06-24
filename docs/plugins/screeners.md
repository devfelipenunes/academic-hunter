# Screeners Plugins (Relevance Scoring)

The Screening layer is responsible for determining if a downloaded paper is "relevant" or "noise" based on the user's `config.json`.

By abstracting this into `plugins/screeners/`, Academic Hunter allows researchers to hot-swap between different scoring algorithms without touching the core engine.

## Base Architecture
All Screeners must inherit from `BaseScreener` (`src/academic_hunter/plugins/screeners/base_screener.py`) and implement the `evaluate()` method.

```python
def evaluate(self, paper_data: Dict[str, Any], config: Dict[str, Any]) -> float:
    # Returns a score. 0.0 means irrelevant.
```

## Available Screeners

### 1. `KeywordScreener` (Default)
The classic, blazing-fast heuristic engine. It uses Regex to search for `anchors` and `technical_strings` within the title and abstract, applying multipliers for matches found in the title.
- **Use Case:** Broad, traditional boolean searches.
- **Speed:** Instant.

### 2. `SemanticScreener` (Advanced NLP)
Uses local Small Language Models (SLMs) via HuggingFace `sentence-transformers` (e.g., `all-MiniLM-L6-v2` running via ONNX on CPU) to measure the semantic distance between the paper and the user's research topic.
- **Use Case:** Eliminating false positives where the keywords match but the context is completely wrong.
- **Speed:** Slower, requires downloading model weights on first run.

## How to Create Your Own
1. Create a new file in `plugins/screeners/`.
2. Inherit from `BaseScreener`.
3. Add your custom logic in `evaluate()`.
4. Register your plugin in the pipeline configuration.
