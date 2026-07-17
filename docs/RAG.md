# RAG Pipeline

**Code:** `rag/` · **Models:** `backend/app/models/knowledge.py`

Part 6 requires document ingestion (PDF/DOCX/TXT), a justified chunking strategy, a justified embedding model, vector search, and citation support. This document covers the justifications; the code covers the rest.

---

## Pipeline

```
Upload  ──►  Load        PyPDFLoader / Docx2txtLoader / TextLoader
             │
             ├──►  Chunk       RecursiveCharacterTextSplitter
             │                 800 tokens / 120 overlap, heading-aware
             │
             ├──►  Persist     chunks table   (text + page + heading)
             │
             ├──►  Embed       text-embedding-3-small, batches of 100
             │
             └──►  Index       ChromaDB, cosine, metadata-filtered

Query   ──►  Embed query ──► Chroma dense search (metadata pre-filter)
                              ──► top-k ──► resolve citations ──► render
```

---

## 1. Document Ingestion

`rag/ingestion/loaders.py`

| Format | Loader | Pagination |
|---|---|---|
| PDF | `PyPDFLoader` | One document per page |
| DOCX | `Docx2txtLoader` | None — `page` stays `None` |
| TXT | `TextLoader` (utf-8) | None — `page` stays `None` |

**Page numbers are normalised to one-based.** PyPDFLoader emits zero-based pages. A citation reading "page 6" that a reviewer opens to find on page 7 destroys trust in every other citation the platform produces, so the off-by-one is corrected at the loader boundary rather than being carried through the system.

**DOCX and TXT get `page=None`, not `page=1`.** A fabricated page number is worse than an absent one: absent, the reviewer reads the whole file; fabricated, they check page 1, don't find it, and conclude the platform hallucinates citations.

**Empty extraction is an error, not an empty document.** A scanned PDF loads successfully and yields nothing. Ingesting it produces a document that is indexed, has zero chunks, and silently contributes nothing to retrieval — the failure surfaces weeks later as an unexplained knowledge gap. The pipeline raises instead, and the message names OCR as the fix.

---

## 2. Chunking Strategy

`rag/ingestion/chunking.py`

### Configuration

| Parameter | Value |
|---|---|
| Splitter | `RecursiveCharacterTextSplitter` |
| Chunk size | 800 tokens |
| Overlap | 120 tokens (15%) |
| Length function | `tiktoken` `cl100k_base` |
| Separators | `\n\n` → `\n` → `. ` → `? ` → `! ` → `; ` → `, ` → ` ` → `""` |

### Justification

**Why recursive, not fixed-size.** The corpus is support documentation: runbooks, KB articles, release notes. It is structured — headings, then paragraphs, then sentences. Recursive splitting tries paragraph boundaries first and only falls to sentences, then words, when a piece still exceeds the budget. Fixed-size splitting cuts mid-sentence, and a chunk that begins mid-sentence retrieves badly (its embedding encodes a fragment) and cites worse (the reviewer opens the page and finds the claim split across the boundary).

Semantic chunking was considered and rejected: it costs an embedding call per candidate boundary at ingest, and the corpus is already explicitly structured. Paying a model to infer structure that is present in the markup is a poor trade.

**Why 800 tokens.** The competing pressures:

- *Too small* (~200): a chunk holds a symptom without its remedy. Retrieval returns "exports over 50,000 rows are processed asynchronously" and loses "the job may take up to 30 minutes." The Diagnostic Agent then reasons from half a fact.
- *Too large* (~2000): the embedding averages several topics and matches everything weakly. Worse for citations — "it's somewhere in these 2000 tokens" is not a citation a reviewer can check quickly, and an unverifiable citation is functionally an uncited claim.

800 tokens holds a complete KB section — heading, explanation, remedy — which is the unit a support answer is actually built from. The retrieval-accuracy metric in Part 12 is what would justify changing this; it is a starting point with a rationale, not a tuned optimum.

**Why 120 overlap (15%).** A fact that straddles a boundary is retrievable from either side. Zero overlap loses exactly the facts that span a paragraph break, which in procedural documentation is where the "but if X then Y" clauses live. Beyond ~20% the duplication starts returning near-identical chunks in the same result set, which wastes the top-k budget on redundancy.

