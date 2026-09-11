"""Build the diagram-only planning companion; this is documentation tooling.

Run: python tools/build_visual_guide.py
Requires reportlab. Does not install or exercise the planned Jarvis application.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import reportlab
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/pdf/jarvis-memory-visual-guide.pdf"
QA = ROOT / "tmp/pdfs"
W, H = 1440, 960
BASE = "https://github.com/harshith0518/ProjectSemanticMemoryJarvis/blob/main/"
INK = "#23364B"
MUTED = "#586B80"
PAPER = "#F7F9FC"
LINE = "#74859B"
COLORS = {
    "user": ("#344D68", "#EDF1F6"),
    "data": ("#2668B8", "#EDF4FD"),
    "code": ("#087C7A", "#EAF7F5"),
    "model": ("#7550B9", "#F2EDFC"),
    "decision": ("#A76600", "#FFF4D9"),
    "risk": ("#B7444E", "#FFF0F0"),
    "ready": ("#28744E", "#EAF6EF"),
}
STATUS = {
    "PROPOSED": "decision",
    "OPTIONAL": "model",
    "OPEN": "decision",
    "VERIFIED": "ready",
    "UNTESTED": "risk",
    "DECIDED": "data",
    "REFERENCE": "user",
}


def fonts():
    win = Path("C:/Windows/Fonts")
    fallback = Path(reportlab.__file__).parent / "fonts"
    regular = win / "segoeui.ttf"
    bold = win / "segoeuib.ttf"
    if not regular.exists():
        regular, bold = fallback / "Vera.ttf", fallback / "VeraBd.ttf"
    pdfmetrics.registerFont(TTFont("Guide", str(regular)))
    pdfmetrics.registerFont(TTFont("GuideBold", str(bold)))


def color(value):
    return HexColor(value)


def text(c, value, x, y, size=18, bold=False, fill=INK, align="left"):
    c.setFont("GuideBold" if bold else "Guide", size)
    c.setFillColor(color(fill))
    method = {"left": c.drawString, "center": c.drawCentredString, "right": c.drawRightString}[align]
    method(x, H - y - size * 0.80, value)


def wrap(value, width, size, bold=False):
    font = "GuideBold" if bold else "Guide"
    result = []
    for line in value.split("\n"):
        words = line.split()
        if not words:
            result.append("")
            continue
        current = ""
        for word in words:
            assert pdfmetrics.stringWidth(word, font, size) <= width, (word, width, size)
            trial = (current + " " + word).strip()
            if pdfmetrics.stringWidth(trial, font, size) <= width:
                current = trial
            else:
                result.append(current)
                current = word
        result.append(current)
    return result


@dataclass
class Node:
    key: str
    x: float
    y: float
    w: float
    h: float
    title: str
    body: str = ""
    kind: str = "code"
    shape: str = "round"
    tag: str | None = None
    target: int | None = None
    title_size: float = 22
    body_size: float = 18

    def port(self, side):
        return {
            "L": (self.x, self.y + self.h / 2),
            "R": (self.x + self.w, self.y + self.h / 2),
            "T": (self.x + self.w / 2, self.y),
            "B": (self.x + self.w / 2, self.y + self.h),
        }[side]


@dataclass
class Edge:
    start: str
    end: str
    sp: str = "R"
    ep: str = "L"
    via: list = field(default_factory=list)
    label: str = ""
    at: tuple | None = None
    kind: str = "code"
    dashed: bool = False
    double: bool = False


class Page:
    def __init__(self, number, title, question, ref, tag="PROPOSED"):
        self.number, self.title, self.question, self.ref, self.tag = number, title, question, ref, tag
        self.nodes = {}
        self.edges = []
        self.groups = []
        self.labels = []
        self.fit_report = []

    def n(self, key, x, y, w, h, title, body="", kind="code", shape="round", tag=None,
          target=None, title_size=22, body_size=18):
        assert key not in self.nodes, (self.number, key)
        self.nodes[key] = Node(key, x, y, w, h, title, body, kind, shape, tag, target, title_size, body_size)
        return key

    def e(self, start, end, sp="R", ep="L", via=None, label="", at=None,
          kind="code", dashed=False, double=False):
        self.edges.append(Edge(start, end, sp, ep, via or [], label, at, kind, dashed, double))

    def group(self, x, y, w, h, label, kind="user"):
        self.groups.append((x, y, w, h, label, kind))

    def label(self, x, y, value, size=17, fill=MUTED, bold=False):
        self.labels.append((x, y, value, size, fill, bold))

    def pill(self, c, x, y, value, kind="user"):
        stroke, bg = COLORS[kind]
        width = pdfmetrics.stringWidth(value, "GuideBold", 12) + 22
        c.setFillColor(color(bg))
        c.setStrokeColor(color(stroke))
        c.setLineWidth(0.9)
        c.roundRect(x, H - y - 25, width, 25, 10, fill=1, stroke=1)
        text(c, value, x + width / 2, y + 7, 12, True, stroke, "center")
        return width

    def node(self, c, n):
        assert n.x >= 44 and n.x + n.w <= W - 44, (self.number, n.key, "x bounds")
        assert n.y >= 150 and n.y + n.h <= 872, (self.number, n.key, "y bounds")
        stroke, bg = COLORS[n.kind]
        c.setFillColor(color(bg))
        c.setStrokeColor(color(stroke))
        c.setLineWidth(1.7)
        x, y, w, h = n.x, H - n.y - n.h, n.w, n.h
        inset = 18
        if n.shape == "diamond":
            p = c.beginPath()
            p.moveTo(x + w / 2, y + h)
            p.lineTo(x + w, y + h / 2)
            p.lineTo(x + w / 2, y)
            p.lineTo(x, y + h / 2)
            p.close()
            c.drawPath(p, fill=1, stroke=1)
            inset = w * 0.23
        elif n.shape == "hex":
            d = 22
            p = c.beginPath()
            p.moveTo(x + d, y + h)
            for px, py in [(x + w - d, y + h), (x + w, y + h / 2),
                           (x + w - d, y), (x + d, y), (x, y + h / 2)]:
                p.lineTo(px, py)
            p.close()
            c.drawPath(p, fill=1, stroke=1)
            inset = 28
        elif n.shape == "cylinder":
            c.rect(x, y + 13, w, h - 26, fill=1, stroke=0)
            c.ellipse(x, y, x + w, y + 28, fill=1, stroke=1)
            c.rect(x, y + 14, w, h - 28, fill=1, stroke=0)
            c.line(x, y + 14, x, y + h - 14)
            c.line(x + w, y + 14, x + w, y + h - 14)
            c.ellipse(x, y + h - 28, x + w, y + h, fill=1, stroke=1)
        elif n.shape == "document":
            d = 20
            p = c.beginPath()
            p.moveTo(x, y)
            for px, py in [(x + w, y), (x + w, y + h - d), (x + w - d, y + h), (x, y + h)]:
                p.lineTo(px, py)
            p.close()
            c.drawPath(p, fill=1, stroke=1)
            c.line(x + w - d, y + h, x + w - d, y + h - d)
            c.line(x + w - d, y + h - d, x + w, y + h - d)
        else:
            c.roundRect(x, y, w, h, min(22 if n.shape == "pill" else 12, h / 2), fill=1, stroke=1)
        title_size, body_size = n.title_size, n.body_size
        key_room = 24 if n.shape != "diamond" else 0
        if n.shape == "cylinder":
            key_room = 39
        tag_room = 32 if n.tag else 0
        available = h - key_room - tag_room - 17
        if n.shape == "diamond":
            available = h * 0.61
        while True:
            tw = wrap(n.title, w - 2 * inset, title_size, True)
            bw = wrap(n.body, w - 2 * inset, body_size) if n.body else []
            block = len(tw) * title_size * 1.18 + (11 if bw else 0) + len(bw) * body_size * 1.26
            if block <= available:
                break
            title_size -= 0.5
            body_size -= 0.5
            assert body_size >= 14, (self.number, n.key, n.title, "text overflow")
        cy = n.y + key_room + max(10, (available - block) / 2 + 8)
        if n.shape == "diamond":
            cy = n.y + (h - block) / 2
        if n.shape != "diamond":
            text(c, f"{self.number:02}.{n.key}", x + (31 if n.shape == "hex" else 13), n.y + (23 if n.shape == "cylinder" else 9),
                 11, True, stroke)
        for line in tw:
            text(c, line, x + w / 2, cy, title_size, True, stroke, "center")
            cy += title_size * 1.18
        if bw:
            cy += 11
        for line in bw:
            text(c, line, x + w / 2, cy, body_size, False, INK, "center")
            cy += body_size * 1.26
        if n.tag:
            self.pill(c, x + 12, n.y + h - 31, n.tag, STATUS[n.tag])
        if n.target:
            c.linkRect("", f"P{n.target:02}", (x, y, x + w, y + h), relative=0, thickness=0)
        self.fit_report.append({"id": f"{self.number:02}.{n.key}", "title": n.title,
                                "title_size": title_size, "body_size": body_size})

    def arrow(self, c, edge):
        assert edge.start in self.nodes and edge.end in self.nodes
        start, end = self.nodes[edge.start].port(edge.sp), self.nodes[edge.end].port(edge.ep)
        pts = [start] + list(edge.via) + [end]
        stroke = COLORS[edge.kind][0]
        c.setStrokeColor(color(stroke))
        c.setFillColor(color(stroke))
        c.setLineWidth(2.2)
        c.setDash(7, 5) if edge.dashed else c.setDash()
        p = c.beginPath()
        p.moveTo(pts[0][0], H - pts[0][1])
        for px, py in pts[1:]:
            p.lineTo(px, H - py)
        c.drawPath(p, fill=0, stroke=1)
        c.setDash()
        self.head(c, pts[-2], pts[-1], stroke)
        if edge.double:
            self.head(c, pts[1], pts[0], stroke)

    def head(self, c, start, end, stroke):
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        length, half = 10, 4.7
        bx, by = end[0] - length * math.cos(angle), end[1] - length * math.sin(angle)
        p = c.beginPath()
        p.moveTo(end[0], H - end[1])
        p.lineTo(bx + half * math.sin(angle), H - (by - half * math.cos(angle)))
        p.lineTo(bx - half * math.sin(angle), H - (by + half * math.cos(angle)))
        p.close()
        c.setFillColor(color(stroke))
        c.drawPath(p, fill=1, stroke=0)

    def draw(self, c):
        c.bookmarkPage(f"P{self.number:02}")
        c.addOutlineEntry(f"{self.number:02}  {self.title}", f"P{self.number:02}", level=0)
        c.setFillColor(color(PAPER))
        c.rect(0, 0, W, H, stroke=0, fill=1)
        c.setFillColor(color(INK))
        c.rect(0, H - 9, W, 9, stroke=0, fill=1)
        text(c, "HEY JARVIS  /  MEMORY ATLAS", 54, 28, 14, True, MUTED)
        heading_size = 36
        while pdfmetrics.stringWidth(self.title, "GuideBold", heading_size) > W - 260:
            heading_size -= 0.5
        text(c, self.title, 54, 58, heading_size, True)
        text(c, self.question, 55, 109, 18, False, MUTED)
        text(c, f"{self.number:02}", 1386, 34, 57, True, INK, "right")
        self.pill(c, 1173, 107, self.tag, STATUS[self.tag])
        for x, y, w, h, label, kind in self.groups:
            stroke, bg = COLORS[kind]
            c.setStrokeColor(color(stroke))
            c.setFillColor(color("#FFFFFF"))
            c.setLineWidth(1)
            c.setDash(5, 4)
            c.roundRect(x, H - y - h, w, h, 17, fill=1, stroke=1)
            c.setDash()
            text(c, label, x + 17, y + 13, 14, True, stroke)
        for e in self.edges:
            self.arrow(c, e)
        for n in self.nodes.values():
            self.node(c, n)
        for e in self.edges:
            if e.label:
                if e.at:
                    px, py = e.at
                else:
                    a, b = self.nodes[e.start].port(e.sp), self.nodes[e.end].port(e.ep)
                    px, py = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 13
                width = pdfmetrics.stringWidth(e.label, "GuideBold", 14) + 14
                c.setFillColor(color(PAPER))
                c.roundRect(px - width / 2, H - py - 21, width, 24, 5, stroke=0, fill=1)
                text(c, e.label, px, py + 3, 14, True, COLORS[e.kind][0], "center")
        for x, y, value, size, fill, bold in self.labels:
            text(c, value, x, y, size, bold, fill)
        c.setStrokeColor(color("#D9E1EA"))
        c.setLineWidth(1)
        c.line(54, H - 897, 1386, H - 897)
        text(c, "PLAN SNAPSHOT  11 SEP 2026  |  Product implementation & live evaluation: pending",
             54, 913, 13, False, MUTED)
        ref_label = f"READ: {self.ref}"
        text(c, ref_label, 900, 913, 13, True, COLORS["data"][0])
        c.linkURL(BASE + self.ref.split("#")[0], (895, 22, 1310, 49), relative=0, thickness=0)
        text(c, "MAP", 1346, 913, 13, True, COLORS["data"][0])
        c.linkRect("", "P01", (1336, 22, 1390, 49), relative=0, thickness=0)
        c.showPage()


def row(p, keys, y, titles, bodies=None, kinds=None, shapes=None, h=120, x=54, w=240, gap=42):
    for i, key in enumerate(keys):
        p.n(key, x + i * (w + gap), y, w, h, titles[i],
            (bodies or [""] * len(keys))[i], (kinds or ["code"] * len(keys))[i],
            (shapes or ["round"] * len(keys))[i])
    for a, b in zip(keys, keys[1:]):
        p.e(a, b)


def build_pages():
    pages = []
    p = Page(1, "The whole plan, one visual language", "Follow the arrows. Use a page + node ID when asking a question.", "README.md", "REFERENCE")
    row(p, list("ABCDE"), 166,
        ["User context", "Supported memory", "Relevant evidence", "Useful reply", "User control"],
        ["Messages + dictations", "Facts + scope + sources", "For this request", "Answer / draft + Sources", "Correct / Forget / Private"],
        ["user", "data", "code", "model", "decision"], ["pill", "cylinder", "round", "hex", "round"],
        h=146, w=230, gap=45)
    p.label(55, 322, "COLOR = ROLE", 15, INK, True)
    legend = [("data", "Source / stored evidence", "document"), ("code", "Application code", "round"),
              ("model", "Model proposal", "hex"), ("decision", "Decision / uncertainty", "diamond"),
              ("risk", "Excluded / failure", "round"), ("user", "User / workflow", "pill")]
    for i, (kind, title, shape) in enumerate(legend):
        p.n(f"L{i+1}", 54 + i * 225, 349, 207, 83, title, kind=kind, shape=shape, title_size=17, body_size=15)
    p.label(55, 463, "CLICK A CARD TO JUMP  /  SOLID = FLOW  /  DASHED = OPTIONAL OR CONDITIONAL", 15, INK, True)
    topics = ["Visual map", "Memory meanings", "Shared backend", "Evidence records", "Time + uncertainty",
              "Learning flow", "Update decisions", "Request routing", "Retrieval + ranking", "One useful answer",
              "Model roles + cost", "Private boundary", "Forget propagation", "Concurrency guards",
              "Feedback repair", "Evaluation", "Architecture tradeoffs", "Build + handoff"]
    for i, title in enumerate(topics):
        p.n(f"N{i+1}", 54 + (i % 6) * 225, 502 + (i // 6) * 107, 207, 87,
            f"P{i+1:02}", title, kind="user", target=i+1, title_size=17, body_size=17)
    p.label(55, 846, "STATUS TAGS: DECIDED / PROPOSED / VERIFIED / UNTESTED  |  Color never means 'already built'.", 15)
    pages.append(p)

    p = Page(2, "Semantic and persistent are different axes", "What is remembered?  x  How long is it kept?", "ARCHITECTURE.md")
    p.group(54, 162, 1332, 300, "AXIS 1  /  CONTENT KIND")
    p.n("A", 79, 209, 405, 205, "Semantic", "Reusable facts + scoped preferences\nMira: three-bullet Atlas updates", "data", "document")
    p.n("B", 516, 209, 405, 205, "Episodic", "What was reported to happen\nUser reported sending a checklist", "data", "document")
    p.n("C", 953, 209, 405, 205, "Procedural", "How to carry out a task\nReviewed steps; automatic learning deferred", "model", "document")
    p.group(54, 491, 1332, 244, "AXIS 2  /  LIFETIME")
    p.n("D", 80, 543, 305, 140, "Persistent store", "Survives requests / restart\nCan hold different content kinds", "data", "cylinder")
    p.n("E", 563, 543, 306, 140, "Working context", "Selected evidence + current request\nFits the model input budget", "code")
    p.n("F", 1048, 543, 306, 140, "Model response", "Uses the supplied context\nDoes not update model weights", "model", "hex")
    p.e("D", "E", label="retrieve", at=(473, 599))
    p.e("E", "F", label="prompt", at=(956, 599))
    p.n("G", 80, 775, 605, 83, "Factual memory belongs under semantic memory", kind="data", title_size=21)
    p.n("H", 749, 775, 605, 83, "Saved claim does not mean independently verified", kind="decision", title_size=21)
    pages.append(p)

    p = Page(3, "One backend, several ways to use it", "Every entry point follows the same policy and service logic.", "ARCHITECTURE.md")
    p.group(54, 159, 1332, 483, "PROPOSED APPLICATION  /  LOCAL LOOPBACK REVIEW")
    for k, y, title, body in [("A", 210, "Ordinary-user UI", "Import / Ask / Sources / controls"),
                              ("B", 349, "Typer CLI", "Import / process / inspect / evaluate"),
                              ("C", 488, "Worker + evaluator", "Same application operations")]:
        p.n(k, 80, y, 282, 110, title, body, "user", "pill")
    p.n("D", 426, 209, 227, 111, "FastAPI", "Typed HTTP boundary", "code")
    p.n("E", 717, 344, 265, 143, "Shared services", "Server-owned identity\nMode + evidence policy", "code")
    p.n("F", 1061, 201, 296, 173, "PostgreSQL", "Sources / claims / revisions\nExclusions / jobs / indexes", "data", "cylinder")
    p.n("G", 1061, 445, 296, 154, "Model adapters", "Extractor / responder\nOptional embedder", "model", "hex")
    p.e("A", "D")
    p.e("D", "E", sp="R", ep="T", via=[(682, 264), (849, 264)])
    p.e("B", "E", via=[(536, 404), (536, 415)])
    p.e("C", "E", ep="B", via=[(663, 543), (849, 543)])
    p.e("E", "F", ep="L", via=[(1019, 415), (1019, 287)], label="code owns writes", at=(1123, 395))
    p.e("E", "G", via=[(1021, 415), (1021, 522)], kind="model")
    p.group(54, 672, 865, 192, "COMPOSE STARTUP  /  ONE PYTHON IMAGE")
    row(p, list("HIJ"), 723, ["DB healthy", "Migrate once", "API + worker"],
        kinds=["data", "code", "code"], h=104, x=77, w=247, gap=38)
    p.n("K", 963, 703, 395, 127, "Isolated test database", "Separate credentials + storage\nCannot reach application data", "risk", "cylinder")
    pages.append(p)

    p = Page(4, "A memory needs an evidence trail", "Store meaning, attribution and uncertainty alongside the original source.", "ARCHITECTURE.md")
    p.n("A", 54, 176, 325, 140, "One observation", "dict_0002\nRaw + formatted = one record", "data", "document")
    p.n("B", 521, 176, 348, 140, "Exact source passage", '"Atlas updates to three bullets"\nSource version + checked span', "data", "document")
    p.n("C", 1013, 176, 373, 140, "Derived claim", "Mira / format preference\nAtlas updates / three bullets", "data", "cylinder")
    p.e("A", "B", label="preserve", at=(449, 231))
    p.e("B", "C", label="interpret", at=(942, 231), kind="model")
    fields = [
        ("D", "Identity + ownership", "Whose source? Who said it?\nStable IDs; names are not identity", "data"),
        ("E", "Subject + scope", "Mira + Atlas updates\nNot every recipient or topic", "code"),
        ("F", "Typed meaning", "Predicate + value + units\nNegation + conditions", "code"),
        ("G", "Evidence status", "Reported / tentative / disputed\nModel confidence is not proof", "decision"),
        ("H", "Time", "Capture / import / event / validity\nMissing times stay unknown", "decision"),
        ("I", "Lifecycle + lineage", "Active / superseded / corrected\nSource -> claim -> index", "data"),
    ]
    p.group(54, 359, 1332, 354, "CLAIM REVISION  /  INSPECTABLE FIELDS")
    for i, (key, title, body, kind) in enumerate(fields):
        p.n(key, 79 + (i % 3) * 438, 407 + (i // 3) * 149, 405, 125, title, body, kind, title_size=21, body_size=17)
    p.n("J", 79, 764, 601, 93, "Evidence-backed relations", "Supersedes / contradicts / conditional-on", "data", title_size=21)
    p.n("K", 751, 764, 607, 93, "Search index = derived view", "Keep original evidence; invalidate stale derivatives", "code", title_size=21)
    pages.append(p)

    p = Page(5, "Keep time and certainty separate", "A newer import can describe an older plan.", "ARCHITECTURE.md")
    p.group(54, 161, 1332, 294, "ATLAS  /  TWO OBSERVATIONS, ONE CHANGING PLAN")
    p.n("A", 79, 209, 370, 183, "dict_0001", "Captured: 01 Sep 2026\nReported launch plan: 18 Sep", "data", "document")
    p.n("B", 528, 209, 370, 183, "dict_0003", "Captured: 04 Sep 2026\nMoved to 21 Sep; legal needs time", "data", "document")
    p.n("C", 977, 209, 379, 183, "Use recorded knowledge", "Earlier recorded plan: 18 Sep\nLatest recorded plan: 21 Sep", "code")
    p.e("A", "B", label="change", at=(489, 286))
    p.e("B", "C", label="interpret", at=(938, 286))
    p.label(81, 419, "Launch date is the claim value. Its effective start is separate; unknown stays unknown.", 17, MUTED)
    p.group(54, 487, 637, 229, "EVIDENCE STATUS  /  HOW STRONG IS THE STATEMENT?")
    p.n("D", 78, 538, 588, 133, "Reported / tentative / disputed", "Ravi could own the budget IF Finance signs off\nConditional possibility; no confirmed appointment", "decision", title_size=22)
    p.group(724, 487, 662, 229, "LIFECYCLE  /  HOW MAY THIS VERSION BE USED?")
    p.n("E", 751, 538, 607, 133, "Active / superseded / corrected / excluded", "A tentative claim can still be active\nA superseded claim may answer a historical question", "code", title_size=22)
    p.n("F", 79, 758, 588, 100, "Capture time is not content time", "Orion says 25 Sep; capture time + app are unknown", "risk", title_size=21)
    p.n("G", 751, 758, 607, 100, "Latest import is not latest truth", "Resolve source meaning + scope + relevant time", "decision", title_size=21)
    pages.append(p)

    p = Page(6, "Learning is a guarded pipeline", "A small model interprets eligible input; application code validates and commits.", "ARCHITECTURE.md")
    row(p, list("ABCD"), 178,
        ["Input + mode", "Source eligibility", "Preserve source", "Typed proposal"],
        ["User message / dictation", "Normal? Allowed source?\nPreserve eligible history", "Raw + formatted; stable ID\nSource + job in one transaction", "Claims + spans + scope\nExpected revisions"],
        ["user", "decision", "data", "model"], ["pill", "round", "document", "hex"],
        h=158, w=291, gap=56)
    p.n("E", 1059, 431, 327, 157, "Validate in code", "Schema / ownership / exact span\nExclusions / allowed transition", "code")
    p.n("F", 720, 431, 276, 157, "Useful memory?", "Reconcile: add / support / change\nCorrect / conflict / ignore", "decision")
    p.n("G", 385, 431, 274, 157, "Guarded commit", "Shared policy lock\nRecheck revisions, then write", "code")
    p.n("H", 54, 431, 273, 157, "Build views", "Lexical / optional vectors\nFrom committed state", "data", "cylinder")
    p.e("D", "E", sp="B", ep="T", kind="model")
    p.e("E", "F", sp="L", ep="R")
    p.e("F", "G", sp="L", ep="R")
    p.e("G", "H", sp="L", ep="R")
    p.n("I", 54, 696, 396, 152, "Ineligible / Private", "Skip durable source + jobs\nPrivate uses the temporary reply path", "risk")
    p.n("J", 519, 696, 403, 152, "Invalid model output", "At most one schema-repair retry\nThen expose failure; keep eligible source", "risk")
    p.n("K", 991, 696, 395, 152, "Faithfulness still needs testing", "Valid JSON + real span\nDo not prove a correct interpretation", "decision")
    p.e("B", "I", sp="B", ep="T", via=[(547.5, 374), (28, 374), (28, 669), (252, 669)], kind="risk", dashed=True)
    p.e("E", "J", sp="B", ep="T", via=[(1222.5, 642), (720.5, 642)], kind="risk", dashed=True)
    p.label(387, 623, "Model/network calls run outside the database lock.", 17, MUTED)
    pages.append(p)

    p = Page(7, "The same new sentence can mean different things", "Compare subject, property, scope, source meaning and time before changing memory.", "ARCHITECTURE.md")
    p.n("A", 54, 361, 231, 211, "New evidence", "Compare with related\npermitted claims", "data", "document")
    choices = [
        ("B", "New claim", "No equivalent supported claim", "ADD revision", "code"),
        ("C", "Additional support", "Separate observation; same scoped fact", "LINK evidence", "code"),
        ("D", "World changed", "Atlas plan: 18 -> 21 Sep", "CREATE successor; preserve history", "data"),
        ("E", "Interpretation was wrong", "Ravi recorded as owner; source says 'could'", "CORRECT derived claim; preserve source", "risk"),
        ("F", "Conflict remains", "Same record: INR 15,000 / INR 50,000", "KEEP disputed; ask if needed", "decision"),
        ("G", "Nothing to learn", "Exact reimport / irrelevant / ineligible", "NOOP / idempotent receipt", "user"),
    ]
    for i, (key, title, body, action, kind) in enumerate(choices):
        y = 164 + i * 115
        p.n(key, 389, y, 465, 99, title, body, kind, title_size=21, body_size=17)
        p.n(key+"1", 968, y, 418, 99, action, kind=kind, title_size=20)
        p.e("A", key, via=[(337, 466), (337, y+49.5)], kind=kind)
        p.e(key, key+"1", kind=kind)
    p.label(389, 866, "Same words can be different observations. Similar names do not establish the same person.", 15, MUTED)
    pages.append(p)

    p = Page(8, "Decide whether personal retrieval is needed", "Check mode before accessing any saved personal information.", "ARCHITECTURE.md")
    p.n("A", 54, 361, 222, 120, "Current request", "Server-owned user identity", "user", "pill")
    p.n("B", 358, 315, 237, 206, "Private?", kind="decision", shape="diamond")
    p.n("C", 710, 175, 282, 124, "Temporary context", "Current input + explicit additions\nNo saved personal data", "code")
    p.n("D", 710, 387, 282, 136, "Needs personal history?", "Intent + person/project + time\nResolve follow-up referents", "decision")
    p.n("E", 1087, 175, 299, 124, "Private reply path", "Transient processing\nDiscard on exit; see P12", "model", "hex", target=12)
    p.n("F", 1087, 387, 299, 136, "Retrieve eligible evidence", "Sources + optional claims\nUnclear referent? Clarify", "data", "cylinder", target=9)
    p.n("G", 710, 645, 282, 136, "Self-contained answer", "Skip personal retrieval\nExample: explain binary search", "model", "hex")
    p.n("H", 1087, 645, 299, 136, "Current instruction wins", "Requested format applies now\nNo automatic permanent preference", "code")
    p.e("A", "B")
    p.e("B", "C", sp="T", ep="L", via=[(476.5, 237)], label="yes", at=(588, 220))
    p.e("B", "D", label="no", at=(650, 418))
    p.e("C", "E")
    p.e("D", "F", label="yes", at=(1040, 438))
    p.e("D", "G", sp="B", ep="T", label="no", at=(851, 580))
    p.e("F", "H", sp="B", ep="T")
    p.n("I", 54, 659, 541, 122, "Normal input can be available immediately", "Routine learning may follow asynchronously\nCorrect / Forget use their guarded control paths first", "data", title_size=21, body_size=17)
    pages.append(p)

    p = Page(9, "Retrieve candidates, then rank useful evidence", "Similarity finds candidates; provenance and policy determine usable evidence.", "ARCHITECTURE.md")
    p.n("A", 54, 183, 291, 133, "Eligible search pool", "Source passages\nOptional derived claims", "data", "cylinder")
    p.n("B", 440, 171, 300, 103, "Lexical candidates", "Names + exact terms; PostgreSQL FTS", "data", title_size=21, body_size=16)
    p.n("C", 440, 340, 300, 146, "Exact dense candidates", "Semantic matches; pgvector\nOptional embedding model", "model", tag="OPTIONAL", title_size=21, body_size=16)
    p.n("D", 830, 234, 226, 153, "Union + deduplicate", "Keep hits from either list\nDeduplicate by identity", "code", title_size=21)
    p.n("E", 1150, 234, 236, 153, "Time + conflict", "Current vs historical\nKeep decisive contradictions", "decision", title_size=21, body_size=17)
    p.e("A", "B", via=[(392, 249.5), (392, 222.5)])
    p.e("A", "C", via=[(392, 249.5), (392, 403)], dashed=True, kind="model")
    p.e("B", "D", via=[(786, 222.5), (786, 310.5)])
    p.e("C", "D", via=[(786, 403), (786, 310.5)], dashed=True, kind="model")
    p.e("D", "E")
    p.n("F", 1116, 536, 270, 138, "Rank fusion", "RRF in code\nModel rerank? Recheck access first", "code", body_size=17)
    p.n("G", 758, 536, 272, 138, "Evidence packet", "Complementary sources + claims\nWithin a token budget", "data", "document")
    p.n("H", 403, 536, 271, 138, "Canonical recheck", "Ownership + exclusions + revisions\nBefore model context is released", "code")
    p.n("I", 54, 536, 266, 138, "DeepSeek responder", "Use permitted evidence\nSee worked example P10", "model", "hex", target=10)
    p.e("E", "F", sp="B", ep="T")
    p.e("F", "G", sp="L", ep="R")
    p.e("G", "H", sp="L", ep="R")
    p.e("H", "I", sp="L", ep="R")
    p.n("J", 54, 745, 407, 113, "RRF(d) = sum 1 / (60 + rank)", "Only lists containing d; ranks start at 1\nExample: ranks 1 + 3 -> 0.03227", "code", title_size=20, body_size=16)
    p.n("K", 514, 745, 410, 113, "Exact vector scan: O(N x d)", "N candidate vectors; d dimensions\nAdd ANN only after measured need", "model", title_size=21, body_size=16)
    p.n("L", 977, 745, 409, 113, "Lexical-only hits must enter the pool", "Reranking cannot recover unseen candidates\nPostgreSQL FTS is not automatically BM25", "decision", title_size=19, body_size=16)
    pages.append(p)

    p = Page(10, "Watch three memories support one useful draft", "Example: 'Draft an Atlas update for Mira in her requested format.'", "EVALUATION.md")
    for key, x, title, body in [
        ("A", 54, "dict_0002 / preference", "Three bullets for Atlas updates\nCall out blockers"),
        ("B", 517, "dict_0003 / latest plan", "18 -> 21 September 2026\nLegal review needs more time"),
        ("C", 980, "dict_0006 / blocker + next step", "Legal approval is the blocker\nAsk Legal for its review date")]:
        p.n(key, x, 177, 406, 127, title, body, "data", "document", title_size=21)
    p.n("D", 420, 380, 596, 120, "Evidence + instruction budget", "System rules | current request | selected evidence | reply reserve\nUse original supporting passages + source IDs", "code", title_size=23, body_size=18)
    for key in "ABC":
        p.e(key, "D", sp="B", ep="T", via=[(p.nodes[key].x+203, 342), (718, 342)])
    p.n("E", 54, 579, 303, 153, "DeepSeek", "Generate a grounded draft\nMaintain scope + uncertainty", "model", "hex")
    p.n("F", 427, 563, 552, 184, "Draft + Sources", "1  Latest recorded plan: 21 September\n2  Blocker: legal approval\n3  Next step: ask Legal for a review date\nSources: dict_0002, dict_0003, dict_0006", "data", "document", title_size=23, body_size=20)
    p.n("G", 1053, 579, 333, 153, "Check + release", "IDs valid? Support faithful?\nRecheck revocation before publication", "code")
    p.e("D", "E", sp="L", ep="T", via=[(205.5, 440)])
    p.e("E", "F")
    p.e("F", "G")
    p.n("H", 54, 786, 400, 74, "Draft created; nothing was sent", kind="risk", title_size=21)
    p.n("I", 517, 786, 405, 74, "Missing fact -> acknowledge / ask", kind="decision", title_size=21)
    p.n("J", 980, 786, 406, 74, "Search failure -> report / bounded retry", kind="risk", title_size=20)
    pages.append(p)

    p = Page(11, "Give each model a bounded role", "The smaller model is a cost hypothesis to test, not a trusted database operator.", "ARCHITECTURE.md", "UNTESTED")
    p.n("A", 54, 178, 393, 164, "Small extractor", "Nemotron Lightning or Qwen3-8B\nPropose claims / evidence / revisions", "model", "hex", tag="UNTESTED")
    p.n("B", 524, 178, 391, 164, "DeepSeek responder", "Reason over retrieved evidence\nAnswer / draft / clarification", "model", "hex", tag="DECIDED")
    p.n("C", 994, 178, 392, 164, "Optional embedder", "Qwen3-Embedding-0.6B candidate\nProduce versioned search vectors", "model", "hex", tag="OPTIONAL", title_size=21)
    p.n("D", 287, 432, 866, 142, "Application code keeps authority", "Typed schemas | ownership | policy | exact spans | transitions\nShared revision guard | transactions | bounded retries | usage accounting", "code", title_size=26, body_size=21)
    for key in "ABC":
        p.e(key, "D", sp="B", ep="T", via=[(p.nodes[key].x+p.nodes[key].w/2, 389), (720, 389)], kind="model")
    p.n("E", 54, 678, 395, 177, "Before live calls", "Verify endpoint + account access\nRetention / no-training settings\nCredentials + agreed spend ceiling", "decision", title_size=23)
    p.n("F", 523, 678, 392, 177, "What a proposal can say", "ADD_CLAIM / LINK_EVIDENCE\nPROPOSE_SUPERSESSION / NOOP\nNEEDS_CLARIFICATION", "data", "document", title_size=23, body_size=17)
    p.n("G", 990, 678, 396, 177, "Measure total cost", "Ingestion + answers + retries + failures\nCompare cost per successful task\nSmaller parameters do not prove savings", "code", title_size=23)
    p.label(292, 609, "No unrestricted SQL. No model-selected user identity. No claimed hidden reasoning traces.", 18, MUTED)
    pages.append(p)

    p = Page(12, "Private is a boundary before personal state", "Private starts fresh and never backfills into Normal.", "DECISIONS.md", "DECIDED")
    p.group(54, 165, 1332, 228, "NORMAL  /  PERMITTED HISTORY + SELECTIVE LEARNING", "data")
    row(p, list("ABC"), 218, ["Eligible input", "Saved history + memory", "Personalized reply"],
        ["Mode + policy gate", "Source-backed retrieval / updates", "Sources + permitted operation trace"],
        ["user", "data", "model"], ["pill", "cylinder", "hex"], h=123, w=381, gap=70, x=79)
    p.group(54, 426, 1332, 236, "PRIVATE  /  TRANSIENT SESSION ONLY", "code")
    row(p, list("DEFG"), 479, ["Fresh input", "Temporary context", "Temporary reply", "Discard"],
        ["No Normal carryover", "Only explicitly supplied evidence", "Transient model call / counters", "Exit / close / no backfill"],
        ["user", "code", "model", "risk"], ["pill", "round", "hex", "round"], h=126, w=278, gap=56, x=79)
    p.n("H", 79, 715, 602, 141, "Blocked personal reads + durable writes", "History / memory / dictionary / style\nLogs / jobs / embeddings / cache / browser / exports\nApplies on success, timeout and error", "risk", title_size=21, body_size=18)
    p.n("I", 751, 715, 607, 141, "Hosted inference is a separate boundary", "Provider retention + no-training must be checked\nOnly the Private switch preference may persist", "decision", title_size=22, body_size=18)
    p.label(82, 866, "Private example: saved Atlas date is unavailable unless supplied again as temporary context.", 15, MUTED)
    pages.append(p)

    p = Page(13, "Forgetting must follow every dependency", "Forgetting a memory is more than deleting its vector.", "ARCHITECTURE.md", "DECIDED")
    p.n("A", 54, 178, 325, 132, "Forget request", "Select memory + supporting passages\nUser controls the scope", "user", "pill")
    p.n("B", 506, 178, 422, 132, "Commit exclusions + new revision", "Shared policy guard\nCover known duplicates + reimports", "code")
    p.n("C", 1055, 178, 331, 132, "Invalidate usable derivatives", "Canonical state + pending work\nFuture retrieval and relearning blocked", "risk")
    p.e("A", "B")
    p.e("B", "C")
    p.group(54, 362, 1332, 298, "DEPENDENCY MAP  /  CONTROLLED BY CANONICAL EXCLUSIONS", "risk")
    row(p, list("DEFGH"), 442, ["Source passage", "Claim revision", "Search view", "Selected context", "Buffered reply"],
        ["Excluded for future use", "Exclude supported interpretation", "Text / vectors / summaries / caches\nKnown derivatives; if present", "Recheck before model use", "Guarded release; see P14"],
        ["data", "data", "data", "code", "model"], ["document", "cylinder", "cylinder", "round", "hex"],
        h=146, w=233, gap=37, x=78)
    p.e("B", "D", sp="B", ep="T", via=[(717, 336), (29, 336), (29, 407), (194.5, 407)], kind="risk", dashed=True)
    p.n("I", 54, 716, 401, 140, "Delayed jobs / retries / reimport", "Shared guard rejects stale commits\nExclusions stop relearning known support", "risk", title_size=22, body_size=18)
    p.n("J", 520, 716, 402, 140, "History can remain visible", "Inspect separately until deleted\nVisibility does not authorize memory reuse", "data", title_size=22, body_size=18)
    p.n("K", 986, 716, 400, 140, "Already released text", "Cannot be recalled or unsent\nFuture uses must honor revocation", "decision", title_size=22, body_size=18)
    pages.append(p)

    p = Page(14, "A shared guard defeats stale work", "Illustrative interleaving: Forget commits while extraction is in flight.", "EVALUATION.md")
    p.group(54, 163, 1332, 210, "WORKER  /  MODEL CALL OUTSIDE LOCK", "model")
    row(p, list("ABC"), 219, ["Read revision 7", "Model proposes memory", "Wait for shared guard"],
        ["Permitted source snapshot", "May take time; no DB lock held", "Do not blindly commit old output"],
        ["data", "model", "decision"], ["document", "hex", "round"], h=116, w=381, gap=70, x=79)
    p.group(54, 407, 1332, 220, "FORGET  /  SAME PER-USER POLICY GUARD", "risk")
    row(p, list("DEF"), 464, ["Acquire common policy guard", "Commit revision 8", "Release guard"],
        ["Exclusive update lock\nOr equivalent atomic protocol", "Exclusions + dependent invalidation", "Forget is committed"],
        ["code", "risk", "code"], h=123, w=381, gap=70, x=79)
    p.n("G", 79, 704, 380, 151, "Worker acquires guard", "Recheck source / claim / policy\nRevision changed: reject or recompute", "code", title_size=22)
    p.n("H", 529, 704, 381, 151, "Same guard at reply release", "Retrieve -> generate buffer\nSynchronize recheck + atomic publication", "code", title_size=22)
    p.n("I", 979, 704, 379, 151, "Test the actual database", "Two connections + explicit barriers\nBoth orders; no timing-sleep simulation", "decision", title_size=22)
    p.e("C", "D", sp="B", ep="T", via=[(1171.5, 388), (269.5, 388)], label="Forget wins the guard", at=(740, 375), kind="risk", dashed=True)
    p.e("F", "G", sp="B", ep="T", via=[(1171.5, 660), (269, 660)], label="worker resumes", at=(728, 648))
    pages.append(p)

    p = Page(15, "Diagnose feedback before changing memory", "Dissatisfaction alone does not supply a new fact or a permanent preference.", "ARCHITECTURE.md")
    p.n("A", 54, 174, 312, 117, "User feedback", "'That is wrong' / specific correction", "user", "pill")
    p.n("B", 469, 174, 418, 117, "Inspect permitted evidence + operation", "Normal: concise saved trace\nPrivate: active temporary context only", "code", title_size=21)
    p.n("C", 990, 174, 396, 117, "Which layer failed?", "Unclear replacement / scope?\nAsk a short clarification first", "decision")
    p.e("A", "B")
    p.e("B", "C")
    repairs = [
        ("D", "Wrong extraction", "Restore Ravi's conditional status\nCorrect interpretation; keep source", "risk"),
        ("E", "Supported world change", "Atlas: 18 -> 21 September\nCreate successor; preserve history", "data"),
        ("F", "Missed retrieval", "Find the missing permitted source\nRepair query / candidate selection", "code"),
        ("G", "Unsupported generation", "Rewrite from evidence\nPreserve uncertainty / abstain", "model"),
        ("H", "Wrong style", "Follow the current request\nPersist only explicit scoped preference", "decision"),
        ("I", "Operational failure", "Report failure; bounded repair\nNever invent tool success", "risk"),
    ]
    for i, (key, title, body, kind) in enumerate(repairs):
        p.n(key, 54+(i%3)*466, 381+(i//3)*160, 402, 128, title, body, kind, title_size=22, body_size=17)
    for key in "DEFGHI":
        n = p.nodes[key]
        spine = n.x - 19
        p.e("C", key, sp="B", ep="L",
            via=[(1188, 327), (spine, 327), (spine, n.y+n.h/2)],
            dashed=True, kind="decision")
    p.n("J", 54, 744, 402, 126, "Smallest supported repair", "Guard changes; invalidate dependent views", "code", title_size=21, body_size=17)
    p.n("K", 520, 744, 402, 126, "Verify the revised reply", "One bounded rerun after diagnosis", "code", title_size=21, body_size=17)
    p.n("L", 986, 744, 400, 126, "Regression case", "Synthetic / permitted example\nNo model-training use; review procedure changes", "data", "document", title_size=21, body_size=16)
    for key in "DEFGHI":
        n = p.nodes[key]
        spine = n.x + n.w + 17
        p.e(key, "J", sp="R", ep="T",
            via=[(spine, n.y+n.h/2), (spine, 707), (255, 707)])
    p.e("J", "K")
    p.e("K", "L")
    p.label(520, 721, "SUPPORTED DIAGNOSIS -> SMALLEST REPAIR -> VERIFIED OUTCOME", 13, MUTED, True)
    pages.append(p)

    p = Page(16, "Prove usefulness with controlled comparisons", "Targets and planned tests are not measured results.", "EVALUATION.md", "UNTESTED")
    row(p, list("ABCX"), 176, ["8 diagnostic observations", "Authorized live pilot", "Choose two variants", "~500 observations"],
        ["Changes / uncertainty / attribution\nPrivate / Forget / reimport / DB races",
         "Diagnostics repeated three times\nPilot: one mechanism at a time",
         "Baseline + justified candidate\nSame responder + evidence budget",
         "Separate tuning / blind questions\nBlind questions repeated three times\nLabels stay outside ingestion"],
        ["data", "model", "code", "data"], ["document", "hex", "round", "cylinder"], h=178, w=291, gap=56)
    p.group(54, 377, 1332, 210, "ABLATIONS  /  CHANGE ONE MECHANISM; HOLD RELEVANT SETTINGS FIXED")
    choices = [
        ("D", "History baseline", "Whole eligible history if it fits\nReport 'does not fit' otherwise"),
        ("E", "Retrieval", "Lexical -> lexical + dense\nSame source chunks"),
        ("F", "Representation", "Sources -> sources + claims\nSame chosen retrieval"),
        ("G", "Extractor", "Small -> stronger reference\nSame DeepSeek responder"),
    ]
    for i,(key,title,body) in enumerate(choices):
        p.n(key, 79+i*327, 428, 300, 120, title, body, "code", title_size=22, body_size=17)
    p.n("H", 54, 641, 406, 217, "Measure all attempts", "Task success / unsupported claims\nExtraction precision + recall\nEvidence coverage / DB growth\nLatency p50 + p95 / total cost\nInclude ingestion, repair and failures", "data", "document", title_size=23, body_size=18)
    p.n("I", 517, 641, 406, 217, "Proposed acceptance targets", "All deterministic invariants pass\nAll eight core cases: every live repeat\nBlind task success >= 90%; no regression\nZero prohibited privacy / Forget behavior", "decision", tag="PROPOSED", title_size=22, body_size=17)
    p.n("J", 980, 641, 406, 217, "Evidence limits", "Mock contracts do not prove model quality\nCheck semantic support, not only source IDs\nRetain failures + skipped comparisons\nSmall samples limit generalization", "risk", title_size=23, body_size=18)
    pages.append(p)

    p = Page(17, "Every extra mechanism must earn its place", "Start small. Measure a concrete failure. Add the smallest justified mechanism.", "DECISIONS.md")
    tradeoffs = [
        ("A", "One PostgreSQL database", "Transactions + sources + jobs + search", "Separate vector / graph services", "Add only for demonstrated capability or scale need"),
        ("B", "Lexical; exact when dense", "Dense retrieval remains an optional comparison", "Approximate nearest neighbors", "Add when measured latency justifies recall tradeoff"),
        ("C", "Source history + selective claims", "Original evidence survives extraction gaps", "Hierarchical summaries / reviewed procedures", "Add evidence links + correction semantics; keep originals"),
        ("D", "DB worker + buffered replies", "Fewer services; smaller revocation surface", "Redis / response cache / streaming", "Add only after invalidation and race tests"),
        ("E", "Thin UI + local Compose", "Complete user journey + reproducible review", "Rich UI / Azure deployment", "Polish and hosting follow required local gates"),
    ]
    p.label(61, 170, "STARTING CHOICE", 15, COLORS["code"][0], True)
    p.label(536, 170, "ALTERNATIVE / EXTRA COMPLEXITY", 15, COLORS["model"][0], True)
    p.label(1013, 170, "DECISION GATE", 15, COLORS["decision"][0], True)
    for i,(key,title,body,alt,gate) in enumerate(tradeoffs):
        y=208+i*130
        p.n(key,54,y,404,107,title,body,"code",title_size=21,body_size=17)
        p.n(key+"1",520,y,403,107,alt,kind="model",shape="hex",title_size=21)
        p.n(key+"2",987,y,399,107,gate,kind="decision",title_size=20)
        p.e(key,key+"1",dashed=True,kind="model")
        p.e(key+"1",key+"2",dashed=True,kind="decision")
    p.label(56, 870, "The goal is a supported useful task, not the largest collection of frameworks.", 15, MUTED)
    pages.append(p)

    p = Page(18, "Understand here, implement from the same plan", "New discussion chat -> recorded decision -> approved CLI work -> tested Git checkpoint.", "todo.md", "REFERENCE")
    row(p, list("ABC"), 167, ["Diagram + Markdown", "Design discussion", "Codex CLI implementation"],
        ["PDF: ask about page + node\nMarkdown: precise requirements",
         "Explain tradeoffs; resolve doubts\nRecord agreed changes + approved scope",
         "Read repo docs + actual Git state\nCLI location/auth/access still to verify"],
        ["data", "user", "code"], ["document", "pill", "round"], h=137, w=406, gap=57)
    p.group(54, 338, 1332, 210, "CURRENT CHECKPOINT  /  VERIFIED ENVIRONMENT DOES NOT MEAN IMPLEMENTED PRODUCT")
    p.n("D", 78, 388, 406, 150, "S01  Final independent Phase One", "User owns final positioning + vision\nAI-assisted references preserved", "decision", tag="OPEN", title_size=20, body_size=16)
    p.n("E", 519, 388, 400, 150, "S02  Docker / WSL readiness", "Engine + Ubuntu access + volume probe\nOne current Windows checkout", "ready", tag="VERIFIED", title_size=20, body_size=16)
    p.n("F", 954, 388, 406, 150, "S03  Bootstrap next", "API + DB + CLI + migrations + tests\nImportant code/schema approval pending", "decision", tag="OPEN", title_size=20, body_size=16)
    steps = [("G","S04-05","Contracts + policy\nImport eight sources"),
             ("H","S06-08","Real answer + claims\nEvaluate retrieval"),
             ("I","S09-10","Controls + repair\nRequired minimal UI"),
             ("J","S11-12","~500 corpus + evaluation\nClean review + scoped reset")]
    for i,(key,title,body) in enumerate(steps):
        p.n(key,54+i*346,589,294,128,title,body,"code",title_size=23,body_size=18)
    for a,b in zip("GHI","HIJ"):
        p.e(a,b)
    p.n("K",54,744,847,126,"Approved scope -> build -> test -> update tracker -> commit -> push -> verify",
        "Same repository; one active checkout; truthful results; fix failed gates before completion",
        "code",title_size=22,body_size=17)
    p.n("L",950,744,436,126,"Target: 12 Sep afternoon IST",
        "Optional experiment freeze: 10:00 proposed\nReserve final hours for clean review",
        "decision",title_size=22,body_size=17)
    pages.append(p)
    return pages


def main():
    fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    pages = build_pages()
    c = canvas.Canvas(str(OUTPUT), pagesize=(W, H), pageCompression=1, invariant=1)
    c.setTitle("Hey Jarvis - Semantic Memory Visual Guide")
    c.setAuthor("ProjectSemanticMemoryJarvis - AI-assisted planning diagrams")
    c.setSubject("18 diagram pages: proposed architecture, evidence, controls, evaluation and delivery")
    for p in pages:
        p.draw(c)
    c.save()
    report = {
        "page_count": len(pages),
        "output": str(OUTPUT.relative_to(ROOT)),
        "basis_commit": "557d1ce",
        "pages": [{"page": p.number, "title": p.title, "nodes": p.fit_report} for p in pages],
    }
    (QA / "visual-guide-layout.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Created {OUTPUT} ({len(pages)} pages, {OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
