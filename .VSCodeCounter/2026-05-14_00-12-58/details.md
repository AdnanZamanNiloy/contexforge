# Details

Date : 2026-05-14 00:12:58

Directory /home/adnan-zaman/Desktop/contextforge/backend

Total : 69 files,  2783 codes, 222 comments, 889 blanks, all 3894 lines

[Summary](results.md) / Details / [Diff Summary](diff.md) / [Diff Details](diff-details.md)

## Files
| filename | language | code | comment | blank | total |
| :--- | :--- | ---: | ---: | ---: | ---: |
| [backend/README.md](/backend/README.md) | Markdown | 2 | 0 | 2 | 4 |
| [backend/\_\_init\_\_.py](/backend/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/app/\_\_init\_\_.py](/backend/app/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/app/config/\_\_init\_\_.py](/backend/app/config/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/app/config/settings.py](/backend/app/config/settings.py) | Python | 55 | 0 | 15 | 70 |
| [backend/app/dependencies.py](/backend/app/dependencies.py) | Python | 84 | 1 | 29 | 114 |
| [backend/app/main.py](/backend/app/main.py) | Python | 20 | 0 | 9 | 29 |
| [backend/app/routes/\_\_init\_\_.py](/backend/app/routes/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/app/routes/github.py](/backend/app/routes/github.py) | Python | 10 | 0 | 6 | 16 |
| [backend/app/routes/ingest.py](/backend/app/routes/ingest.py) | Python | 23 | 0 | 8 | 31 |
| [backend/app/routes/query.py](/backend/app/routes/query.py) | Python | 19 | 0 | 8 | 27 |
| [backend/app/schemas/\_\_init\_\_.py](/backend/app/schemas/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/app/schemas/ingest.py](/backend/app/schemas/ingest.py) | Python | 9 | 2 | 8 | 19 |
| [backend/app/schemas/query.py](/backend/app/schemas/query.py) | Python | 9 | 2 | 8 | 19 |
| [backend/app/services/\_\_init\_\_.py](/backend/app/services/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/app/services/ingest\_service.py](/backend/app/services/ingest_service.py) | Python | 24 | 1 | 8 | 33 |
| [backend/app/services/query\_service.py](/backend/app/services/query_service.py) | Python | 40 | 1 | 9 | 50 |
| [backend/core/\_\_init\_\_.py](/backend/core/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/core/chunking/\_\_init\_\_.py](/backend/core/chunking/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/core/chunking/code\_chunker.py](/backend/core/chunking/code_chunker.py) | Python | 39 | 0 | 9 | 48 |
| [backend/core/chunking/text\_chunker.py](/backend/core/chunking/text_chunker.py) | Python | 94 | 3 | 28 | 125 |
| [backend/core/embedding/\_\_init\_\_.py](/backend/core/embedding/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/core/embedding/bge\_embedder.py](/backend/core/embedding/bge_embedder.py) | Python | 27 | 1 | 11 | 39 |
| [backend/core/embedding/voyage\_embedder.py](/backend/core/embedding/voyage_embedder.py) | Python | 164 | 3 | 53 | 220 |
| [backend/core/generation/\_\_init\_\_.py](/backend/core/generation/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/core/generation/base\_llm.py](/backend/core/generation/base_llm.py) | Python | 58 | 60 | 15 | 133 |
| [backend/core/generation/fallback\_llm.py](/backend/core/generation/fallback_llm.py) | Python | 65 | 0 | 21 | 86 |
| [backend/core/generation/gemini\_llm.py](/backend/core/generation/gemini_llm.py) | Python | 166 | 2 | 42 | 210 |
| [backend/core/generation/groq\_llm.py](/backend/core/generation/groq_llm.py) | Python | 175 | 1 | 50 | 226 |
| [backend/core/generation/prompt\_builder.py](/backend/core/generation/prompt_builder.py) | Python | 79 | 0 | 25 | 104 |
| [backend/core/ingestion/\_\_init\_\_.py](/backend/core/ingestion/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/core/ingestion/base\_loader.py](/backend/core/ingestion/base_loader.py) | Python | 8 | 1 | 6 | 15 |
| [backend/core/ingestion/docx\_loader.py](/backend/core/ingestion/docx_loader.py) | Python | 32 | 0 | 9 | 41 |
| [backend/core/ingestion/github\_loader.py](/backend/core/ingestion/github_loader.py) | Python | 100 | 0 | 16 | 116 |
| [backend/core/ingestion/pdf\_loader.py](/backend/core/ingestion/pdf_loader.py) | Python | 49 | 0 | 14 | 63 |
| [backend/core/ingestion/text\_loader.py](/backend/core/ingestion/text_loader.py) | Python | 13 | 0 | 5 | 18 |
| [backend/core/ingestion/web\_loader.py](/backend/core/ingestion/web_loader.py) | Python | 132 | 19 | 46 | 197 |
| [backend/core/interfaces/\_\_init\_\_.py](/backend/core/interfaces/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/core/interfaces/embedder.py](/backend/core/interfaces/embedder.py) | Python | 20 | 0 | 10 | 30 |
| [backend/core/interfaces/llm.py](/backend/core/interfaces/llm.py) | Python | 10 | 1 | 6 | 17 |
| [backend/core/interfaces/retriever.py](/backend/core/interfaces/retriever.py) | Python | 13 | 0 | 9 | 22 |
| [backend/core/orchestrator.py](/backend/core/orchestrator.py) | Python | 163 | 91 | 26 | 280 |
| [backend/core/pipeline.py](/backend/core/pipeline.py) | Python | 10 | 13 | 4 | 27 |
| [backend/core/processing/\_\_init\_\_.py](/backend/core/processing/__init__.py) | Python | 4 | 0 | 2 | 6 |
| [backend/core/processing/cleaner.py](/backend/core/processing/cleaner.py) | Python | 120 | 0 | 31 | 151 |
| [backend/core/processing/deduplicator.py](/backend/core/processing/deduplicator.py) | Python | 60 | 0 | 24 | 84 |
| [backend/core/processing/metadata\_extractor.py](/backend/core/processing/metadata_extractor.py) | Python | 117 | 1 | 28 | 146 |
| [backend/core/retrieval/\_\_init\_\_.py](/backend/core/retrieval/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/core/retrieval/bm25\_retriever.py](/backend/core/retrieval/bm25_retriever.py) | Python | 22 | 0 | 9 | 31 |
| [backend/core/retrieval/dense\_retriever.py](/backend/core/retrieval/dense_retriever.py) | Python | 22 | 0 | 9 | 31 |
| [backend/core/retrieval/hybrid\_retriever.py](/backend/core/retrieval/hybrid_retriever.py) | Python | 62 | 1 | 18 | 81 |
| [backend/core/retrieval/hyde.py](/backend/core/retrieval/hyde.py) | Python | 39 | 0 | 14 | 53 |
| [backend/core/retrieval/reranker.py](/backend/core/retrieval/reranker.py) | Python | 64 | 0 | 20 | 84 |
| [backend/core/retrieval/rrf\_fusion.py](/backend/core/retrieval/rrf_fusion.py) | Python | 41 | 0 | 15 | 56 |
| [backend/core/storage/\_\_init\_\_.py](/backend/core/storage/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/core/storage/bm25\_index.py](/backend/core/storage/bm25_index.py) | Python | 123 | 17 | 39 | 179 |
| [backend/core/storage/faiss\_store.py](/backend/core/storage/faiss_store.py) | Python | 139 | 1 | 42 | 182 |
| [backend/core/types.py](/backend/core/types.py) | Python | 78 | 0 | 29 | 107 |
| [backend/observability/\_\_init\_\_.py](/backend/observability/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/observability/tracer.py](/backend/observability/tracer.py) | Python | 18 | 0 | 12 | 30 |
| [backend/tests/\_\_init\_\_.py](/backend/tests/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/tests/integration/\_\_init\_\_.py](/backend/tests/integration/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/tests/integration/test\_api.py](/backend/tests/integration/test_api.py) | Python | 46 | 0 | 24 | 70 |
| [backend/tests/unit/\_\_init\_\_.py](/backend/tests/unit/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [backend/tests/unit/test\_chunkers.py](/backend/tests/unit/test_chunkers.py) | Python | 29 | 0 | 6 | 35 |
| [backend/tests/unit/test\_embedding\_cache.py](/backend/tests/unit/test_embedding_cache.py) | Python | 17 | 0 | 9 | 26 |
| [backend/tests/unit/test\_hyde.py](/backend/tests/unit/test_hyde.py) | Python | 12 | 0 | 7 | 19 |
| [backend/tests/unit/test\_reranker.py](/backend/tests/unit/test_reranker.py) | Python | 19 | 0 | 9 | 28 |
| [backend/tests/unit/test\_storage\_and\_retrieval.py](/backend/tests/unit/test_storage_and_retrieval.py) | Python | 39 | 0 | 9 | 48 |

[Summary](results.md) / Details / [Diff Summary](diff.md) / [Diff Details](diff-details.md)