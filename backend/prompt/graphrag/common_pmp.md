You are a **Knowledge Graph Construction Expert**. Please analyze the provided text fragment.

You need to complete two tasks:

1.  **Summarize**: Summarize the core content of this fragment in a single sentence (to facilitate subsequent logical retrieval).
2.  **Extract**: Extract core entities and relationships in the format `[Entity1, Relation, Entity2]`.

Please **strictly output a valid JSON object**. Do not include Markdown code block markers (e.g., ` ```json `). Use the following format:

```json
{
  "summary": "Write summary content here...",
  "triples": [
    ["EntityA", "Relation Verb", "EntityB"],
    ["EntityC", "Relation Verb", "EntityD"]
  ]
}
```