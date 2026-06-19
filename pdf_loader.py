"""
PDF Documentation loader for FortiGate technical documentation.
Loads and chunks PDF docs for use in LangChain RAG pipelines.
"""

from pathlib import Path
from typing import Optional, List
import json


class PDFDocumentationLoader:
    """Load and parse PDF documentation for FortiGate firewall."""

    def __init__(self, pdf_path: Optional[str] = None):
        """
        Initialize loader with optional PDF path.
        If no path provided, creates sample documentation.
        """
        self.pdf_path = pdf_path
        self.chunks = []

    def load_pdf(self) -> str:
        """Load PDF documentation."""
        if not self.pdf_path or not Path(self.pdf_path).exists():
            return self._get_default_documentation()

        try:
            from pypdf import PdfReader

            reader = PdfReader(self.pdf_path)
            text = "\n".join(page.extract_text() for page in reader.pages)
            self.chunks = self._chunk_text(text)
            return text
        except ImportError:
            print("pypdf not installed, using default documentation")
            return self._get_default_documentation()

    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Split text into overlapping chunks."""
        chunks = []
        for i in range(0, len(text), chunk_size - overlap):
            chunks.append(text[i : i + chunk_size])
        return chunks

    def _get_default_documentation(self) -> str:
        """
        Return sample FortiGate documentation for demo purposes.
        Replace with actual PDF path for production use.
        """
        return """
# FortiGate Firewall Configuration Guide

## Policy Management

### Policy Creation Best Practices
1. Always define source and destination zones
2. Specify explicit services rather than "ALL"
3. Use address groups for multiple IPs
4. Apply UTM profiles for security
5. Document purpose in policy comments

### Policy Decision Logic
FortiGate evaluates policies in order:
1. Interface matching
2. Source address matching
3. Destination address matching
4. Service/protocol matching
5. Time-based rules (if configured)

The FIRST matching policy is applied.

### Policy Status Codes
- enable: Policy is active
- disable: Policy is inactive (bypassed)
- Policies in disable state are not evaluated

### Common Policy Issues

#### Traffic Denied
Common causes:
- Source IP not in srcaddr objects
- Service not in service objects
- Wrong interface specified
- Policy is disabled
- Firewall session limit reached
- Implicit deny at end of policy chain

#### Solution Steps
1. Check policy list for matching rules
2. Verify source/dest addresses are correct
3. Confirm services match traffic
4. Check interface assignments
5. Review logs: get_traffic_logs(action="deny")

## Address Objects

### Address Types
- ipmask: Single IP or CIDR range
- iprange: IP range (10.0.0.1-10.0.0.255)
- fqdn: Domain name (resolved at sync interval)
- dynamic: Dynamic address groups

### Address Groups
- Container for multiple address objects
- Can include other groups
- Useful for bulk policy management
- Example: "Internal-Networks" group

## Service Objects

### Built-in Services
- HTTP/HTTPS (ports 80, 443)
- SSH (port 22)
- SMTP/POP3 (ports 25, 110)
- DNS (port 53)
- ALL (wildcard - not recommended)

### Custom Services
Define when built-in services don't match:
- Specify protocol (TCP/UDP)
- Set port ranges
- Can define multiple ports per service

## Interface Configuration

### Interface Types
- Physical: Actual ports (port1, port2)
- Virtual: Logical (vlan1, loopback)
- Aggregate: LAG (port1-2)
- Redundant: Active/passive failover

### VLAN Configuration
- Tag traffic on physical port
- Configure sub-interface with VLAN ID
- Assign IP to VLAN interface
- Reference in policy srcintf/dstintf

## Traffic Logs

### Log Fields
- srcip: Source IP address
- dstip: Destination IP address
- srcport: Source port
- dstport: Destination port
- service: Service name/port
- policyid: Matching policy ID
- action: accept/deny/implicitdeny
- bytes: Traffic volume
- packets: Packet count
- app: Application detected
- appcat: Application category

### Filtering Traffic Logs
```
get_traffic_logs(srcip="10.0.0.1")  # Single source
get_traffic_logs(action="deny")      # Denied traffic only
get_traffic_logs(policyid=5)         # Specific policy
```

### Log Sources
- disk: Persistent storage (default)
- memory: Volatile log buffer
- forticloud: Cloud logging (if enabled)

## VPN Configuration

### IPsec Tunnel Status
- up: Tunnel active
- down: Tunnel inactive
- Indicated in monitor data

