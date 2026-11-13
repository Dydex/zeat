"""Tiny SVG line-chart renderer (no dependencies).

Colours are CSS variables defined by the page, so charts follow light/dark
themes. Every chart carries a <title> and <desc> for screen readers.
"""

import html
import json
import math

W, H = 720, 300
M = dict(l=66, r=16, t=30, b=34)

# Series styles map to CSS variables in site.py.
_CLIP = 0

STYLES = {
    "primary": "var(--c-primary)",
    "control": "var(--c-control)",
    "muted": "var(--c-muted)",
    "accent": "var(--c-accent)",
    "bad": "var(--c-bad)",
}


def nice_ticks(lo, hi, n=5):
    if hi == lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    start = math.floor(lo / step) * step
    ticks, v = [], start
    while v <= hi + step * 1e-9:
        if v >= lo - step * 1e-9:
            ticks.append(round(v, 10))
        v += step
    return ticks


def log_ticks(lo, hi):
    """Ticks at 1, 2, 5 x 10^k inside [lo, hi] (values in linear units)."""
    out = []
    for k in range(math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1):
        for m in (1, 2, 5):
            v = m * 10 ** k
            if lo <= v <= hi:
                out.append(v)
    if len(out) > 7:
        out = [v for v in out if str(v).lstrip("0.").startswith("1")]
    return out


def _hover_attr(xs_px, rows, top, bottom):
    """Data for the page's hover script: crosshair x positions and tooltip rows."""
    d = dict(w=W, t=top, b=bottom, x=[round(x, 1) for x in xs_px], rows=rows)
    return f' data-hover="{html.escape(json.dumps(d, separators=(",", ":")), quote=True)}"'


def _event_label(x, label, e):
    if x > W - M["r"] - 40:
        return f'<text x="{x + 4:.1f}" y="{M["t"] - 9}" class="event-label" text-anchor="end">{e(label)}</text>'
    return f'<text x="{x:.1f}" y="{M["t"] - 9}" class="event-label" text-anchor="middle">{e(label)}</text>'


def _legend(items):
    if len(items) < 2:
        return ""
    return '<div class="legend">' + "".join(items) + "</div>"


