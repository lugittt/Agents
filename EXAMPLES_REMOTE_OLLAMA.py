"""
Examples of using the FortiGate agent with remote Ollama servers.
Shows different ways to connect to Ollama on different machines.
"""

from langchain_firewall_agent import create_firewall_agent, query_firewall

# ==============================================================================
# Example 1: Local Ollama (Default - Current Setup)
# ==============================================================================

print("=" * 70)
print("Example 1: Local Ollama Server (Current Default)")
print("=" * 70)

# Creates agent connecting to localhost:11434
agent_local = create_firewall_agent(
    model="qwen2.5",
    base_url="http://localhost:11434"  # Local machine
)
answer = agent_local.query("List all firewall policies")
print(answer)
print()

# ==============================================================================
# Example 2: Remote Ollama on LAN
# ==============================================================================

print("=" * 70)
print("Example 2: Remote Ollama on Local Network (LAN)")
print("=" * 70)

# If you have Ollama running on another machine on your network
# Assuming Ollama is on 192.168.1.100
agent_remote_lan = create_firewall_agent(
    model="qwen2.5",
    base_url="http://192.168.1.100:11434"  # Different machine on LAN
)
answer = agent_remote_lan.query("Check firewall system health")
print(answer)
print()

# ==============================================================================
# Example 3: Remote Ollama with Hostname
# ==============================================================================

print("=" * 70)
print("Example 3: Remote Ollama using Hostname (mDNS)")
print("=" * 70)

# If your Ollama server has a hostname (e.g., ollama-server.local)
agent_remote_hostname = create_firewall_agent(
    model="qwen2.5",
    base_url="http://ollama-server.local:11434"  # Using hostname
)
answer = agent_remote_hostname.query("List all address objects")
print(answer)
print()

# ==============================================================================
# Example 4: Ollama in Docker Container
# ==============================================================================

print("=" * 70)
print("Example 4: Ollama in Docker Container (from host)")
print("=" * 70)

# If Ollama is running in Docker on same machine
agent_docker = create_firewall_agent(
    model="qwen2.5",
    base_url="http://localhost:11434"  # Docker port-mapped to localhost
)
answer = agent_docker.query("Show network interfaces")
print(answer)
print()

# Or if Docker container on different machine:
# base_url="http://192.168.1.200:11434"

# ==============================================================================
# Example 5: Ollama on Public Server (with HTTPS)
# ==============================================================================

print("=" * 70)
print("Example 5: Ollama on Remote Public Server")
print("=" * 70)

# If you have Ollama accessible over internet (with HTTPS)
agent_public = create_firewall_agent(
    model="qwen2.5",
    base_url="https://ollama.example.com:11434"  # Public domain with HTTPS
)
answer = agent_public.query("List service objects")
print(answer)
print()

# ==============================================================================
# Example 6: Different Models on Same Server
# ==============================================================================

print("=" * 70)
print("Example 6: Different Models on Remote Server")
print("=" * 70)

# Connect to same server but use different model
base_url = "http://192.168.1.100:11434"

# Use fast model
agent_fast = create_firewall_agent(
    model="granite4.1",  # 3B model, faster
    base_url=base_url
)
answer_fast = agent_fast.query("List all policies")
print("Fast model response:", answer_fast[:100], "...")
print()

# Use high-quality model
agent_quality = create_firewall_agent(
    model="mistral",  # Higher quality
    base_url=base_url
)
answer_quality = agent_quality.query("List all policies")
print("Quality model response:", answer_quality[:100], "...")
print()

# ==============================================================================
# Example 7: Programmatic - Query Function with Remote Server
# ==============================================================================

print("=" * 70)
print("Example 7: Using query_firewall() with Remote Server")
print("=" * 70)

# Note: query_firewall() currently doesn't expose base_url parameter
# So you need to create agent first, OR modify query_firewall()

# To use with remote server, modify query_firewall() to accept base_url:
# def query_firewall(question: str, model: str = "qwen2.5",
#                    base_url: str = "http://localhost:11434") -> str:
#     agent = create_firewall_agent(model=model, base_url=base_url)
#     return agent.query(question)

# Then use like:
# answer = query_firewall("Show statistics", model="qwen2.5",
#                         base_url="http://192.168.1.100:11434")

print("(See modification needed in langchain_firewall_agent.py)")
print()

# ==============================================================================
# Example 8: Configuration from Environment
# ==============================================================================

print("=" * 70)
print("Example 8: Load Configuration from Environment")
print("=" * 70)

import os
from dotenv import load_dotenv

# Load from .env file
load_dotenv()

# Get from environment (or use default)
ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5")

agent_env = create_firewall_agent(
    model=ollama_model,
    base_url=ollama_host
)
answer = agent_env.query("Show VPN status")
print(f"Connected to: {ollama_host}")
print(f"Using model: {ollama_model}")
print(answer)
print()

# ==============================================================================
# How to Setup Remote Ollama Server
# ==============================================================================

print("=" * 70)
print("How to Setup Remote Ollama Server")
print("=" * 70)

setup_instructions = """
On the Remote Machine (where Ollama will run):

1. Install Ollama (if not already installed):
   Linux/Mac:
   curl -fsSL https://ollama.ai/install.sh | sh

   Windows:
   Download from https://ollama.ai

2. Pull a model:
   ollama pull qwen2.5
   ollama pull mistral
   ollama pull llama3.2

3. Start Ollama listening on all interfaces:
   ollama serve --host 0.0.0.0:11434

   Or use environment variable:
   OLLAMA_HOST=0.0.0.0:11434 ollama serve

4. Verify it's working (from remote machine):
   curl http://localhost:11434/api/tags

On Your Local Machine (where you run this app):

1. Test connectivity to remote Ollama:
   curl http://192.168.1.100:11434/api/tags

   Should return JSON with available models:
   {"models": [{"name": "qwen2.5:latest"}, ...]}

2. Update this file or langchain_firewall_agent.py:
   base_url="http://192.168.1.100:11434"

3. Run the application:
   python langchain_firewall_agent.py qwen2.5
"""

print(setup_instructions)

# ==============================================================================
# Summary
# ==============================================================================

print("=" * 70)
print("Summary: Changing from Local to Remote Ollama")
print("=" * 70)

summary = """
✓ Easy to change - just update the base_url parameter

✓ Three ways to change:
  1. Edit code (lines 100 & 285 in langchain_firewall_agent.py)
  2. Use Python API: create_firewall_agent(base_url="http://remote:11434")
  3. Environment variable: OLLAMA_HOST (requires code modification)

✓ Works with:
  • Local machine: http://localhost:11434
  • LAN computer: http://192.168.1.100:11434
  • Hostname: http://ollama.local:11434
  • Docker: http://docker-host:11434
  • Public IP: http://203.0.113.42:11434

✓ Remote Ollama must be:
  • Running and accessible
  • Listening on the network (--host 0.0.0.0:11434)
  • Have models installed (ollama pull <model>)

✓ Recommended for most flexibility:
  Use Python API with base_url parameter
"""

print(summary)
