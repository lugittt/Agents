"""
Deterministic test of the agent's tool-calling loop and PDF context.

Mocks the LLM (scripted responses) and the firewall so we can assert, without
a live model, that:
  1. The documentation (PDF context) is injected into the prompt.
  2. The loop runs MULTIPLE iterations when the model keeps emitting TOOL: calls.
  3. Tool results ACCUMULATE across iterations (cross-tool correlation).
  4. The [PDF] indicator is appended.
"""

import os

os.environ.setdefault("FORTIGATE_HOST", "x")
os.environ.setdefault("FORTIGATE_TOKEN", "x")

import langchain_firewall_agent as agent_mod
from langchain_firewall_agent import FirewallAgent, create_documentation_context


class FakeLLM:
    """Returns scripted responses and records every prompt it receives."""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.scripted.pop(0) if self.scripted else "No more script."


def make_agent(scripted):
    """Build a FirewallAgent without touching real Ollama/FortiGate."""
    a = FirewallAgent.__new__(FirewallAgent)
    a.model_name = "fake-model"
    a.base_url = "http://localhost:11434"
    a.documentation = create_documentation_context()
    a.doc_source = "Built-in FortiGate Documentation"
    a.messages = []
    a.llm = FakeLLM(scripted)
    # Replace real tool execution with canned firewall data.
    a._call_tool = lambda name, **kw: f"<<DATA from {name} {kw}>>"
    return a


def run():
    passed = []

    # Script: two tool calls in sequence, then a final answer.
    scripted = [
        "TOOL: system_health_check()",
        "TOOL: get_admin_logs(rows=5)",
        "CPU is at OK levels and the last change was an admin login.\n"
        "Recommendation: enable traffic logging on key policies.",
    ]
    a = make_agent(scripted)
    answer = a.query("Is the firewall healthy and what changed recently?")

    fake = a.llm

    # 1. PDF/documentation present in the FIRST prompt.
    doc_marker = "FortiGate Firewall Configuration Guide"
    t1 = doc_marker in fake.prompts[0]
    passed.append(("Documentation injected into prompt", t1))

    # 2. Multiple iterations actually happened (2 tool calls -> 3 invokes).
    t2 = len(fake.prompts) == 3
    passed.append(("Loop ran multiple iterations (3 LLM invokes)", t2))

    # 3. Accumulation: the LAST prompt contains BOTH tool results.
    last = fake.prompts[-1]
    t3 = ("system_health_check" in last) and ("get_admin_logs" in last)
    passed.append(("Both tool results accumulated in final prompt", t3))

    # 3b. Documentation still present in later prompts too.
    t3b = doc_marker in last
    passed.append(("Documentation present in follow-up prompts", t3b))

    # 4. PDF indicator appended (recommendation is doc-based).
    t4 = "[PDF] Documentation used in this answer" in answer
    passed.append(("[PDF] indicator appended to answer", t4))

    # 5. Single-tool question stops after ONE iteration (expected behavior).
    a2 = make_agent(["TOOL: list_firewall_policies()",
                     "There are 7 policies.\nRecommendation: none"])
    a2.query("List policies")
    t5 = len(a2.llm.prompts) == 2  # 1 initial + 1 after the single tool
    passed.append(("Single-tool query => exactly one iteration", t5))

    # 6. Loop is capped at max_iterations (model spams TOOL: forever).
    a3 = make_agent(["TOOL: list_firewall_policies()"] * 10)
    a3.query("loop forever")
    # 1 initial invoke + up to 3 iteration invokes = 4 total.
    t6 = len(a3.llm.prompts) == 4
    passed.append(("Loop capped at max_iterations (=3)", t6))

    # 7. Parser accepts both with and without parentheses.
    p_with = a._parse_tool_call("TOOL: get_admin_logs(rows=5)")
    p_without = a._parse_tool_call("TOOL: get_system_status")
    t7 = (p_with == ("get_admin_logs", {"rows": "5"})) and \
         (p_without == ("get_system_status", {}))
    passed.append(("Parser handles parens AND no-parens forms", t7))

    print("=" * 64)
    print("AGENT LOOP / PDF CONTEXT TEST")
    print("=" * 64)
    ok = True
    for name, result in passed:
        print(f"[{'PASS' if result else 'FAIL'}] {name}")
        ok = ok and result
    print("-" * 64)
    print("RESULT:", "ALL PASSED" if ok else "SOME FAILED")
    print("\nFinal answer returned by agent:\n", answer)
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
