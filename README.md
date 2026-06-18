# FortiGate LangChain Agent - Application

Minimal production-ready application to query your FortiGate firewall using local Ollama models.

## Quick Start (5 Minutes)

### 1. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure FortiGate Access
```bash
# Copy template to actual config file
cp .env.template .env

# Edit .env with your FortiGate details
# Open .env and set:
#   - FORTIGATE_HOST: Your FortiGate IP (e.g., 192.168.1.1)
#   - FORTIGATE_TOKEN: Your API token from FortiGate
#   - FORTIGATE_VDOM: VDOM name (usually "root")
```

### 3. Ensure Ollama is Running
```bash
# In a separate terminal:
ollama serve
```

### 4. Start the Agent
```bash
python langchain_firewall_agent.py qwen2.5
```

### 5. Ask Your First Question
```
[INPUT] Ask about your firewall: List all firewall policies
```

Done! 🎉

---

## Usage

### Interactive Mode (Best for Exploration)
```bash
python langchain_firewall_agent.py qwen2.5
```

Then type questions interactively:
```
List all firewall policies
Show me policy number 1
Why is traffic being denied?
Check system health
```

### Python Code (Best for Integration)
```python
from langchain_firewall_agent import query_firewall

# Simple query
answer = query_firewall(
    "List all firewall policies",
    model="qwen2.5"
)
print(answer)
```

### Batch Processing
```python
from langchain_firewall_agent import query_firewall

questions = [
    "List all policies",
    "Show addresses",
    "Check system health"
]

for q in questions:
    answer = query_firewall(q, model="qwen2.5")
    print(f"Q: {q}")
    print(f"A: {answer}\n")
```

---

## Available Ollama Models

| Model | Speed | Quality | Best For |
|-------|-------|---------|----------|
| granite4.1 | ⚡⚡⚡ | Good | Quick simple queries |
| qwen2.5 | ⚡⚡ | Very Good | **Recommended** |
| llama3.2 | ⚡ | Excellent | Complex analysis |
| mistral | ⚡⚡ | Very Good | Fast & reliable |
| James | 🐢 | Best | Deep analysis |

**Recommended for most use:** `qwen2.5` (good balance of speed and quality)

---

## Example Questions

```
"List all firewall policies"
"Show me address objects"
"What services are configured?"
"Get policy number 1 details"
"Check firewall system health"
"Show policy statistics"
"Which policies are most active?"
"List network interfaces"
"What configuration changes were made recently?"
"Is the firewall under resource pressure?"
```

---

## Available Tools

The agent can call these tools automatically to answer your questions.

### Policy & Configuration
| Tool | Description |
|------|-------------|
| `list_firewall_policies` | List all firewall policies (summary) |
| `get_firewall_policy` | Full detail of one policy by ID |
| `get_address_objects` | Address objects and address groups |
| `get_service_objects` | Service objects and service groups |
| `get_network_interfaces` | Network interfaces |
| `list_vips` | Virtual IPs (port forwarding / NAT mappings) |
| `list_static_routes` | Configured static routes |

### Monitoring & Health
| Tool | Description |
|------|-------------|
| `get_firewall_health` | Raw system status (CPU, memory, disk, uptime, firmware, serial) |
| `system_health_check` | **Interpreted** health summary with OK/WARN/CRITICAL flags + interface up/down counts |
| `get_policy_statistics` | Per-policy hit counters (packets/bytes) |
| `get_interface_stats` | Per-interface packets/bytes/errors/link state |
| `get_vpn_status` | IPsec VPN tunnel status |

### Logs & Recent Changes
| Tool | Description |
|------|-------------|
| `get_traffic_logs` | Traffic logs (filters: srcip, dstip, action, policyid) |
| `get_admin_logs` | **Recent admin logins and configuration changes** — what was last changed and by whom |
| `get_system_logs` | System event logs (optional severity filter) |

### Documentation
| Tool | Description |
|------|-------------|
| `search_documentation` | Search built-in FortiGate documentation for a keyword |
| `get_documentation_section` | Retrieve a specific documentation section |

> **Note:** The log tools (`get_admin_logs`, `get_system_logs`, `get_traffic_logs`) require the API token to have **Log & Report → Log Access** read permission on the FortiGate. The other tools only need standard read access.

---

## Files in This Folder

