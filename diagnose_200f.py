"""
Diagnostic probe for a FortiGate (built for a 200F / FortiOS 7.6, no VDOM).

Run on a machine that can reach the firewall:
    python diagnose_200f.py

For each endpoint it prints the raw HTTP status and what came back, so you can
tell apart:
    HTTP 403            -> API admin access profile lacks read permission
    HTTP 200, empty     -> endpoint reachable but no data (scope/shape/none)
    HTTP 200, has data  -> works
"""

import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

HOST = os.environ.get("FORTIGATE_HOST", "192.168.1.1")
TOKEN = os.environ.get("FORTIGATE_TOKEN", "")
VDOM = os.environ.get("FORTIGATE_VDOM", "root")
VERIFY = os.environ.get("FORTIGATE_VERIFY_SSL", "false").lower() == "true"
BASE = f"https://{HOST}/api/v2"

client = httpx.Client(
    headers={"Authorization": f"Bearer {TOKEN}"}, verify=VERIFY, timeout=15.0
)


def probe(label, path, params=None):
    p = {"vdom": VDOM}
    if params:
        p.update(params)
    try:
        r = client.get(f"{BASE}{path}", params=p)
    except Exception as e:
        print(f"[{label:24}] CONNECT-ERROR  {type(e).__name__}: {e}")
        return
    status = r.status_code
    body = ""
    try:
        data = r.json()
        results = data.get("results")
        if results is None:
            shape = "no 'results' key"
        elif isinstance(results, list):
            shape = f"list, {len(results)} item(s)"
        elif isinstance(results, dict):
            shape = f"dict, {len(results)} key(s)"
        else:
            shape = f"{type(results).__name__}"
        # FortiOS often echoes the access scope it used:
        scope = data.get("vdom", "")
        body = f"results={shape}  vdom={scope}"
    except Exception:
        body = f"(non-JSON, {len(r.text)} bytes) {r.text[:80]!r}"
    flag = "OK  " if status == 200 and "0 item" not in body and "no 'results'" not in body else "EMPTY/ERR"
    print(f"[{label:24}] HTTP {status}  {flag}  {body}")


print("=" * 78)
print(f"FortiGate diagnostic  host={HOST}  vdom={VDOM}  verify_ssl={VERIFY}")
print("=" * 78)

# First: confirm identity / version / whether VDOM mode is on.
try:
    r = client.get(f"{BASE}/monitor/system/status", params={"vdom": VDOM})
    d = r.json().get("results", {})
    if isinstance(d, list) and d:
        d = d[0]
    print(f"version={d.get('version')}  hostname={d.get('hostname')}  "
          f"serial={d.get('serial')}  vdom_mode={d.get('vdom')}")
except Exception as e:
    print("system/status check failed:", e)
print("-" * 78)

# cmdb (config) endpoints — these honor the access profile per feature area.
probe("firewall policy", "/cmdb/firewall/policy/")
probe("firewall address", "/cmdb/firewall/address/")
probe("firewall vip", "/cmdb/firewall/vip/")
probe("router static", "/cmdb/router/static/")
probe("system interface(cmdb)", "/cmdb/system/interface/")

# monitor endpoints — some may be global-scope on certain builds.
probe("system status", "/monitor/system/status")
probe("resource usage", "/monitor/system/resource/usage")
probe("resource usage(global)", "/monitor/system/resource/usage", {"scope": "global"})
probe("interface stats", "/monitor/system/interface")
probe("policy stats", "/monitor/firewall/policy/")
probe("vpn ipsec", "/monitor/vpn/ipsec")

# log endpoints — depend on where logs are stored.
probe("log traffic disk", "/log/disk/traffic/forward", {"rows": 5})
probe("log traffic memory", "/log/memory/traffic/forward", {"rows": 5})
probe("log admin disk", "/log/disk/event/system", {"rows": 5})

print("-" * 78)
print("Read the FLAG column:")
print("  HTTP 403            -> access profile lacks read perm for that feature")
print("  HTTP 200 + 0 items  -> reachable but empty (scope/shape/nothing configured)")
print("  HTTP 200 + N items  -> works")