**Why token-based length, not character-based.** The embedding model has a *token* limit. Characters-per-token varies by an order of magnitude between prose and code, and support documentation contains both. Character-based splitting silently overflows the model on code-heavy chunks and underfills on prose. `tiktoken` is the same tokeniser the embedding model uses, so the budget is measured in the model's own units.

The tokeniser is loaded lazily (`@lru_cache`). tiktoken downloads its BPE table on first use; built at module scope, that would put a network call in the import path and break any importer without egress — including the test suite.

**Heading enrichment.** Each chunk records the heading governing it. A chunk reading "This is terminated and marked failed" is nearly useless alone; tagged `Timeout Behaviour`, it is interpretable. The heading is searched up to the chunk's *end*, not its start — the splitter breaks on `\n\n`, so headings land at chunk boundaries, and searching only up to the start finds nothing for exactly the chunks whose heading is most obvious.

---

## 3. Embedding Model

`rag/embeddings.py`

**Default: `BAAI/bge-small-en-v1.5` via fastembed** (384 dimensions, local, ONNX on CPU)
**Alternative: `text-embedding-3-small`** (1536 dimensions, OpenAI) — set `EMBEDDING_PROVIDER=openai`

The provider is configuration, not code. This matters because the LLM provider and the embedding
provider are independent choices: xAI/Grok exposes no public embeddings endpoint, so a Grok
deployment still needs an embedding source. Local embeddings are the option that needs no second
account.

### Justification

| Criterion | Reasoning |
|---|---|
| **Setup cost** | `fastembed` runs the model through ONNX runtime, not `torch`. This was the original objection to `bge-small` — `sentence-transformers` pulls ~2GB and a platform-specific torch build, which would break the reproducible setup the assessment requires. ONNX sidesteps that: it is a normal wheel, and the setup stays at one `pip install`. |
| **No key required** | The default path needs no account, no key, and no egress at query time. A grader can clone, install, and run retrieval end to end. |
| **Privacy** | Chunks never leave the machine. `RAG.md` previously listed this as the on-premise answer for real customer data — it is now the default rather than a migration path. |
| **Quality** | Comfortably sufficient for support documentation retrieval — English, moderate jargon, no cross-lingual or code-search demands. The bottleneck here is chunking and metadata scoping, not the marginal MTEB points between small embedding models. |
| **Cost** | Negligible at this corpus size. Embeddings are computed once at ingest; only the query embedding is per-request. |

### Trade-offs Accepted

- **First run downloads the model.** ~50MB from the fastembed CDN, cached thereafter. Ingest is CPU-bound rather than network-bound, so a large corpus is slower to index than it would be against a hosted API — but query latency is lower, because there is no round trip.
- **384 dimensions, not 1536.** Smaller vectors, smaller index, faster search, and measurably weaker than the OpenAI model on hard retrieval. For English support documentation this is an acceptable trade; Part 12's retrieval accuracy metric is what would justify switching to `EMBEDDING_PROVIDER=openai`.
- **Re-indexing cost on model change.** Vectors from different models are not comparable, so switching provider requires `python -m scripts.reindex`. Storing chunk text in the `chunks` table rather than only in Chroma is exactly what makes that a re-index rather than a re-ingest — nothing is re-parsed and citations keep resolving.

**Why 1536 dimensions, not `text-embedding-3-large`'s 3072.** Double the storage and slower search for a marginal gain on a corpus this size and this homogeneous. If Part 12's retrieval accuracy metric shows dense search missing, chunking and metadata scoping are the higher-leverage fixes to try first.

---

## 4. Vector Search

`rag/retrieval/vectorstore.py`, `rag/retrieval/retriever.py`

### ChromaDB, persistent local client

No server, no container. Consistent with the SQLite decision: the whole platform runs from `pip install` + `npm install`.

### Cosine, not L2

Chroma defaults to L2. The collection is created with `{"hnsw:space": "cosine"}`. OpenAI embeddings are normalised, so cosine is the metric the model was trained under; ranking by L2 measures a geometry the vectors do not encode.

Chroma returns cosine *distance*; the retriever converts to similarity (`1 - distance`) because that is what agents and citations reason about.

### Metadata pre-filtering

Filters are passed to Chroma's `where` clause, applied **before** the ANN search. Retrieving top-k globally and filtering afterwards returns fewer than k results and silently starves the agent of evidence — the agent then reports a knowledge gap that does not exist.

