"""Build the two word clouds on the overview slide of the design-elements deck.

Input:  docs/explorer/index.html (the explorer data, written by build_site.py),
        downloads/examples/CDISC_Pilot_Study.json
Output: site/slides/design-elements-slides.html, the parts between the
        <!-- cloud:model -->, <!-- cloud:study --> and <!-- cloud:stats --> markers

Left cloud: attribute names of the USDM v4 model, sized by the number of classes
that declare them, coloured by content group; housekeeping and containment left out.
Right cloud: the read-text attributes in the CDISC Pilot example, sized by the
characters they hold. Run after build_site.py; then run render_slides.py.
"""
import json
import math
import re
from collections import Counter, defaultdict

from common import ROOT

SLIDES = ROOT / "site" / "slides" / "design-elements-slides.html"
EXPLORER = ROOT / "docs" / "explorer" / "index.html"
PILOT = ROOT / "downloads" / "examples" / "CDISC_Pilot_Study.json"

COLOUR = {"data": "#1E4F8A", "str": "#5B8FD0", "words": "#B85F1E", "naming": "#8A93A6"}
CATEGORY = {"Coded": "data", "Reference": "data", "TypedValue": "data", "structure": "str", "read": "words", "Naming": "naming"}
DATA_GROUPS = ("structure", "Reference", "TypedValue", "Coded")
FRIENDLY = {
    ("NarrativeContentItem", "text"): "protocol sections",
    ("EligibilityCriterionItem", "text"): "eligibility criteria",
    ("Objective", "text"): "objectives",
    ("Endpoint", "text"): "endpoints",
    ("TransitionRule", "text"): "element rules",
    ("Condition", "text"): "conditions",
}
WIDTH, HEIGHT = 780, 520


def explorer_data():
    text = EXPLORER.read_text()
    found = re.search(r'<script type="application/json" id="data">(.*?)</script>', text, re.S)
    return json.loads(found.group(1).replace("<\\/", "</"))


def model_words(data):
    """Unique attribute names with the number of classes declaring them and their majority category."""
    names = defaultdict(Counter)
    for cls in data["classes"]:
        for attr in cls["attrs"]:
            if attr["group"] in CATEGORY:
                names[attr["a"]][attr["group"]] += 1
    return [(name, sum(groups.values()), CATEGORY[groups.most_common(1)[0][0]]) for name, groups in names.items()]


def pilot_counts(data):
    """Characters and values per content group in the Pilot file, and characters per read-text attribute."""
    group = {(cls["name"], attr["a"]): attr["group"] for cls in data["classes"] for attr in cls["attrs"]}
    supers = {cls["name"]: cls["super"] for cls in data["classes"]}

    def lookup(cls, attr):
        queue = [cls]
        while queue:
            current = queue.pop(0)
            if (current, attr) in group:
                return group[(current, attr)]
            queue += supers.get(current, [])
        raise RuntimeError(f"{cls}.{attr} has no assessment in the overlay")

    chars, values, words = Counter(), Counter(), Counter()

    def walk(node):
        if isinstance(node, dict):
            cls = node.get("instanceType")
            for key, value in node.items():
                if cls and isinstance(value, str) and value.strip():
                    g = lookup(cls, key)
                    chars[g] += len(value)
                    values[g] += 1
                    if g == "read":
                        words[(cls, key)] += len(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(json.loads(PILOT.read_text()))
    return chars, values, words


def place(items):
    """items: (label, font size, colour), largest first. Archimedean spiral placement with box collision."""
    boxes, out = [], []
    for label, size0, colour in items:
        for size in (size0, size0 * 0.9, size0 * 0.8):
            w, h = 0.56 * size * len(label), size * 1.05
            a = 0.0
            spot = None
            while a < 1200:
                r = 1.6 * a
                x = WIDTH / 2 + r * math.cos(a) * 1.5 - w / 2
                y = HEIGHT / 2 + r * math.sin(a) - h / 2
                inside = x >= 0 and y >= 0 and x + w <= WIDTH and y + h <= HEIGHT
                if inside and all(x + w + 4 < bx or bx + bw + 4 < x or y + h + 2 < by or by + bh + 2 < y for bx, by, bw, bh in boxes):
                    spot = (x, y)
                    break
                a += min(0.05, 4 / (r + 1))
            if spot:
                boxes.append((spot[0], spot[1], w, h))
                out.append((label, size, colour, spot[0], spot[1] + h * 0.82))
                break
        else:
            raise RuntimeError(f"Could not place {label} in the cloud")
    return out


def svg(placed):
    body = "".join(
        f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size:.0f}" font-weight="{700 if size > 30 else 600}" fill="{colour}">{label}</text>'
        for label, size, colour, x, y in placed
    )
    return f'<svg width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" style="font-family:\'Nunito Sans\',sans-serif">{body}</svg>'


def replace_between(text, name, content):
    start, end = f"<!-- cloud:{name} -->", f"<!-- /cloud:{name} -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise RuntimeError(f"{SLIDES.name} must hold exactly one {start} ... {end} pair")
    i, j = text.index(start) + len(start), text.index(end)
    return text[:i] + content + text[j:]


def main():
    data = explorer_data()
    model = model_words(data)
    chars, values, words = pilot_counts(data)
    study = [(FRIENDLY.get(key, f"{key[0]}.{key[1]}"), n) for key, n in words.items()]

    data_values = sum(values[g] for g in DATA_GROUPS)
    data_chars = sum(chars[g] for g in DATA_GROUPS)
    share = chars["read"] / (chars["read"] + data_chars)
    stats_line = (
        f"In the CDISC Pilot, {values['read']} text values hold {round(share * 100)}% of the characters, "
        f"against {data_values:,} values that are data (housekeeping and naming not counted). "
        "The model cloud leaves out housekeeping and containment attributes."
    )

    model_items = sorted(((n, min(58, 13 + 7 * math.sqrt(k - 1)), COLOUR[cat]) for n, k, cat in model), key=lambda r: -r[1])
    study_items = sorted(((label, min(18 + 0.16 * math.sqrt(n), 700 / (0.56 * len(label))), COLOUR["words"]) for label, n in study), key=lambda r: -r[1])

    text = SLIDES.read_text()
    text = replace_between(text, "model", svg(place(model_items)))
    text = replace_between(text, "study", svg(place(study_items)))
    text = replace_between(text, "stats", stats_line)
    SLIDES.write_text(text)
    print(f"OK: {len(model)} attribute names and {len(study)} Pilot text attributes. {stats_line}")


if __name__ == "__main__":
    main()
