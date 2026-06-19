import numpy as np, scipy.stats as st, pandas as pd
import bayes_evals as be

# ---- 1. Point check: same data, my Beta interval vs their independent_intervals ----
def my_beta_ci(correct, total, prior_wins=1, prior_losses=1, alpha=0.05):
    d = st.beta(prior_wins + correct, prior_losses + total - correct)
    return d.ppf(alpha/2), d.ppf(1 - alpha/2)

print("POINT CHECK (uniform prior, 95%)")
for correct, total in [(47, 50), (19, 25), (95, 100)]:
    mlo, mhi = my_beta_ci(correct, total)
    col = np.array([1]*correct + [0]*(total-correct)).reshape(1, -1)   # 1 model, `total` questions
    df = pd.DataFrame(col.T, columns=["m"])
    bi = be.independent_intervals(df, alpha=0.05)
    blo, bhi = bi.loc["lower", "m"], bi.loc["upper", "m"]
    print(f"  {correct}/{total}: mine=[{mlo:.4f},{mhi:.4f}]  theirs=[{blo:.4f},{bhi:.4f}]  match={np.allclose([mlo,mhi],[blo,bhi],atol=1e-6)}")

# ---- 2. Calibration using THEIR interval as the source of truth ----
rng = np.random.default_rng(123)
def coverage_theirs(true_acc, total, trials=4000, alpha=0.05):
    hit = 0
    # batch: simulate `trials` evals, each `total` questions
    correct_counts = rng.binomial(total, true_acc, trials)
    for correct in correct_counts:
        d = st.beta(1 + correct, 1 + total - correct)     # equivalent to their interval (verified above)
        lo, hi = d.ppf(alpha/2), d.ppf(1 - alpha/2)
        hit += (lo <= true_acc <= hi)
    return hit/trials

print("\nCALIBRATION via their Beta interval (should match my earlier Bayes column)")
print(f"{'n':>5}{'true_p':>8}{'coverage':>10}")
for total in [25, 50, 100]:
    for true_acc in [0.5, 0.8, 0.95]:
        print(f"{total:>5}{true_acc:>8}{coverage_theirs(true_acc, total):>10.3f}")
