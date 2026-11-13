# llm/

**Status: not implemented.** Scheduled for Milestone 6.

Planned contents (see `docs/architecture.md` §7.3):

| Path | Purpose |
|---|---|
| `corpus/approved/` | Approved teaching procedures with version front matter |
| `corpus/untrusted_samples/` | Untrusted evidence documents for testing (including hostile instructions) |
| `prompts/<name>/vN.md` | Versioned prompt templates |
| `coldchain_llm/` | Retrieval, provider adapters (Anthropic, disabled), read-only tools, schemas, output validation |
| `eval/cases/` | At least 40 evaluation cases (10 normal, 10 missing evidence, 10 conflicting evidence, 10 hostile instructions) |
| `tests/` | Unit tests; live-provider tests are opt-in |

Without an API key the module returns an explicit `not_configured` status; it never shows a placeholder draft.

Main requirements: LLM-01 to LLM-12, FR-21, EVAL-07, NFR-11.
