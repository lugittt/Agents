import httpx
from typing import Optional


class FortiGateClient:
    def __init__(self, host: str, api_token: str, vdom: str = "root", verify_ssl: bool = False):
        self.base_url = f"https://{host}/api/v2"
        self.vdom = vdom
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {api_token}"},
            verify=verify_ssl,
            timeout=30.0,
        )

    def _params(self, extra: Optional[dict] = None) -> dict:
        p = {"vdom": self.vdom}
        if extra:
            p.update(extra)
        return p

    def _check(self, response: httpx.Response) -> dict:
        response.raise_for_status()
        return response.json()

    # --- Firewall policies ---

    def list_policies(self) -> list:
        return self._check(
            self.client.get(f"{self.base_url}/cmdb/firewall/policy/", params=self._params())
        )["results"]

    def get_policy(self, policy_id: int) -> dict:
        return self._check(
            self.client.get(f"{self.base_url}/cmdb/firewall/policy/{policy_id}", params=self._params())
        )["results"][0]

    def create_policy(self, data: dict) -> dict:
        return self._check(
            self.client.post(f"{self.base_url}/cmdb/firewall/policy/", json=data, params=self._params())
        )

    def update_policy(self, policy_id: int, data: dict) -> dict:
        return self._check(
            self.client.put(f"{self.base_url}/cmdb/firewall/policy/{policy_id}", json=data, params=self._params())
        )

    def delete_policy(self, policy_id: int) -> dict:
        return self._check(
            self.client.delete(f"{self.base_url}/cmdb/firewall/policy/{policy_id}", params=self._params())
        )

    def move_policy(self, policy_id: int, position: str, neighbor_id: int) -> dict:
        # position must be "before" or "after"
        return self._check(
            self.client.put(
                f"{self.base_url}/cmdb/firewall/policy/{policy_id}",
                params=self._params({"action": "move", position: neighbor_id}),
            )
        )

    # --- Reference objects (read-only) ---

    def list_addresses(self) -> list:
        return self._check(
            self.client.get(f"{self.base_url}/cmdb/firewall/address/", params=self._params())
        )["results"]

    def list_address_groups(self) -> list:
        return self._check(
            self.client.get(f"{self.base_url}/cmdb/firewall/addrgrp/", params=self._params())
        )["results"]

    def list_services(self) -> list:
        custom = self._check(
            self.client.get(f"{self.base_url}/cmdb/firewall/service/custom/", params=self._params())
        )["results"]
        groups = self._check(
            self.client.get(f"{self.base_url}/cmdb/firewall/service/group/", params=self._params())
        )["results"]
        return custom + groups

    def list_interfaces(self) -> list:
        return self._check(
            self.client.get(f"{self.base_url}/cmdb/system/interface/", params=self._params())
        )["results"]

    def list_vips(self) -> list:
        return self._check(
            self.client.get(f"{self.base_url}/cmdb/firewall/vip/", params=self._params())
        )["results"]

    def list_static_routes(self) -> list:
        return self._check(
            self.client.get(f"{self.base_url}/cmdb/router/static/", params=self._params())
        )["results"]

    # --- Logs & monitoring ---

    # Tried in order when no explicit log source is given. Different FortiGate
    # configs store logs in different places (diskless models log to memory,
    # others forward to FortiCloud), so we probe until one returns data.
    LOG_SOURCES = ("disk", "memory", "forticloud")

    def _read_log(self, suffix: str, extra: dict, source: Optional[str] = None) -> list:
        """
        Read a log endpoint, falling back across log sources.

        suffix: path after the source segment, e.g. "traffic/forward".
        source: if given, only that source is tried; otherwise LOG_SOURCES
                are tried in order and the first non-empty result is returned.
        """
        sources = [source] if source else list(self.LOG_SOURCES)
        for src in sources:
            try:
                data = self._check(
                    self.client.get(
                        f"{self.base_url}/log/{src}/{suffix}",
                        params=self._params(extra),
                    )
                )
            except httpx.HTTPStatusError:
                # This source isn't available on this device — try the next.
                continue
            results = data.get("results", [])
            if results:
                return results
        return []

    def get_traffic_logs(
        self,
        source: Optional[str] = None,
        log_type: str = "forward",
        rows: int = 50,
        srcip: Optional[str] = None,
        dstip: Optional[str] = None,
        action: Optional[str] = None,
        policyid: Optional[int] = None,
    ) -> list:
        """Read traffic logs. source: disk|memory|forticloud (None = auto fallback). log_type: forward|local|multicast."""
        extra: dict = {"rows": rows}
        if srcip:
            extra["srcip"] = srcip
        if dstip:
            extra["dstip"] = dstip
        if action:
            extra["action"] = action
        if policyid is not None:
            extra["policyid"] = policyid
        return self._read_log(f"traffic/{log_type}", extra, source=source)

    def get_policy_stats(self) -> list:
        """Return per-policy packet/byte hit counters from the monitor API."""
        data = self._check(
            self.client.get(
                f"{self.base_url}/monitor/firewall/policy/",
                params=self._params(),
            )
        )
        return data.get("results", [])

    def get_vpn_tunnels(self) -> list:
        """Return IPsec VPN tunnel status (phase1/phase2 state, traffic counters) from the monitor API."""
        data = self._check(
            self.client.get(
                f"{self.base_url}/monitor/vpn/ipsec",
                params=self._params(),
            )
        )
        return data.get("results", [])

    def get_system_logs(
        self, rows: int = 50, severity: Optional[str] = None, source: Optional[str] = None
    ) -> list:
        """Read system event logs. severity: critical|alert|error|warning|notice|info|debug."""
        extra: dict = {"rows": rows}
        if severity:
            extra["severity"] = severity
        return self._read_log("system/event", extra, source=source)

    def get_admin_logs(self, rows: int = 50, source: Optional[str] = None) -> list:
        """Read admin activity logs (logins, config changes, etc.)."""
        return self._read_log("admin/login", {"rows": rows}, source=source)

    def get_system_status(self) -> dict:
        """Return system status: CPU, memory, disk, uptime, serial number, firmware version."""
        data = self._check(
            self.client.get(
                f"{self.base_url}/monitor/system/status",
                params=self._params(),
            )
        )
        results = data.get("results")
        if results and isinstance(results, list) and len(results) > 0:
            return results[0] if isinstance(results[0], dict) else {}
        elif isinstance(results, dict):
            return results
        return {}

    def get_resource_usage(self) -> dict:
        """
        Return live CPU / memory / disk / session usage from the monitor API.

        These metrics live at /monitor/system/resource/usage, NOT in
        /monitor/system/status. The response shape is:
            {"results": {"cpu": [{"current": N}], "mem": [...], "disk": [...]}}
        """
        data = self._check(
            self.client.get(
                f"{self.base_url}/monitor/system/resource/usage",
                params=self._params(),
            )
        )
        results = data.get("results")
        return results if isinstance(results, dict) else {}

    def get_interface_stats(self) -> list:
        """Return per-interface statistics: packets, bytes, errors, collisions."""
        data = self._check(
            self.client.get(
                f"{self.base_url}/monitor/system/interface",
                params=self._params(),
            )
        )
        results = data.get("results", [])
        if isinstance(results, str):
            return []
        return results if isinstance(results, list) else []
