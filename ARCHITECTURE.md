# Architecture

This document describes how the FortiGate Firewall AI Agent is structured, how
the files relate to each other, and how a question flows through the system.

## Overview

The application is a **local, privacy-preserving AI assistant** for a FortiGate
firewall. It combines three things:

1. **A local LLM** (via Ollama) that reasons about firewall questions.
2. **Live firewall data** pulled from the FortiOS REST API on demand.
3. **Built-in documentation** injected as context so answers are grounded and
   end with a documentation-based recommendation.

Nothing leaves your machine except the LAN calls to the FortiGate and to the
Ollama server — there are no cloud API keys.

## Components / files

| File | Layer | Responsibility |
|------|-------|----------------|
| `langchain_firewall_agent.py` | Orchestration | Entry point. Builds the prompt, runs the tool-calling loop, talks to Ollama, renders the colored header, appends the `[PDF]` indicator. |
| `fortigate_api_wrapper.py` | Adapter | Maps tool names → `FortiGateClient` methods, shapes/normalizes results into JSON strings, surfaces API errors. |
| `fortigate.py` | Transport | Thin `httpx` REST client. One method per FortiOS endpoint (`/cmdb`, `/monitor`, `/log`). |
| `pdf_loader.py` | Knowledge | Loads documentation (external PDF or built-in text) and exposes search/section helpers. |
| `.env` | Config | FortiGate host/token/VDOM, `OLLAMA_BASE_URL`, optional `FORTIGATE_LOG_SOURCE`. (git-ignored) |
| *Ollama* | External | Local LLM server (`OLLAMA_BASE_URL`). |
| *FortiGate* | External | The firewall, reached over HTTPS via API token. |

## File correlation graphic

```
                    ┌───────────────────────────────────────────────┐
                    │                  USER (terminal)               │
                    └───────────────────────┬───────────────────────┘
                                             │ question / answer
                                             ▼
        ┌─────────────────────────────────────────────────────────────────┐
        │                  langchain_firewall_agent.py                      │
        │                  (orchestrator — FirewallAgent)                   │
        │                                                                   │
        │   • TOOLS registry        • query() tool-calling loop             │
        │   • colored header        • [PDF] usage indicator                 │
        └───────┬───────────────────────┬──────────────────────────┬───────┘
                │ reads config           │ tool calls               │ prompt + invoke
                ▼                        ▼                          ▼
        ┌──────────────┐      ┌────────────────────────┐    ┌──────────────┐
        │   .env       │      │ fortigate_api_wrapper.py│    │   Ollama     │
        │ (config)     │      │ (FortiGateAPIWrapper)   │    │ (local LLM)  │
        └──────────────┘      └───────────┬────────────┘    └──────────────┘
                                          │ method per endpoint
                                          ▼
                              ┌────────────────────────┐
                              │      fortigate.py       │
                              │   (FortiGateClient)     │
                              └───────────┬────────────┘
                                          │ HTTPS /api/v2 + token
                                          ▼
                              ┌────────────────────────┐
                              │   FortiGate firewall    │
                              └────────────────────────┘

        ┌────────────────────────┐
        │      pdf_loader.py      │  ──── documentation context ───►  injected into
        │ (PDFDocumentationLoader)│                                   the system prompt
        └────────────────────────┘                                   (orchestrator)
```

**How to read it:** the orchestrator is the only component that talks to the
user and to Ollama. It reaches the firewall *indirectly* through the wrapper →
client chain. `pdf_loader.py` feeds static documentation into the prompt at
startup; it does not touch the firewall.

## Traffic / data flow

A single question travels through the system like this:

```
 1. USER types a question
        │
        ▼
 2. agent.query() builds a prompt =
        system prompt (tool list + DOCUMENTATION from pdf_loader)
        + the user question
        │
        ▼
 3. Ollama LLM responds. Two cases:
        (a) it emits  TOOL: tool_name(param=value)
        (b) it answers directly
        │
        ▼  (case a)
 4. agent parses the TOOL: line and calls FortiGateAPIWrapper
        │
        ▼
 5. wrapper maps the tool name to a FortiGateClient method
        │
        ▼
 6. fortigate.py sends HTTPS GET/POST to  https://<host>/api/v2/...
        with the API token from .env
        │
        ▼
 7. FortiGate returns JSON  →  client returns Python objects
        →  wrapper normalizes + formats (or surfaces the error)
        │
        ▼
 8. agent appends the result to the *accumulated* tool data and
        re-prompts Ollama (loop, up to 3 iterations)
        │
        ▼
 9. once the model answers (no more TOOL: calls), agent:
        • appends a documentation-based "Recommendation:" section
        • appends the [PDF] documentation-used indicator
        │
        ▼
10. ANSWER is printed under the pinned colored header
```

### Sequence (with the network hops)

```
USER → agent: "Is the firewall under resource pressure?"
agent → Ollama: prompt (system + docs + question)
Ollama → agent: TOOL: system_health_check()
agent → wrapper: system_health_check()
wrapper → client: get_system_status() + get_resource_usage() + get_interface_stats()
client → FortiGate: HTTPS GET /api/v2/monitor/system/...
FortiGate → client: JSON
client → wrapper → agent: interpreted health summary (OK/WARN/CRITICAL)
agent → Ollama: prompt (system + docs + gathered data)
Ollama → agent: final answer + Recommendation
agent → USER: answer + [PDF] indicator
```

## Key design points

- **Tool protocol is text-based.** The model must literally print
  `TOOL: name(arg=value)`, which a regex in the orchestrator parses. This keeps
  the app model-agnostic but means smaller LLMs follow it less reliably.
- **Context accumulates.** Every tool result from the loop is re-sent on each
  iteration so the model can correlate data across multiple tools.
- **Errors are surfaced, not swallowed.** The wrapper returns the real FortiOS
  error (e.g. HTTP 403/404) or an explicit "succeeded but empty" note, instead
  of failing silently.
- **Logs auto-fall-back.** Log tools try `disk → memory → forticloud` (or a
  fixed `FORTIGATE_LOG_SOURCE`) so they work across FortiGate models/configs.
- **Everything is configurable via `.env`** — FortiGate target, Ollama URL,
  log source — with no code changes.

## Configuration surface (`.env`)

| Variable | Used by | Purpose |
|----------|---------|---------|
| `FORTIGATE_HOST` | `fortigate_api_wrapper.py` → `fortigate.py` | Firewall IP/hostname |
| `FORTIGATE_TOKEN` | same | REST API token |
| `FORTIGATE_VDOM` | same | VDOM (default `root`) |
| `FORTIGATE_VERIFY_SSL` | same | TLS verification |
| `FORTIGATE_LOG_SOURCE` | wrapper | Force log source (else auto-fallback) |
| `OLLAMA_BASE_URL` | `langchain_firewall_agent.py` | Ollama server URL (local or remote) |
```