| File | Purpose |
|------|---------|
| **langchain_firewall_agent.py** | Main agent - entry point |
| **fortigate_api_wrapper.py** | FortiGate API wrapper |
| **pdf_loader.py** | Built-in documentation |
| **fortigate.py** | Low-level REST API client |
| **requirements.txt** | Python dependencies |
| **.env.template** | Config template (copy to .env) |
| **README.md** | This file |

---

## Configuration (.env File)

**Location:** Create `.env` in this folder (copy from `.env.template`)

**Required Settings:**
```bash
FORTIGATE_HOST=192.168.1.1           # Your FortiGate IP
FORTIGATE_TOKEN=your-api-token       # API token from FortiGate
FORTIGATE_VDOM=root                  # VDOM name (default)
FORTIGATE_VERIFY_SSL=false           # SSL verification (self-signed cert)
```

**How to get API token:**
1. Log into FortiGate
2. Go to System → Administrators
3. Create new REST API Admin
4. Copy the generated token

---

## Troubleshooting

### "Cannot connect to Ollama at localhost:11434"
```bash
# Make sure Ollama is running in another terminal:
ollama serve
```

### "FortiGate connection failed"
- Verify FORTIGATE_HOST is correct
- Check API token hasn't expired
- Ensure API admin has permission to access firewall policy

### "Model 'qwen2.5' not found"
```bash
# Pull the model:
ollama pull qwen2.5

# Or use a model you have:
python langchain_firewall_agent.py llama3.2
ollama list  # See installed models
```

### "Very slow responses"
- Use faster model: `granite4.1` (3B model)
- Close other applications
- Check CPU/memory usage

### "Response is incomplete or cut off"
- This is normal with larger models
- Try simpler questions
- Or use a smaller/faster model

---

## Advanced Usage

### Using Different Model
```bash
python langchain_firewall_agent.py llama3.2
python langchain_firewall_agent.py mistral
python langchain_firewall_agent.py granite4.1
```

### Custom Temperature (affects creativity)
Edit `langchain_firewall_agent.py` and modify:
```python
agent = create_firewall_agent(
    model="qwen2.5",
    temperature=0.3  # Lower = more consistent, Higher = more creative
)
```

### Using Remote Ollama
If Ollama runs on a different machine:
```python
from langchain_firewall_agent import create_firewall_agent

agent = create_firewall_agent(
    model="qwen2.5",
    base_url="http://192.168.1.100:11434"  # Remote machine
)
```

---

## System Requirements

- **Python:** 3.8+
- **Ollama:** Running locally (or remote)
- **RAM:** 4GB minimum (depends on model size)
- **FortiGate:** Accessible on network with API enabled
- **Internet:** Not required (runs locally)

---

## How It Works

```
1. You ask a question
2. Agent loads built-in FortiGate documentation
3. Agent sends request to local Ollama model
4. Ollama decides which tools to call
5. Tools query your FortiGate firewall
6. Ollama analyzes results with documentation context
7. Answer returned to you with recommendations
```

Everything stays local, no API costs, complete privacy! 🔒

---

## Documentation

For detailed information, refer to the original `mcp_server` folder:
- `FILE_GUIDE.md` - Detailed file descriptions
- `ARCHITECTURE.md` - System architecture
- `OLLAMA_SETUP.md` - Complete Ollama setup
- `LANGCHAIN_AGENT_README.md` - Technical details

---

## Quick Commands Reference

```bash
# Install dependencies
pip install -r requirements.txt

# Start Ollama (in separate terminal)
ollama serve

# Run agent with default model (qwen2.5)
python langchain_firewall_agent.py

# Run with specific model
python langchain_firewall_agent.py granite4.1

# See installed models
ollama list

# Pull new model
ollama pull mistral
```

---

## First Run Checklist

- [ ] Copied `.env.template` to `.env`
- [ ] Filled in `.env` with FortiGate details
- [ ] Ran `pip install -r requirements.txt`
- [ ] Verified Ollama is running (`ollama serve`)
- [ ] Started agent: `python langchain_firewall_agent.py qwen2.5`
- [ ] Asked a test question

---

## Next Steps

1. **Try simple questions first** to verify everything works
2. **Explore your firewall configuration** through the agent
3. **Ask complex questions** combining multiple data sources
4. **Integrate into your workflow** using Python API

---

**Ready to start?** Run `python langchain_firewall_agent.py qwen2.5` 🚀
