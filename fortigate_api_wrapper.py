"""
Wrapper to call FortiGate REST API tools from LangChain.
Executes API calls and returns results as formatted strings.
"""

import json
import subprocess
import os
from typing import Any
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class FortiGateAPIWrapper:
    """Wrapper around the FortiGate REST API for LangChain integration."""

    def __init__(self):
        """Initialize FortiGate REST API client."""
        pass

    def _call_tool(self, tool_name: str, **kwargs) -> dict:
        """
        Call a FortiGate API tool and return structured result.
        """
        try:
            result = self._invoke_local_tool(tool_name, kwargs)
            return {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _format(self, result: dict) -> str:
        """
        Render a tool result as a JSON string. On error, surface the real
        FortiGate message (e.g. HTTP 403/404) instead of crashing on a
        missing 'data' key — so failing tools explain WHY they failed.
        Also flags successful-but-empty results so the model knows the call
        worked but the device returned nothing.
        """
        if result.get("status") == "error":
            return json.dumps({"error": result.get("message")}, indent=2)
        data = result.get("data")
        if data in (None, [], {}, ""):
            return json.dumps(
                {"info": "The call succeeded but the device returned no data."},
                indent=2,
            )
        return json.dumps(data, indent=2)

    def _log_source(self):
        """
        Optional fixed log source from FORTIGATE_LOG_SOURCE (disk|memory|forticloud).
        Returns None when unset, which lets the client auto-fall-back across
        sources — needed because not every FortiGate logs to disk.
        """
        src = (os.environ.get("FORTIGATE_LOG_SOURCE") or "").strip().lower()
        return src or None

    def _invoke_local_tool(self, tool_name: str, params: dict) -> Any:
        """
        Invoke FortiGate API tool methods by directly importing and calling.
        """
        import sys
        from fortigate import FortiGateClient

        # Initialize FortiGate client with env vars
        fg = FortiGateClient(
            host=os.environ.get("FORTIGATE_HOST", "192.168.1.1"),
            api_token=os.environ.get("FORTIGATE_TOKEN", ""),
            vdom=os.environ.get("FORTIGATE_VDOM", "root"),
            verify_ssl=os.environ.get("FORTIGATE_VERIFY_SSL", "false").lower() == "true",
        )

        # Map tool names to FortiGateClient methods
        if tool_name == "list_policies":
            policies = fg.list_policies()
            return [self._policy_summary(p) for p in policies]

        elif tool_name == "get_policy":
            policy_id = params.get("policy_id")
            return fg.get_policy(policy_id)

        elif tool_name == "list_addresses":
            addrs = fg.list_addresses()
            groups = fg.list_address_groups()
            return {
                "addresses": [
                    {
                        "name": a["name"],
                        "type": a.get("type"),
                        "subnet": a.get("subnet", ""),
                    }
                    for a in addrs
                ],
                "groups": [
                    {"name": g["name"], "members": [m["name"] for m in g.get("member", [])]}
                    for g in groups
                ],
            }

        elif tool_name == "list_services":
            services = fg.list_services()
            return [
                {
                    "name": s["name"],
                    "protocol": s.get("protocol"),
                    "tcp_portrange": s.get("tcp-portrange", ""),
                    "udp_portrange": s.get("udp-portrange", ""),
                }
                for s in services
            ]

        elif tool_name == "list_interfaces":
            ifaces = fg.list_interfaces()
            return [
                {
                    "name": i["name"],
                    "type": i.get("type"),
                    "ip": i.get("ip", ""),
                    "status": i.get("status"),
                }
                for i in ifaces
            ]

        elif tool_name == "get_traffic_logs":
            srcip = params.get("srcip")
            dstip = params.get("dstip")
            action = params.get("action")
            policyid = params.get("policyid")
            logs = fg.get_traffic_logs(
                source=self._log_source(),
                srcip=srcip,
                dstip=dstip,
                action=action,
                policyid=policyid,
            )
            return logs

        elif tool_name == "get_policy_stats":
            stats = fg.get_policy_stats()
            return stats

        elif tool_name == "get_vpn_tunnels":
            tunnels = fg.get_vpn_tunnels()
            return tunnels

        elif tool_name == "get_system_status":
            status = fg.get_system_status()
            return status

        elif tool_name == "system_health_check":
            return self._build_health_check(fg)

        elif tool_name == "get_admin_logs":
            rows = params.get("rows") or 50
            return fg.get_admin_logs(rows=int(rows), source=self._log_source())

        elif tool_name == "get_system_logs":
            rows = params.get("rows") or 50
            severity = params.get("severity")
            return fg.get_system_logs(
                rows=int(rows), severity=severity, source=self._log_source()
            )

        elif tool_name == "get_interface_stats":
            return fg.get_interface_stats()

        elif tool_name == "list_vips":
            vips = fg.list_vips()
            return [
                {
                    "name": v.get("name"),
                    "extip": v.get("extip", ""),
                    "mappedip": [
                        m["range"] if isinstance(m, dict) else m
                        for m in v.get("mappedip", [])
                    ],
                    "extintf": v.get("extintf", ""),
                    "portforward": v.get("portforward", ""),
                    "extport": v.get("extport", ""),
                    "mappedport": v.get("mappedport", ""),
                }
                for v in vips
            ]

        elif tool_name == "list_static_routes":
            routes = fg.list_static_routes()
            return [
                {
                    "seq_num": r.get("seq-num"),
                    "dst": r.get("dst", ""),
                    "gateway": r.get("gateway", ""),
                    "device": r.get("device", ""),
                    "distance": r.get("distance"),
                    "status": r.get("status"),
                    "comment": r.get("comment", ""),
                }
                for r in routes
            ]

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _build_health_check(self, fg) -> dict:
        """
        Build an interpreted system health summary from system status +
        resource usage + interface stats, with simple OK/WARN flags so the
        model can reason about resource pressure without parsing raw counters.
        """
        status = fg.get_system_status()

        # CPU / memory / disk come from the resource-usage endpoint, NOT from
        # system status (which only carries serial/version/hostname/uptime).
        try:
            usage = fg.get_resource_usage()
        except Exception:
            usage = {}

        def _pct(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _current(metric: str):
            """Extract the latest sample for a resource metric from usage data."""
            v = usage.get(metric)
            if isinstance(v, list) and v:
                v = v[0]
            if isinstance(v, dict):
                return _pct(v.get("current"))
            return _pct(v)

        cpu = _current("cpu")
        mem = _current("mem")
        # FortiOS reports memory as "mem" and disk as "disk"; fall back to
        # alternate field names seen on some versions.
        if mem is None:
            mem = _current("memory")
        disk = _current("disk")

        def _flag(value, warn, crit):
            if value is None:
                return "unknown"
            if value >= crit:
                return "CRITICAL"
            if value >= warn:
                return "WARN"
            return "OK"

        # Interface up/down summary (best effort — names/fields vary by model).
        interfaces_up = interfaces_down = 0
        try:
            for iface in fg.get_interface_stats():
                link = str(iface.get("link", iface.get("status", ""))).lower()
                if link in ("up", "1", "true"):
                    interfaces_up += 1
                elif link in ("down", "0", "false"):
                    interfaces_down += 1
        except Exception:
            pass

        return {
            "hostname": status.get("hostname"),
            "serial": status.get("serial"),
            "version": status.get("version"),
            "uptime": status.get("uptime"),
            "resources": {
                "cpu_percent": cpu,
                "cpu_status": _flag(cpu, 70, 90),
                "memory_percent": mem,
                "memory_status": _flag(mem, 70, 90),
                "disk_percent": disk,
                "disk_status": _flag(disk, 80, 95),
            },
            "interfaces": {
                "up": interfaces_up,
                "down": interfaces_down,
            },
        }

    def _policy_summary(self, p: dict) -> dict:
        """Format policy as summary."""
        return {
            "id": p.get("policyid"),
            "name": p.get("name"),
            "srcintf": [i["name"] if isinstance(i, dict) else i for i in p.get("srcintf", [])],
            "dstintf": [i["name"] if isinstance(i, dict) else i for i in p.get("dstintf", [])],
            "srcaddr": [a["name"] if isinstance(a, dict) else a for a in p.get("srcaddr", [])],
            "dstaddr": [a["name"] if isinstance(a, dict) else a for a in p.get("dstaddr", [])],
            "service": [s["name"] if isinstance(s, dict) else s for s in p.get("service", [])],
            "action": p.get("action"),
            "status": p.get("status"),
            "comments": p.get("comments", ""),
        }

    # Public methods for LangChain tools
    def list_policies(self) -> str:
        """List all firewall policies."""
        result = self._call_tool("list_policies")
        return self._format(result)

    def get_policy(self, policy_id: int) -> str:
        """Get details of a specific policy."""
        result = self._call_tool("get_policy", policy_id=policy_id)
        return self._format(result)

    def list_addresses(self) -> str:
        """List addresses and address groups."""
        result = self._call_tool("list_addresses")
        return self._format(result)

    def list_services(self) -> str:
        """List services and service groups."""
        result = self._call_tool("list_services")
        return self._format(result)

    def list_interfaces(self) -> str:
        """List network interfaces."""
        result = self._call_tool("list_interfaces")
        return self._format(result)

    def get_traffic_logs(
        self, srcip: str = None, dstip: str = None, action: str = None, policyid: int = None
    ) -> str:
        """Get traffic logs with optional filters."""
        result = self._call_tool(
            "get_traffic_logs", srcip=srcip, dstip=dstip, action=action, policyid=policyid
        )
        return self._format(result)

    def get_policy_stats(self) -> str:
        """Get per-policy statistics."""
        result = self._call_tool("get_policy_stats")
        return self._format(result)

    def get_vpn_tunnels(self) -> str:
        """Get VPN tunnel status."""
        result = self._call_tool("get_vpn_tunnels")
        return self._format(result)

    def get_system_status(self) -> str:
        """Get system health and status."""
        result = self._call_tool("get_system_status")
        return self._format(result)

    def system_health_check(self) -> str:
        """Get an interpreted health summary (CPU/memory/disk + interface up/down)."""
        result = self._call_tool("system_health_check")
        return self._format(result)

    def get_admin_logs(self, rows: int = 50) -> str:
        """Get admin activity logs: logins and configuration changes (recent changes)."""
        result = self._call_tool("get_admin_logs", rows=rows)
        return self._format(result)

    def get_system_logs(self, rows: int = 50, severity: str = None) -> str:
        """Get system event logs, optionally filtered by severity."""
        result = self._call_tool("get_system_logs", rows=rows, severity=severity)
        return self._format(result)

    def get_interface_stats(self) -> str:
        """Get per-interface statistics: packets, bytes, errors."""
        result = self._call_tool("get_interface_stats")
        return self._format(result)

    def list_vips(self) -> str:
        """List virtual IPs (port forwarding / NAT mappings)."""
        result = self._call_tool("list_vips")
        return self._format(result)

    def list_static_routes(self) -> str:
        """List configured static routes."""
        result = self._call_tool("list_static_routes")
        return self._format(result)