### VPN Phase 1 Settings
- IKE version (v1 or v2)
- Encryption algorithm
- Hash algorithm
- DH group
- Lifetime

### VPN Phase 2 Settings
- Encapsulation (IPsec tunnel mode)
- Protocol (ESP)
- Encryption algorithm
- Hash algorithm
- Lifetime

## System Health

### Key Metrics
- CPU usage: Should be <80% sustained
- Memory: Monitor for leaks
- Disk: Ensure >20% free space
- Uptime: Useful for troubleshooting reboots
- Firmware version: Keep current

### Session Limits
- Max sessions: Firewall resource limit
- When reached: New connections dropped
- Monitor via get_firewall_sessions()

## Performance Tuning

### Firewall Acceleration
- Enable NP acceleration for throughput
- Use session helpers for complex protocols
- Offload encryption if available

### Policy Optimization
- Place frequently-matched policies first
- Use implicit deny (more efficient)
- Minimize service "ANY"

## Security Best Practices

### Policy Design
1. Default deny (implicit deny at end)
2. Allow only needed traffic
3. Use address groups for scalability
4. Regularly audit policies
5. Document all policies

### Logging Configuration
- Enable traffic logs for important policies
- Log denied traffic for forensics
- Archive logs regularly
- Set appropriate retention

### Updates
- Apply security patches promptly
- Test in lab before production
- Plan maintenance windows
- Keep firmware current

## Troubleshooting Checklist

For denied traffic:
- [ ] Policy enabled (status=enable)?
- [ ] Source IP in srcaddr?
- [ ] Dest IP in dstaddr?
- [ ] Service in service list?
- [ ] Correct interfaces (srcintf/dstintf)?
- [ ] Any other policies matching first?
- [ ] Session limit exceeded?
- [ ] Time-based rules blocking?

For VPN issues:
- [ ] Phase 1 tunnel up?
- [ ] Encryption/hash algorithms matching?
- [ ] DH groups compatible?
- [ ] Firewall rules allowing encrypted traffic?
- [ ] NAT not interfering?

For performance:
- [ ] CPU usage high?
- [ ] Session table full?
- [ ] Link saturated?
- [ ] NP acceleration enabled?
- [ ] Unnecessary traffic filtered?
"""

    def get_section(self, section_name: str) -> str:
        """Get specific documentation section."""
        full_doc = self.load_pdf()
        if f"## {section_name}" in full_doc:
            start = full_doc.find(f"## {section_name}")
            end = full_doc.find("## ", start + 1)
            return full_doc[start:end] if end > start else full_doc[start:]
        return ""

    def search_documentation(self, keyword: str) -> List[str]:
        """Search documentation for keyword."""
        full_doc = self.load_pdf()
        results = []
        for chunk in full_doc.split("\n"):
            if keyword.lower() in chunk.lower():
                results.append(chunk)
        return results


# Curated, real Fortinet documentation URLs (FortiOS 7.6). Only these links
# may be cited in answers — the model must NOT invent any other URL.
OFFICIAL_DOC_LINKS = {
    "FortiGate docs home": "https://docs.fortinet.com/product/fortigate",
    "Administration Guide": "https://docs.fortinet.com/document/fortigate/7.6.0/administration-guide",
    "Best Practices": "https://docs.fortinet.com/document/fortigate/7.6.0/best-practices",
    "FortiOS REST API": "https://docs.fortinet.com/document/fortigate/7.6.0/fortios-rest-api",
    "CLI Reference": "https://docs.fortinet.com/document/fortigate/7.6.0/cli-reference",
    "Hardware (FortiGate 200F)": "https://docs.fortinet.com/product/fortigate/hardware",
    "Fortinet Community / KB": "https://community.fortinet.com",
}


def _reference_links_block() -> str:
    lines = ["=== Reference Links (cite ONLY these exact URLs; never invent links) ==="]
    for name, url in OFFICIAL_DOC_LINKS.items():
        lines.append(f"- {name}: {url}")
    return "\n".join(lines)


def create_documentation_context(pdf_path: Optional[str] = None) -> str:
    """Create formatted documentation context for LangChain."""
    loader = PDFDocumentationLoader(pdf_path)
    doc_text = loader.load_pdf()
    return f"""
=== Official FortiGate Documentation ===

{doc_text}

{_reference_links_block()}

=== Usage Guidelines ===
When answering questions about FortiGate configuration:
1. Reference specific sections from documentation
2. Cite section titles
3. Note any compatibility requirements
4. Warn about deprecated features
"""