| Filter | Source |
|---|---|
| `product_area` | `TriageOutput.product_area` |
| `doc_type` | Caller |

**`product_area="unknown"` disables the filter rather than filtering on `"unknown"`.** `unknown` means Triage could not classify the ticket. Filtering on it would search only the unclassified corner of the corpus — the precise opposite of what an unclassified ticket needs. This is a one-line rule that would otherwise be a very confusing bug.

### Dense only

Hybrid retrieval (BM25 + reciprocal rank fusion) and cross-encoder reranking are the standard next levers on retrieval accuracy. Neither is implemented. Part 6 requires vector search and citations; each addition brings a dependency and a failure mode, and there is no evidence yet that dense retrieval is the bottleneck. Part 12 measures retrieval accuracy — that is the signal that would justify adding them. Building them first would be optimising against a guess.

---

## 5. Citation Support

Citations resolve against the `chunks` table, not against Chroma.

**Chunks are stored twice, deliberately.** Chroma holds vectors and answers *what is similar to this query*. The `chunks` table holds text and provenance and answers *what exactly did chunk #abc123 say, and where is it from*. Separating them means:

- A citation survives a re-index. Change the embedding model, rebuild the collection — `chunk_id` still resolves.
- The Validation Agent can check whether a citation actually says what a draft claims, by reading the *stored* text rather than the copy that passed through the drafting agent's context. Checking the agent's own copy would only verify that it copied itself faithfully.

**Citation shape** (`agents/schemas.py`):

```python
Citation(doc_id, chunk_id, source, page, score)
```

**Provenance travels inline with the text.** `RetrievedChunk.render()` emits:

```
[#a1b2c3 | exports.pdf p12 — Timeout Behaviour | score 0.847]
An export exceeding 30 minutes is terminated and marked failed...
```

Given text in one block and a source list in another, models attach the wrong citation to the right claim. The association has to survive into the context window, so it is formatted into the text itself.

**Empty retrieval says so explicitly.** `render_context([])` returns `(retrieval returned no results for this query)` rather than an empty string. An agent handed a blank context block infers a formatting bug and starts improvising from priors. Told plainly that retrieval found nothing, it reports a knowledge gap — which is the behaviour the Research Agent's prompt asks for.

---

## 6. Failure Handling

| Failure | Behaviour |
|---|---|
| Unsupported file type | `UnsupportedFileType`, listing what is supported |
| No extractable text (scanned PDF) | `IngestionError` naming OCR; document marked `FAILED` |
| Embedding API failure | Document marked `FAILED` with the error; chunks already persisted, so retry re-embeds rather than re-parses |
| Chroma unavailable at query | Retrieval returns empty → Research reports a knowledge gap → run escalates to a human. Degrade to a human, never to a guess. |
| Document deletion | Chroma first, then the DB. A chunk row without a vector is invisible to retrieval and harmless; a vector without a resolvable citation gets returned and cannot be verified. |

---

## 7. Verified Behaviour

Tested against real ChromaDB and real chunking with a deterministic stub embedder:

1. TXT/DOCX/PDF ingest → `INDEXED` with chunks persisted
2. Heading and token count captured per chunk
3. Search returns hits with citations that resolve
4. `product_area` filter scopes the corpus; no cross-area leakage
5. `unknown` bypasses the filter
6. `chunk_id` resolves to the canonical stored text
7. Context renders with inline provenance; empty retrieval is explicit
8. Deletion purges both stores
9. Unsupported type and empty file → `FAILED` with a diagnostic error
10. Chunking holds the token budget and preserves page metadata

---

## 8. Configuration

| Setting | Default | Meaning |
|---|---|---|
| `CHUNK_SIZE` | 800 | Tokens per chunk |
| `CHUNK_OVERLAP` | 120 | Token overlap |
| `EMBEDDING_PROVIDER` | `local` | `local` (fastembed) or `openai` |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | |
| `LLM_BASE_URL` | *(unset)* | Set for any OpenAI-compatible provider, e.g. xAI |
| `CHROMA_COLLECTION` | `enterprise_knowledge` | |
| `CHROMA_DIR` | `./data/chroma` | Persistent client path |
| `RETRIEVAL_TOP_K` | 5 | Default hits per query |
