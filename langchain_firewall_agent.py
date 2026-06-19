"""
LangChain application combining FortiGate REST API + PDF documentation.
Uses LOCAL OLLAMA model running on localhost:11434.

Creates an intelligent agent that answers technical firewall questions
by combining live data from FortiGate + reference documentation.
"""

import os
import sys
from typing import Any, Optional
import json

from langchain_ollama import OllamaLLM
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

from fortigate_api_wrapper import FortiGateAPIWrapper
from pdf_loader import PDFDocumentationLoader, create_documentation_context

load_dotenv()


# Ollama server URL — configurable via .env (OLLAMA_BASE_URL), e.g.
# http://localhost:11434 (local) or http://192.168.1.100:11434 (remote).
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


# ==============================================================================
# 0. TERMINAL COLORS
# ==============================================================================

# ANSI color codes used to render the header.
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"
    GREY = "\033[90m"
    WHITE = "\033[97m"


def _enable_ansi_colors() -> None:
    """Enable ANSI escape sequence processing on Windows terminals."""
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004 on STD_OUTPUT_HANDLE (-11)
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def _header_lines(app_name: str, model_name: str, base_url: str, doc_source: str) -> list:
    """Build the colored header rows (used by both the static and sticky header)."""
    width = 80
    line = f"{C.CYAN}{'-' * width}{C.RESET}"
    return [
        line,
        f"{C.BOLD}{C.MAGENTA}  {app_name}{C.RESET}",
        f"  {C.GREY}LLM model:{C.RESET} {C.BOLD}{C.GREEN}{model_name}{C.RESET}"
        f"   {C.GREY}@{C.RESET} {C.BLUE}{base_url}{C.RESET}",
        f"  {C.GREY}Knowledge base:{C.RESET} {C.BOLD}{C.YELLOW}{doc_source}{C.RESET}",
        line,
    ]


# Number of rows reserved at the top of the screen for the sticky header.
HEADER_ROWS = 5


def print_header(app_name: str, model_name: str, base_url: str, doc_source: str) -> None:
    """Print a colored application header with model + documentation info."""
    _enable_ansi_colors()
    for ln in _header_lines(app_name, model_name, base_url, doc_source):
        print(ln)


def _term_rows() -> int:
    """Return the terminal height in rows (fallback 24)."""
    import shutil

    try:
        return shutil.get_terminal_size((80, 24)).lines
    except Exception:
        return 24


def _draw_sticky_header(lines: list) -> None:
    """Paint the header into the top fixed rows without disturbing the cursor."""
    out = sys.stdout
    out.write("\0337")  # save cursor position
    for i, ln in enumerate(lines, start=1):
        out.write(f"\033[{i};1H\033[2K{ln}")  # absolute row, clear line, draw
    out.write("\0338")  # restore cursor position
    out.flush()


def install_sticky_header(
    app_name: str, model_name: str, base_url: str, doc_source: str
) -> bool:
    """
    Pin the header to the top rows and confine scrolling to the area below it.

    Returns True if the sticky header was installed, False if the terminal
    can't support it (e.g. output is piped) and the caller should fall back
    to the normal static header.
    """
    if not sys.stdout.isatty():
        return False

    _enable_ansi_colors()
    lines = _header_lines(app_name, model_name, base_url, doc_source)
    rows = _term_rows()
    if rows <= HEADER_ROWS + 1:
        return False  # terminal too short to bother

    out = sys.stdout
    out.write("\033[2J")                       # clear screen
    out.write(f"\033[{HEADER_ROWS + 1};{rows}r")  # scroll region = below header
    _draw_sticky_header(lines)                  # paint fixed header at top
    out.write(f"\033[{HEADER_ROWS + 1};1H")     # move cursor into scroll area
    out.flush()
    return True


def refresh_sticky_header(
    app_name: str, model_name: str, base_url: str, doc_source: str
) -> None:
    """Repaint the fixed header (cheap; handles terminal resize between turns)."""
    if not sys.stdout.isatty():
        return
    _draw_sticky_header(_header_lines(app_name, model_name, base_url, doc_source))


