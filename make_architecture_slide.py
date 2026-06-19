"""
Generate a one-page PowerPoint slide describing the application architecture.

Run:  python make_architecture_slide.py
Output: ARCHITECTURE.pptx
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn

# --- palette ---------------------------------------------------------------
INK = RGBColor(0x1F, 0x2A, 0x37)        # dark text
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
USER = RGBColor(0x55, 0x5F, 0x6B)       # grey
ORCH = RGBColor(0x7C, 0x3A, 0xED)       # purple (orchestrator)
OLLAMA = RGBColor(0x16, 0xA3, 0x4A)     # green
WRAP = RGBColor(0x25, 0x63, 0xEB)       # blue
CLIENT = RGBColor(0x0E, 0x94, 0x88)     # teal
FGT = RGBColor(0xDC, 0x2A, 0x26)        # red (FortiGate brand-ish)
DOCS = RGBColor(0xCA, 0x8A, 0x04)       # gold (documentation)
CONF = RGBColor(0x6B, 0x72, 0x80)       # slate (config)
LINE = RGBColor(0x94, 0xA3, 0xB8)       # arrow grey

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank


def box(x, y, w, h, fill, title, subtitle="", title_sz=14, sub_sz=10,
        fg=WHITE, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    sp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    sp.line.color.rgb = fill
    sp.shadow.inherit = False
    tf = sp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_top = Pt(2)
    tf.margin_bottom = Pt(2)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = title
    r.font.bold = True
    r.font.size = Pt(title_sz)
    r.font.color.rgb = fg
    if subtitle:
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = subtitle
        r2.font.size = Pt(sub_sz)
        r2.font.color.rgb = fg
    return sp


def arrow(x1, y1, x2, y2, label="", color=LINE, width=2.25, dash=False,
          double=False):
    cn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                    Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    cn.line.color.rgb = color
    cn.line.width = Pt(width)
    le = cn.line._get_or_add_ln()
    tail = le.makeelement(qn('a:tailEnd'), {'type': 'triangle'})
    le.append(tail)
    if double:
        head = le.makeelement(qn('a:headEnd'), {'type': 'triangle'})
        le.append(head)
    if dash:
        d = le.makeelement(qn('a:prstDash'), {'val': 'dash'})
        le.append(d)
    if label:
        lx, ly = (x1 + x2) / 2 - 0.9, (y1 + y2) / 2 - 0.28
        tb = slide.shapes.add_textbox(Inches(lx), Inches(ly), Inches(1.8), Inches(0.3))
        tp = tb.text_frame.paragraphs[0]
        tp.alignment = PP_ALIGN.CENTER
        rr = tp.add_run()
        rr.text = label
        rr.font.size = Pt(8.5)
        rr.font.italic = True
        rr.font.color.rgb = INK
    return cn


# --- title -----------------------------------------------------------------
t = slide.shapes.add_textbox(Inches(0.4), Inches(0.18), Inches(12.5), Inches(0.9))
tp = t.text_frame.paragraphs[0]
r = tp.add_run()
r.text = "FortiGate Firewall AI Agent — Architecture"
r.font.size = Pt(28)
r.font.bold = True
r.font.color.rgb = ORCH
sub = t.text_frame.add_paragraph()
rs = sub.add_run()
rs.text = "Local, privacy-preserving LLM assistant: live FortiGate data + built-in docs, all on your machine (no cloud keys)."
rs.font.size = Pt(12)
rs.font.color.rgb = INK

# --- nodes -----------------------------------------------------------------
ROW = 3.05      # main pipeline y
H = 1.05
# Ollama (top, above orchestrator)
box(2.55, 1.35, 2.55, 0.9, OLLAMA, "Ollama  (local LLM)",
    "OLLAMA_BASE_URL · reasons + emits TOOL: calls", sub_sz=9)
# pipeline
box(0.45, ROW, 1.75, H, USER, "USER", "terminal Q & A")
box(2.55, ROW, 2.55, H, ORCH, "langchain_firewall_agent.py",
    "Orchestrator · prompt + tool loop", sub_sz=9)
box(5.45, ROW, 2.35, H, WRAP, "fortigate_api_wrapper.py",
    "Adapter · maps tools, formats", sub_sz=9)
box(8.10, ROW, 2.05, H, CLIENT, "fortigate.py",
    "REST client (httpx)", sub_sz=9)
box(10.45, ROW, 2.45, H, FGT, "FortiGate firewall",
    "FortiOS /api/v2", sub_sz=9)
# documentation (below orchestrator)
box(2.55, 4.75, 2.55, 0.9, DOCS, "pdf_loader.py",
    "Built-in documentation → prompt context", sub_sz=9)
# config (.env) feeding wrapper
box(5.45, 4.75, 2.35, 0.9, CONF, ".env  (config)",
    "host · token · VDOM · log source", sub_sz=9)

# --- arrows ----------------------------------------------------------------
midL = ROW + H / 2
arrow(2.20, midL, 2.55, midL, double=True)                       # user <-> orch
arrow(3.82, ROW, 3.82, 2.25, label="prompt / answer", double=True)  # orch <-> ollama
arrow(5.10, midL, 5.45, midL, label="TOOL: call")               # orch -> wrapper
arrow(7.80, midL, 8.10, midL, label="method")                   # wrapper -> client
arrow(10.15, midL, 10.45, midL, label="HTTPS + token")          # client -> fgt
arrow(3.82, 4.75, 3.82, ROW + H, label="docs context", color=DOCS, dash=True)  # docs -> orch
arrow(6.62, 4.75, 6.62, ROW + H, label="config", color=CONF, dash=True)        # .env -> wrapper

# --- flow strip (bottom) ---------------------------------------------------
flow = slide.shapes.add_textbox(Inches(0.45), Inches(5.95), Inches(12.45), Inches(0.5))
fp = flow.text_frame.paragraphs[0]
fr = fp.add_run()
fr.text = ("Traffic flow:  Question → prompt (system + docs) → LLM emits "
           "TOOL: call → wrapper → client → HTTPS to FortiGate → JSON back "
           "→ results accumulate, LLM re-prompted (≤3×) → answer + Recommendation + [PDF] indicator")
fr.font.size = Pt(10.5)
fr.font.bold = True
fr.font.color.rgb = INK

# --- key points ------------------------------------------------------------
kp = slide.shapes.add_textbox(Inches(0.45), Inches(6.45), Inches(12.45), Inches(0.95))
tf = kp.text_frame
tf.word_wrap = True
points = [
    "Text-based tool protocol (model prints TOOL: name(args), parsed by regex) — keeps it model-agnostic.",
    "Context accumulates across iterations; errors are surfaced (HTTP 403/404), not swallowed.",
    "Log tools auto-fall-back disk → memory → forticloud; everything configurable via .env (incl. Ollama URL).",
]
for i, txt in enumerate(points):
    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
    rb = p.add_run()
    rb.text = "•  " + txt
    rb.font.size = Pt(10)
    rb.font.color.rgb = INK

prs.save("ARCHITECTURE.pptx")
print("Saved ARCHITECTURE.pptx")
