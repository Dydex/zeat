"""Small, dependency-free numerical routines.

Everything here is plain Python so the project runs with no installs. Each
function is covered by tests/test_stats.py, including known-answer checks.
"""

import math
import random


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def project_simplex(v):
    """Euclidean projection onto {w >= 0, sum w = 1} (Duchi et al., 2008)."""
    u = sorted(v, reverse=True)
    css, rho, theta = 0.0, 0, 0.0
    for i, ui in enumerate(u, 1):
        css += ui
        t = (css - 1.0) / i
        if ui - t > 0:
            rho, theta = i, t
    return [max(x - theta, 0.0) for x in v]


def _matvec(X, w):
    return [sum(a * b for a, b in zip(row, w)) for row in X]


def _lipschitz(X, iters=100):
    """Largest eigenvalue of X^T X by power iteration."""
    n = len(X[0])
    v = [1.0 / math.sqrt(n)] * n
    lam = 0.0
    for _ in range(iters):
        Xv = _matvec(X, v)
        g = [sum(X[t][j] * Xv[t] for t in range(len(X))) for j in range(n)]
        lam = math.sqrt(sum(x * x for x in g))
        if lam == 0:
            return 1.0
        v = [x / lam for x in g]
    return lam


def synthetic_control(y, X, iters=20000, tol=1e-12):
    """Fit simplex weights with a free intercept on demeaned data.

    y: list of T floats; X: T rows x J donors. Returns (weights, intercept).
    Solved by accelerated projected gradient (FISTA); the problem is convex.
    """
    T, J = len(y), len(X[0])
    if J == 1:
        return [1.0], mean(y) - mean(r[0] for r in X)
    ym = mean(y)
    xm = [mean(X[t][j] for t in range(T)) for j in range(J)]
    yc = [v - ym for v in y]
    Xc = [[X[t][j] - xm[j] for j in range(J)] for t in range(T)]
    L = _lipschitz(Xc) or 1.0
    w = [1.0 / J] * J
    z, tk = w[:], 1.0
    prev_loss = float("inf")
    for i in range(iters):
        r = [a - b for a, b in zip(_matvec(Xc, z), yc)]
        g = [sum(Xc[t][j] * r[t] for t in range(T)) for j in range(J)]
        w_new = project_simplex([z[j] - g[j] / L for j in range(J)])
        t_new = (1 + math.sqrt(1 + 4 * tk * tk)) / 2
        z = [w_new[j] + (tk - 1) / t_new * (w_new[j] - w[j]) for j in range(J)]
        w, tk = w_new, t_new
        if i % 200 == 0:
            loss = sum((a - b) ** 2 for a, b in zip(_matvec(Xc, w), yc))
            if prev_loss - loss < tol:
                break
            prev_loss = loss
    intercept = ym - sum(w[j] * xm[j] for j in range(J))
    return w, intercept


def ols(x, y):
    """Simple regression y = a + b x. Returns (a, b)."""
    mx, my = mean(x), mean(y)
    sxx = sum((v - mx) ** 2 for v in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
    return my - b * mx, b


def rmspe(xs):
    xs = list(xs)
    return math.sqrt(sum(v * v for v in xs) / len(xs)) if xs else float("nan")


def quantile(xs, q):
    """Linear-interpolation quantile (same as numpy's default)."""
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def block_bootstrap_slope(x, y, block=4, draws=2000, seed=7, level=0.90):
    """Moving-block bootstrap CI for the OLS slope of y on x.

    Resamples blocks of consecutive (x, y) pairs, which keeps short-run
    autocorrelation that a plain bootstrap would destroy.
    """
    rng = random.Random(seed)
    n = len(x)
    starts = list(range(n - block + 1))
    slopes = []
    for _ in range(draws):
        idx = []
        while len(idx) < n:
            s = rng.choice(starts)
            idx.extend(range(s, s + block))
        idx = idx[:n]
        xs, ys = [x[i] for i in idx], [y[i] for i in idx]
        if len(set(xs)) < 2:
            continue
        slopes.append(ols(xs, ys)[1])
    a = (1 - level) / 2
    return quantile(slopes, a), quantile(slopes, 1 - a)
