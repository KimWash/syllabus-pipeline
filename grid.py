# Assign words to table cells using the page's drawn line segments.
import collections

def cell_of(w, H, V, tol=0.6):
    x0, y0, x1, t = w[0], w[1], w[2], w[3]
    cx, cy = (x0 + x1) / 2, y0 + 4.5
    top = max((h[2] for h in H if h[2] < cy and h[0] - tol <= cx <= h[1] + tol), default=None)
    bot = min((h[2] for h in H if h[2] > cy and h[0] - tol <= cx <= h[1] + tol), default=None)
    left = max((v[0] for v in V if v[0] < cx and v[1] - tol <= cy <= v[2] + tol), default=None)
    right = min((v[0] for v in V if v[0] > cx and v[1] - tol <= cy <= v[2] + tol), default=None)
    return (top, bot, left, right)

def cells(words, H, V):
    g = collections.defaultdict(list)
    for w in words:
        g[cell_of(w, H, V)].append(w)
    return g
