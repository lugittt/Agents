# Ollama Configuration Guide - Local vs Remote

## Current Configuration (Local)

The default configuration uses a **local Ollama server** on your machine.

```
Default: http://localhost:11434
```

---

## Where Ollama Path is Configured

### Location 1: FirewallAgent Class (Line 100)

**File:** `langchain_firewall_agent.py`

```python
def __init__(
    self,
    model: str = "llama2",
    base_url: str = "http://localhost:11434",  # ← HERE
    temperature: float = 0.3,
):
```

### Location 2: create_firewall_agent() Function (Line 285)

**File:** `langchain_firewall_agent.py`

```python
def create_firewall_agent(
    model: str = "llama2",
    base_url: str = "http://localhost:11434",  # ← HERE
    temperature: float = 0.3,
) -> FirewallAgent:
```

### Location 3: OllamaLLM Initialization (Line 118)

**File:** `langchain_firewall_agent.py`

```python
self.llm = OllamaLLM(
    model=model,
    base_url=base_url,  # ← PASSED HERE
    temperature=temperature,
    num_ctx=4096,
)
```

---

## How to Change to Remote Server

### Option 1: Interactive Mode (Easiest)

```bash
# Command line with remote server
python langchain_firewall_agent.py qwen2.5

# Then you'll see:
# [INFO] Connecting to Ollama at http://localhost:11434...

# BUT this still uses default - see Option 2 for truly remote
```

### Option 2: Edit Code (Permanent Change)

**Modify `langchain_firewall_agent.py` - Line 100:**

```python
# BEFORE (Local):
def __init__(
    self,
    model: str = "llama2",
    base_url: str = "http://localhost:11434",
    temperature: float = 0.3,
):

# AFTER (Remote):
def __init__(
    self,
    model: str = "llama2",
    base_url: str = "http://192.168.1.100:11434",  # Your remote Ollama server
    temperature: float = 0.3,
):
```

**Also update Line 285:**

```python
# BEFORE:
def create_firewall_agent(
    model: str = "llama2",
    base_url: str = "http://localhost:11434",
    temperature: float = 0.3,
) -> FirewallAgent:

# AFTER:
def create_firewall_agent(
    model: str = "llama2",
    base_url: str = "http://192.168.1.100:11434",  # Your remote Ollama
    temperature: float = 0.3,
) -> FirewallAgent:
```

### Option 3: Use Environment Variable (Most Flexible)

Create or edit `.env` file:

```bash
# Add this line:
OLLAMA_BASE_URL=http://192.168.1.100:11434
```

Then modify `langchain_firewall_agent.py`:

```python
# Add at top of file (around line 20):
import os
from dotenv import load_dotenv

load_dotenv()

# In __init__ method:
def __init__(
    self,
    model: str = "llama2",
    base_url: str = None,  # Make it optional
    temperature: float = 0.3,
):
    # Use env var if available, otherwise use default
    if base_url is None:
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    
    self.base_url = base_url
    # ... rest of code
```

### Option 4: Use Python API (Dynamic)

```python
from langchain_firewall_agent import create_firewall_agent

# Connect to remote Ollama server
agent = create_firewall_agent(
    model="qwen2.5",
    base_url="http://192.168.1.100:11434",  # Your remote server
)

answer = agent.query("List all firewall policies")
print(answer)
```

### Option 5: Programmatic (Recommended for Integration)

```python
from langchain_firewall_agent import query_firewall

# Using programmatic API with remote server
# First create agent with remote URL
from langchain_firewall_agent import create_firewall_agent

agent = create_firewall_agent(
    model="qwen2.5",
    base_url="http://remote-ollama-server:11434"
)

answer = agent.query("Your question here")
```

---

## Remote Ollama Server Setup

### On Remote Machine (where Ollama runs)

```bash
# Install Ollama (if not already installed)
# See: https://ollama.ai

# Start Ollama server listening on all interfaces:
ollama serve --host 0.0.0.0:11434

# Or modify config to listen on specific IP:
# Edit ~/.ollama/llama.cpp (or server config)
# Make sure it listens on 0.0.0.0 or your specific IP
```

### Test Remote Connection

```bash
# From your local machine, test if remote Ollama is accessible:
curl http://192.168.1.100:11434/api/tags

# Should return JSON with available models:
# {"models": [{"name": "qwen2.5:latest"}, ...]}
```

---

## Example Configurations

### Local Machine (Current Default)
```
http://localhost:11434
or
http://127.0.0.1:11434
```

### Remote on LAN
```
http://192.168.1.100:11434
http://10.0.0.50:11434
http://ollama-server.local:11434
```

### Remote on Different Network
```
http://203.0.113.42:11434  # Public IP
https://ollama.example.com:11434  # With DNS
```

### Docker Container (Remote)
```
http://ollama-container:11434
http://host.docker.internal:11434  # From inside container
```

---

## Full Example: Using Remote Ollama

### Edit langchain_firewall_agent.py

```python
# Line 100 - In FirewallAgent.__init__:
def __init__(
    self,
    model: str = "qwen2.5",
    base_url: str = "http://192.168.1.100:11434",  # Your remote server
    temperature: float = 0.3,
):

# Line 285 - In create_firewall_agent:
def create_firewall_agent(
    model: str = "qwen2.5",
    base_url: str = "http://192.168.1.100:11434",  # Your remote server
    temperature: float = 0.3,
) -> FirewallAgent:
```

### Run Application

```bash
# Will now connect to remote Ollama server
python langchain_firewall_agent.py qwen2.5

# Output:
# [INFO] Connecting to Ollama at http://192.168.1.100:11434...
# [INFO] Using model: qwen2.5
# [OK] Ollama connection verified
```

---

## Key Points

| Aspect | Local | Remote |
|--------|-------|--------|
| **URL** | http://localhost:11434 | http://server-ip:11434 |
| **Setup** | ✓ Easy (same machine) | Requires network setup |
| **Speed** | Fastest | Depends on network |
| **Usage** | Development/Testing | Production/Shared |
| **Configuration** | Line 100, 285 | Same lines, different URL |

---

## Troubleshooting Remote Connection

### "Cannot connect to Ollama"

```
Error: Failed to connect to http://192.168.1.100:11434
```

**Solutions:**
1. Verify remote server IP is correct
2. Check Ollama is running: `ollama serve`
3. Check firewall allows port 11434
4. Test with curl: `curl http://192.168.1.100:11434/api/tags`

### "Connection timeout"

**Solutions:**
1. Ollama might not be running on remote machine
2. Network connectivity issue
3. Wrong IP address
4. Firewall blocking port 11434

### "Model not found"

```
Error: model 'qwen2.5' not found on remote server
```

**Solutions:**
1. Pull model on remote: `ollama pull qwen2.5`
2. Check available models: `curl http://remote-ip:11434/api/tags`
3. Use model that exists on remote server

---

## Summary

| Method | Difficulty | Flexibility | Best For |
|--------|-----------|-------------|----------|
| **Edit Code (Line 100, 285)** | Easy | Low | One-time setup |
| **Environment Variable** | Easy | High | Multiple deployments |
| **Python API** | Medium | Very High | Integration/scripting |
| **Command Line Parameter** | Hard | Very High | Advanced usage |

**Recommended:** Use **Environment Variable** (.env) or **Python API** for flexibility.

---

## Quick Reference

### Change from local to remote (3 steps):

1. **Edit** `langchain_firewall_agent.py` lines 100 and 285
2. **Replace** `"http://localhost:11434"` with `"http://your-server-ip:11434"`
3. **Run** application as normal

That's it! ✅