def remove_sticky_header() -> None:
    """Release the scroll region and drop the cursor back to the bottom."""
    if not sys.stdout.isatty():
        return
    out = sys.stdout
    out.write("\033[r")                  # reset scroll region to full screen
    out.write(f"\033[{_term_rows()};1H") # cursor to bottom
    out.write("\n")
    out.flush()


# ==============================================================================
# 1. INITIALIZE API WRAPPER AND PDF LOADER
# ==============================================================================

api = FortiGateAPIWrapper()
pdf_loader = PDFDocumentationLoader()


# ==============================================================================
# 2. DEFINE TOOLS
# ==============================================================================

TOOLS = {
    "list_firewall_policies": {
        "description": "Fetch all current firewall policies from FortiGate. Returns a JSON list with policy IDs, names, interfaces, addresses, and services.",
        "func": lambda: api.list_policies(),
    },
    "get_firewall_policy": {
        "description": "Get detailed configuration of a specific firewall policy by ID.",
        "func": lambda policy_id: api.get_policy(int(policy_id)),
        "params": {"policy_id": "int"},
    },
    "get_address_objects": {
        "description": "List all address objects and address groups configured in FortiGate.",
        "func": lambda: api.list_addresses(),
    },
    "get_service_objects": {
        "description": "List all service objects and service groups.",
        "func": lambda: api.list_services(),
    },
    "get_network_interfaces": {
        "description": "List all network interfaces configured on the firewall.",
        "func": lambda: api.list_interfaces(),
    },
    "get_traffic_logs": {
        "description": "Fetch traffic logs from FortiGate with optional filters (srcip, dstip, action, policyid).",
        "func": lambda srcip=None, dstip=None, action=None, policyid=None: api.get_traffic_logs(
            srcip=srcip, dstip=dstip, action=action, policyid=policyid
        ),
        "params": {"srcip": "str", "dstip": "str", "action": "str", "policyid": "int"},
    },
    "get_policy_statistics": {
        "description": "Get per-policy statistics from FortiGate monitor API.",
        "func": lambda: api.get_policy_stats(),
    },
    "get_vpn_status": {
        "description": "Get status of IPsec VPN tunnels from monitor API.",
        "func": lambda: api.get_vpn_tunnels(),
    },
    "get_firewall_health": {
        "description": "Get raw system health and status information (CPU, memory, disk, uptime, firmware, serial).",
        "func": lambda: api.get_system_status(),
    },
    "system_health_check": {
        "description": "Run an interpreted health check. Returns CPU/memory/disk usage with OK/WARN/CRITICAL flags plus interface up/down counts. Use this to quickly assess whether the firewall is under resource pressure.",
        "func": lambda: api.system_health_check(),
    },
    "get_admin_logs": {
        "description": "Show the most recent administrator activity: logins and configuration CHANGES made on the device. Use this to find what was last changed and by whom. Optional 'rows' limits how many entries to return.",
        "func": lambda rows=50: api.get_admin_logs(rows=int(rows)),
        "params": {"rows": "int"},
    },
    "get_system_logs": {
        "description": "Show system event logs (reboots, faults, daemon events). Optional 'severity' filter: critical, alert, error, warning, notice, info, debug. Optional 'rows' limits entries.",
        "func": lambda rows=50, severity=None: api.get_system_logs(rows=int(rows), severity=severity),
        "params": {"rows": "int", "severity": "str"},
    },
    "get_interface_stats": {
        "description": "Get per-interface statistics: packets, bytes, errors, and link state.",
        "func": lambda: api.get_interface_stats(),
    },
    "list_vips": {
        "description": "List virtual IPs (port forwarding / NAT mappings) configured on the firewall.",
        "func": lambda: api.list_vips(),
    },
    "list_static_routes": {
        "description": "Use for CONFIGURED static routes. List static routes (destination, gateway, device, status).",
        "func": lambda: api.list_static_routes(),
    },
    "get_routing_table": {
        "description": "Use for how traffic is ACTUALLY routed now / next-hop / effective routes. Returns the live IPv4 routing table (FIB), including connected and dynamic routes — not just static config.",
        "func": lambda: api.get_routing_table(),
    },
    "get_firewall_sessions": {
        "description": "Use for active/live connections, current sessions, who is connected right now. Returns active firewall sessions. Optional 'count' limits entries.",
        "func": lambda count=50: api.get_firewall_sessions(),
        "params": {"count": "int"},
    },
    "get_arp_table": {
        "description": "Use for IP-to-MAC mappings, devices seen on the L2 network, ARP entries.",
        "func": lambda: api.get_arp_table(),
    },
    "get_dhcp_leases": {
        "description": "Use for which device has which IP, DHCP assignments, leased addresses, hostnames on the network.",
        "func": lambda: api.get_dhcp_leases(),
    },
    "get_ha_status": {
        "description": "Use for high availability / cluster / failover / HA peer status and sync state.",
        "func": lambda: api.get_ha_status(),
    },
    "get_denied_traffic": {
        "description": "Use for blocked/denied/dropped traffic. Shortcut returning traffic logs filtered to denied actions. Good for 'why is X blocked'.",
        "func": lambda: api.get_denied_traffic(),
    },
    "get_resource_usage": {
        "description": "Use for raw CPU/memory/disk usage numbers. For an interpreted OK/WARN/CRITICAL summary prefer system_health_check.",
        "func": lambda: api.get_resource_usage(),
    },
    "search_documentation": {
        "description": "Search FortiGate documentation for a specific keyword or topic.",
        "func": lambda keyword: "\n".join(pdf_loader.search_documentation(keyword)),
        "params": {"keyword": "str"},
    },
    "get_documentation_section": {
        "description": "Get a specific section from FortiGate documentation.",
        "func": lambda section_name: pdf_loader.get_section(section_name),
        "params": {"section_name": "str"},
    },
}


