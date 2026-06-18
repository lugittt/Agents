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
        "description": "List configured static routes (destination, gateway, device, status).",
        "func": lambda: api.list_static_routes(),
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
        base_url: str = "http://localhost:11434",
        temperature: float = 0.3,
    ):
        """
        Initialize agent with local Ollama model.

        Args:
            model: Ollama model name (default: llama2)
                   Popular options: llama2, mistral, neural-chat, openchat
            base_url: Ollama server URL (default: http://localhost:11434)
            temperature: Model temperature (0-1, default: 0.3 for consistency)
        """
        self.model_name = model
        self.base_url = base_url

        print(f"[INFO] Connecting to Ollama at {base_url}...")
        print(f"[INFO] Using model: {model}")

        self.llm = OllamaLLM(
            model=model,
            base_url=base_url,
            temperature=temperature,
            num_ctx=4096,      # Context window size
            num_predict=350,   # Cap response length to keep answers short
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
1. Use tools to fetch current firewall state
2. Cross-reference observations with documentation
3. Provide specific, actionable recommendations
4. Always cite the documentation for justification

## Official Documentation:

{self.documentation}

## Communication Style:
- Be brief. Answer in at most 3-5 short sentences or a few bullet points.
- Lead with the direct answer first; add detail only if essential.
- Do NOT include examples, sample commands, or hypothetical scenarios unless explicitly asked.
- Do NOT restate the question or pad with background the user did not request.
- Only cite documentation when it directly justifies the answer.
- Stop as soon as the question is answered."""

    def _call_tool(self, tool_name: str, **kwargs) -> str:
        """Call a tool and return result."""
        if tool_name not in TOOLS:
            return f"Unknown tool: {tool_name}"

        try:
            tool_info = TOOLS[tool_name]
            print(f"[TOOL] Calling {tool_name}...")
            result = tool_info["func"](**kwargs)
            return result
        except Exception as e:
            return f"Error calling {tool_name}: {e}"

    def _parse_tool_call(self, response_text: str) -> Optional[tuple]:
        """
        Parse tool call from response.
        Looks for patterns like: TOOL: tool_name(param=value)
        """
        import re

        # Look for tool calls in response
        pattern = r"TOOL:\s*(\w+)\((.*?)\)"
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

        # Format prompt for Ollama
        prompt = f"""{system_prompt}

User Question: {question}

Instructions:
- If you need data from the firewall, use tool calls with format: TOOL: tool_name(param=value)
- Answer briefly: 3-5 short sentences or a few bullets, direct answer first.
- No examples, sample commands, or extra background unless explicitly asked.

Answer:"""

        print(f"\n[PROCESSING] Sending to {self.model_name}...")

        # Get response from Ollama
        response = self.llm.invoke(prompt)

        # Check if response mentions needing tool calls
        max_iterations = 3
        iteration = 0

        while "TOOL:" in response and iteration < max_iterations:
            iteration += 1
            print(f"[ITERATION] {iteration}/{max_iterations}")

            # Parse tool call
            tool_call = self._parse_tool_call(response)
            if not tool_call:
                break

            tool_name, params = tool_call
            print(f"[TOOL CALL] {tool_name}({params})")

            # Call tool
            tool_result = self._call_tool(tool_name, **params)

            # Add tool result and continue
            prompt = f"""{system_prompt}

User Question: {question}

Previous Response:
{response}

Tool Result from {tool_name}:
{tool_result}

Now answer the question briefly (3-5 short sentences or a few bullets), direct answer first, no examples:"""

            response = self.llm.invoke(prompt)

        return response


# ==============================================================================
# 4. CREATE AGENT INSTANCE
# ==============================================================================


def create_firewall_agent(
    model: str = "llama2",
    base_url: str = "http://localhost:11434",
    temperature: float = 0.3,
) -> FirewallAgent:
    """
    Create a firewall agent using local Ollama model.

    Args:
        model: Ollama model name (default: llama2)
        base_url: Ollama server URL
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