def line_chart(series, title, desc, x_fmt=str, y_fmt=str, log_y=False,
               vlines=(), hline=None, x_ticks=None, y_range=None, x_hover=None, y_hover=None):
    """series: list of dict(name, points=[(x, y)], style, width=2, dash=None,
    opacity=1, legend=True, hover=(style != muted), short=name). x and y are
    numbers; y in linear units. x_hover/y_hover format the tooltip."""
    pts = [(x, y) for s in series for x, y in s["points"] if y is not None]
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    x0, x1 = min(xs), max(xs)
    if y_range:
        y0, y1 = y_range
    else:
        y0, y1 = min(ys), max(ys)
        if hline is not None:
            y0, y1 = min(y0, hline), max(y1, hline)
    if log_y:
        ty = log_ticks(y0, y1)
        fy = math.log10
        y0, y1 = math.log10(y0) - 0.02, math.log10(y1) + 0.02
    else:
        pad = (y1 - y0) * 0.06 or 1
        y0, y1 = y0 - pad, y1 + pad
        ty = nice_ticks(y0, y1)
        fy = float
    pw, ph = W - M["l"] - M["r"], H - M["t"] - M["b"]

    def sx(x):
        return M["l"] + (x - x0) / ((x1 - x0) or 1) * pw

    def sy(y):
        return M["t"] + (1 - (fy(y) - y0) / ((y1 - y0) or 1)) * ph

    e = html.escape
    global _CLIP
    _CLIP += 1
    cid = f"clip{_CLIP}"
    hov = [sr for sr in series if sr.get("hover", sr["style"] != "muted")]
    xh, yh = x_hover or x_fmt, y_hover or y_fmt
    lookup = [dict((x, y) for x, y in sr["points"] if y is not None) for sr in hov]
    hx = sorted({x for lk in lookup for x in lk if x0 <= x <= x1})
    rows = [[xh(x), [[sr.get("short", sr["name"]), STYLES[sr["style"]], yh(lk[x]),
                      round(min(max(sy(lk[x]), M["t"]), H - M["b"]), 1)]
                     for sr, lk in zip(hov, lookup) if x in lk]] for x in hx]
    attr = _hover_attr([sx(x) for x in hx], rows, M["t"], H - M["b"]) if hx else ""
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" class="chart"{attr}>',
           f'<title>{e(title)}</title><desc>{e(desc)}</desc>',
           f'<defs><clipPath id="{cid}"><rect x="{M["l"]}" y="{M["t"]}" width="{pw}" height="{ph}"/></clipPath></defs>']
    # grid + y labels
    for t in ty:
        y = sy(t)
        if M["t"] - 1 <= y <= H - M["b"] + 1:
            out.append(f'<line x1="{M["l"]}" x2="{W - M["r"]}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
            out.append(f'<text x="{M["l"] - 8}" y="{y + 4:.1f}" class="tick" text-anchor="end">{e(y_fmt(t))}</text>')
    # x labels
    for t in (x_ticks if x_ticks is not None else nice_ticks(x0, x1, 6)):
        if x0 <= t <= x1:
            out.append(f'<text x="{sx(t):.1f}" y="{H - 10}" class="tick" text-anchor="middle">{e(x_fmt(t))}</text>')
    if hline is not None:
        out.append(f'<line x1="{M["l"]}" x2="{W - M["r"]}" y1="{sy(hline):.1f}" y2="{sy(hline):.1f}" class="zero"/>')
    for x, label in vlines:
        if x0 <= x <= x1:
            out.append(f'<line x1="{sx(x):.1f}" x2="{sx(x):.1f}" y1="{M["t"]}" y2="{H - M["b"]}" class="event"/>')
            out.append(_event_label(sx(x), label, e))
    out.append(f'<g clip-path="url(#{cid})">')
    for s in series:
        segs, cur = [], []
        for x, y in s["points"]:
            if y is None:
                if cur:
                    segs.append(cur)
                cur = []
            else:
                cur.append(f"{sx(x):.1f},{sy(y):.1f}")
        if cur:
            segs.append(cur)
        dash = f' stroke-dasharray="{s["dash"]}"' if s.get("dash") else ""
        for seg in segs:
            if len(seg) == 1:
                cx, cy = seg[0].split(",")
                out.append(f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="{STYLES[s["style"]]}"/>')
                continue
            out.append(f'<polyline fill="none" stroke="{STYLES[s["style"]]}" stroke-width="{s.get("width", 2)}"'
                       f' stroke-opacity="{s.get("opacity", 1)}" stroke-linejoin="round"{dash}'
                       f' points="{" ".join(seg)}"/>')
    out.append("</g></svg>")
    legend = _legend([
        f'<span class="key"><i style="background:{STYLES[s["style"]]};opacity:{max(s.get("opacity", 1), .6)}"></i>{e(s["name"])}</span>'
        for s in series if s.get("legend", True)])
    return f'<div class="plot">{"".join(out)}{legend}</div>'


def dot_chart(points, title, desc, x_fmt, y_fmt, highlight=None, hline=None, split=None, x_hover=None):
    """Scatter of (x, y) with an optional highlighted real value as a line."""
    series = [dict(name="Placebo (fake event date)", style="muted",
                   points=[], width=0)]
    xs = [x for x, _ in points]
    ys = [y for _, y in points] + ([highlight] if highlight is not None else [])
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    pad = (y1 - y0) * 0.08 or 1
    y0, y1 = y0 - pad, y1 + pad
    pw, ph = W - M["l"] - M["r"], H - M["t"] - M["b"]
    sx = lambda x: M["l"] + (x - x0) / ((x1 - x0) or 1) * pw
    sy = lambda y: M["t"] + (1 - (y - y0) / (y1 - y0)) * ph
    e = html.escape
    xh = x_hover or x_fmt
    pts = sorted(points)
    rows = [[xh(x), [["Placebo effect", "var(--c-muted)", y_fmt(y), round(sy(y), 1)]]
             + ([["Real effect", "var(--c-primary)", y_fmt(highlight), round(sy(highlight), 1)]]
                if highlight is not None else [])] for x, y in pts]
    attr = _hover_attr([sx(x) for x, _ in pts], rows, M["t"], H - M["b"])
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" class="chart"{attr}>',
           f'<title>{e(title)}</title><desc>{e(desc)}</desc>']
    for t in nice_ticks(y0, y1):
        if y0 <= t <= y1:
            out.append(f'<line x1="{M["l"]}" x2="{W - M["r"]}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" class="grid"/>')
            out.append(f'<text x="{M["l"] - 8}" y="{sy(t) + 4:.1f}" class="tick" text-anchor="end">{e(y_fmt(t))}</text>')
    for t in nice_ticks(x0, x1, 6):
        if x0 <= t <= x1:
            out.append(f'<text x="{sx(t):.1f}" y="{H - 10}" class="tick" text-anchor="middle">{e(x_fmt(t))}</text>')
    if hline is not None and y0 <= hline <= y1:
        out.append(f'<line x1="{M["l"]}" x2="{W - M["r"]}" y1="{sy(hline):.1f}" y2="{sy(hline):.1f}" class="zero"/>')
    if split is not None and x0 <= split[0] <= x1:
        out.append(f'<line x1="{sx(split[0]):.1f}" x2="{sx(split[0]):.1f}" y1="{M["t"]}" y2="{H - M["b"]}" class="event"/>')
        out.append(_event_label(sx(split[0]), split[1], e))
    for x, y in points:
        out.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="3.2" fill="var(--c-muted)"/>')
    if highlight is not None:
        out.append(f'<line x1="{M["l"]}" x2="{W - M["r"]}" y1="{sy(highlight):.1f}" y2="{sy(highlight):.1f}" '
                   f'stroke="var(--c-primary)" stroke-width="2.5"/>')
    out.append("</svg>")
    legend = ('<span class="key"><i style="background:var(--c-muted)"></i>Placebo effect at a fake event date</span>'
              '<span class="key"><i style="background:var(--c-primary)"></i>Real effect</span>')
    return f'<div class="plot">{"".join(out)}<div class="legend">{legend}</div></div>'