# ==============================================================================
# 3. OLLAMA AGENT IMPLEMENTATION
# ==============================================================================


class FirewallAgent:
    """Firewall agent using local Ollama model."""

    def __init__(
        self,
        model: str = "llama2",
        base_url: str = None,
        temperature: float = 0.3,
    ):
        """
        Initialize agent with local Ollama model.

        Args:
            model: Ollama model name (default: llama2)
                   Popular options: llama2, mistral, neural-chat, openchat
            base_url: Ollama server URL. Defaults to OLLAMA_BASE_URL from .env,
                      falling back to http://localhost:11434.
            temperature: Model temperature (0-1, default: 0.3 for consistency)
        """
        if base_url is None:
            base_url = DEFAULT_OLLAMA_URL
        self.model_name = model
        self.base_url = base_url

        print(f"[INFO] Connecting to Ollama at {base_url}...")
        print(f"[INFO] Using model: {model}")

        self.llm = OllamaLLM(
            model=model,
            base_url=base_url,
            temperature=temperature,
            num_ctx=8192,      # Larger window: docs + accumulated tool results must fit
            num_predict=1024,  # Generous cap so tool calls / answers aren't truncated
        )

        self.documentation = create_documentation_context()
        self.messages = []

        # Name of the documentation source loaded into the agent's context.
        if pdf_loader.pdf_path and os.path.exists(pdf_loader.pdf_path):
            self.doc_source = os.path.basename(pdf_loader.pdf_path)
        else:
            self.doc_source = "Built-in FortiGate Documentation"

        # Verify connection
        try:
            self._verify_connection()
        except Exception as e:
            print(f"[WARNING] Could not verify Ollama connection: {e}")
            print(f"[INFO] Make sure Ollama is running: ollama serve")

    APP_NAME = "FortiGate Firewall AI Agent"

    def show_header(self) -> None:
        """Print the colored application header once (non-sticky)."""
        print_header(self.APP_NAME, self.model_name, self.base_url, self.doc_source)

    def install_header(self) -> bool:
        """Pin the colored header to the top so chat output scrolls beneath it."""
        return install_sticky_header(
            self.APP_NAME, self.model_name, self.base_url, self.doc_source
        )

    def refresh_header(self) -> None:
        """Repaint the pinned header (handles terminal resize between turns)."""
        refresh_sticky_header(
            self.APP_NAME, self.model_name, self.base_url, self.doc_source
        )

    def _verify_connection(self) -> bool:
        """Verify Ollama is accessible."""
        import httpx

        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                print("[OK] Ollama connection verified")
                return True
        except Exception as e:
            print(f"[ERROR] Cannot connect to Ollama: {e}")
            raise

    def _build_system_prompt(self) -> str:
        """Build system prompt with documentation."""
        return f"""You are an expert FortiGate firewall administrator assistant.

Your role is to help troubleshoot firewall issues, explain configurations, and provide
best practice guidance by combining live data and reference documentation.

## Available Tools:

{json.dumps({k: v['description'] for k, v in TOOLS.items()}, indent=2)}

When answering questions:
1. ALWAYS fetch live data first by emitting a tool call. Do not describe which
   tool you would use or answer from memory — actually call it.
2. To call a tool, output a line in EXACTLY this format and nothing else:
   TOOL: tool_name(param=value)
   (omit the parentheses arguments if the tool takes none, e.g. TOOL: list_firewall_policies())
3. After you receive the tool result, analyze it and give the real answer.
4. Cross-reference the data with the documentation where relevant.

## Official Documentation:

{self.documentation}

## Communication Style:
- Base every answer on data you fetched with a tool, not on assumptions.
- Give a complete, specific answer using the actual values from the firewall.
- Add 1-3 sentences of relevant context/background so the answer is well-rounded
  and the user understands the "why", not just the "what".
- Do NOT include examples, sample commands, or hypothetical scenarios.
- Be focused — no filler or restating the question.
- In the Recommendation, when relevant, cite an official documentation link —
  but ONLY a URL from the "Reference Links" list above. Never invent a URL.

## Tool Selection Guide (match the user's intent to ONE tool):
- rules / policies / what is allowed or blocked by config -> list_firewall_policies (one policy -> get_firewall_policy)
- IP / subnet / address objects or groups -> get_address_objects
- ports / protocols / services -> get_service_objects
- interfaces / ports config / IP on a port -> get_network_interfaces
- NAT / port forwarding / VIP -> list_vips
- configured static routes -> list_static_routes
- how traffic is routed now / next hop / effective routes -> get_routing_table
- health / CPU / memory / disk / resource pressure -> system_health_check (raw numbers -> get_resource_usage)
- firmware / serial / uptime / model -> get_firewall_health
- live connections / active sessions / who is connected -> get_firewall_sessions
- per-interface counters / errors / throughput -> get_interface_stats
- IP-to-MAC / devices on LAN -> get_arp_table
- which device has which IP / DHCP -> get_dhcp_leases
- HA / cluster / failover -> get_ha_status
- VPN tunnels up/down -> get_vpn_status
- traffic logs / who went where -> get_traffic_logs ; blocked traffic -> get_denied_traffic
- recent config CHANGES / who logged in -> get_admin_logs
- system events / reboots / faults -> get_system_logs
- policy hit counts / most active rules -> get_policy_statistics
- best practice / how-to / explanation -> search_documentation or get_documentation_section

Pick the single most specific tool. If unsure between two, choose the one whose
keywords best match the question. Emit exactly one TOOL: line."""

    def _call_tool(self, tool_name: str, **kwargs) -> str:
        """Call a tool and return result."""
        if tool_name not in TOOLS:
            # Resolve near-miss / hallucinated names (e.g. "check_health" ->
            # "system_health_check") so a small slip doesn't abort the answer.
            import difflib

            close = difflib.get_close_matches(tool_name, list(TOOLS.keys()), n=1, cutoff=0.6)
            if close:
                print(f"[TOOL] Resolved '{tool_name}' -> '{close[0]}'")
                tool_name = close[0]
            else:
                return (
                    f"Unknown tool '{tool_name}'. Choose one of: "
                    + ", ".join(TOOLS.keys())
                )

        try:
            tool_info = TOOLS[tool_name]
            print(f"[TOOL] Calling {tool_name}...")
            result = tool_info["func"](**kwargs)
            return result
        except Exception as e:
            return f"Error calling {tool_name}: {e}"

    def _parse_tool_call(self, response_text: str) -> Optional[tuple]:
        """
        Parse a tool call from the model's response.

        Accepts both  TOOL: tool_name(param=value)  and the parenthesis-less
        TOOL: tool_name  form. Being lenient matters: if "TOOL:" appears but
        can't be parsed, the loop would otherwise break and dump the raw
        "TOOL:" line to the user instead of running the tool.
        """
        import re

        # Parentheses (and their contents) are optional.
        pattern = r"TOOL:\s*(\w+)\s*(?:\((.*?)\))?"
        matches = re.findall(pattern, response_text)

        if matches:
            tool_name, params_str = matches[0]
            # Simple param parsing
            params = {}
            if params_str:
                for param in params_str.split(","):
                    if "=" in param:
                        key, val = param.split("=", 1)
                        params[key.strip()] = val.strip().strip('"\'')
            return (tool_name, params)
        return None

    def query(self, question: str) -> str:
        """
        Query the agent.

        Args:
            question: The firewall question to answer

        Returns:
            Agent response with analysis and recommendations
        """
        system_prompt = self._build_system_prompt()
        doc_tools = {"search_documentation", "get_documentation_section"}
        doc_used = False  # set True when the model pulls from the documentation

        # Format prompt for Ollama
        prompt = f"""{system_prompt}

User Question: {question}

Instructions:
- If the question needs firewall data, your FIRST output must be a tool call line:
  TOOL: tool_name(param=value)
  Output only that line — do not explain or answer yet. You will get the result next.
  You may call several tools (across turns) — gather ALL the data you need first.
- Once you have the data, answer using the real values. No examples or hypotheticals.
- End every answer with a section titled "Recommendation:" containing 1-2
  actionable suggestions drawn from the Official Documentation above, with a
  brief reason. Where relevant, add an official link on its own line as
  "Docs: <name> - <url>" using ONLY a URL from the Reference Links list (never
  invent one). If the documentation offers nothing relevant, write
  "Recommendation: none".

Answer:"""

        print(f"\n[PROCESSING] Sending to {self.model_name}...")

        # Get response from Ollama
        response = self.llm.invoke(prompt)

        # Tool-calling loop. Accumulate EVERY tool result so the model keeps
        # full context across iterations (previously only the latest result
        # was passed forward, which broke cross-tool correlation).
        max_iterations = 3
        iteration = 0
        gathered = []  # list of (tool_name, result) across all iterations

        while "TOOL:" in response and iteration < max_iterations:
            iteration += 1
            print(f"[ITERATION] {iteration}/{max_iterations}")

            # Parse tool call
            tool_call = self._parse_tool_call(response)
            if not tool_call:
                break

            tool_name, params = tool_call
            print(f"[TOOL CALL] {tool_name}({params})")

            if tool_name in doc_tools:
                doc_used = True
                print(f"[PDF] Documentation lookup: {tool_name}({params})")

            # Call tool and remember the result.
            tool_result = self._call_tool(tool_name, **params)
            gathered.append((tool_name, tool_result))

            # Re-send ALL gathered data, not just the most recent result.
            gathered_text = "\n\n".join(
                f"Tool Result from {name}:\n{res}" for name, res in gathered
            )
            prompt = f"""{system_prompt}

User Question: {question}

Data gathered so far:
{gathered_text}

Using ALL of the gathered data above, answer the question with the real values.
Be specific, with no examples or hypotheticals, and add 1-3 sentences of
relevant context so the answer is well-rounded. If you still need more data,
emit another TOOL: call instead of answering.
End with a section titled "Recommendation:" containing 1-2 actionable
suggestions (with a brief reason) drawn from the Official Documentation. Where
relevant, add an official link on its own line as "Docs: <name> - <url>" using
ONLY a URL from the Reference Links list (never invent one). If nothing in the
documentation is relevant, write "Recommendation: none":"""

            response = self.llm.invoke(prompt)

        # Documentation contributes either via a doc tool call or via the
        # docs-derived Recommendation section that ends each answer.
        if doc_used or self._recommendation_present(response):
            indicator = f"\n\n[PDF] Documentation used in this answer (source: {self.doc_source})"
        else:
            indicator = "\n\n[PDF] No documentation was used in this answer"

        return response + indicator

    def _recommendation_present(self, text: str) -> bool:
        """True if the answer has a Recommendation section with real content."""
        import re

        m = re.search(r"Recommendation:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
        if not m:
            return False
        content = m.group(1).strip().lower()
        return bool(content) and not content.startswith("none")


# ==============================================================================
# 4. CREATE AGENT INSTANCE
# ==============================================================================


def create_firewall_agent(
    model: str = "llama2",
    base_url: str = None,
    temperature: float = 0.3,
) -> FirewallAgent:
    """
    Create a firewall agent using local Ollama model.

    Args:
        model: Ollama model name (default: llama2)
        base_url: Ollama server URL. Defaults to OLLAMA_BASE_URL from .env,
                  falling back to http://localhost:11434.
        temperature: Model temperature (0-1)

    Returns:
        FirewallAgent instance
    """
    return FirewallAgent(model=model, base_url=base_url, temperature=temperature)


# ==============================================================================
# 5. PROGRAMMATIC API
# ==============================================================================


def query_firewall(
    question: str, model: str = "llama2", verbose: bool = False
) -> str:
    """
    Programmatic API for querying the firewall agent.

    Args:
        question: Your firewall question
        model: Ollama model to use (default: llama2)
        verbose: Show processing (default: False)

    Returns:
        Agent response with analysis and recommendations
    """
    agent = create_firewall_agent(model=model)
    return agent.query(question)


# ==============================================================================
# 6. EXAMPLE QUERIES
# ==============================================================================


def example_queries():
    """Show example questions the agent can answer."""
    return [
        "Why is traffic from 10.0.1.5 to 192.168.1.1 being denied?",
        "Show me all firewall policies that are currently disabled",
        "What services are configured for HTTPS and SSH?",
        "Which policies are getting the most traffic? Show me statistics.",
        "How should I troubleshoot a VPN tunnel that's down?",
        "Check my system health - is the firewall under resource pressure?",
        "What configuration changes were made on the device recently?",
        "Show me the last admin logins and who changed what.",
        "Are there any critical system events in the logs?",
        "List all port-forwarding VIPs configured on the firewall.",
        "Show me the static routing table.",
        "Create a new policy that allows HTTP/HTTPS from internal networks to the DMZ",
        "Which policies are matching traffic from the LAN interface?",
        "Show me best practices for organizing firewall policies",
        "Why would a policy status being 'disable' prevent traffic?",
    ]


# ==============================================================================
# 7. MAIN ENTRY POINT
# ==============================================================================


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    # Allow model selection from command line
    model = "llama2"
    if len(sys.argv) > 1:
        model = sys.argv[1]
        print(f"[INFO] Using model from command line: {model}\n")

    # Create agent
    print("Initializing agent...")
    try:
        agent = create_firewall_agent(model=model)
        print("[OK] Agent ready\n")
    except Exception as e:
        print(f"[ERROR] Failed to initialize agent: {e}")
        print("\nMake sure Ollama is running:")
        print("  ollama serve")
        print("\nThen pull a model:")
        print("  ollama pull llama2")
        print("  ollama pull mistral")
        print("  ollama pull neural-chat")
        sys.exit(1)

    # Pin the colored header to the top so the chat scrolls beneath it.
    # Falls back to a plain printed header if the terminal can't support it.
    sticky = agent.install_header()
    if not sticky:
        agent.show_header()
    print()

    # Show example queries
    print("Example queries you can ask:")
    print("-" * 80)
    for i, query_example in enumerate(example_queries(), 1):
        print(f"{i}. {query_example}")
    print("-" * 80)
    print()
    print("Available Ollama models: llama2, mistral, neural-chat, openchat, dolphin-mixtral")
    print("Usage: python langchain_firewall_agent.py [model_name]")
    print()

    # Interactive loop
    try:
        while True:
            try:
                if sticky:
                    agent.refresh_header()  # keep it crisp across resizes
                user_input = input("\n[INPUT] Ask about your firewall (or 'quit'): ").strip()
                if user_input.lower() in ["quit", "exit", "q"]:
                    print("Goodbye!")
                    break

                if not user_input:
                    continue

                result = agent.query(user_input)

                print("\n[ANSWER]")
                print("-" * 80)
                print(result)
                print("-" * 80)

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"[ERROR] {e}")
                import traceback

                traceback.print_exc()
    finally:
        # Release the scroll region so the terminal is left in a clean state.
        if sticky:
            remove_sticky_header()
