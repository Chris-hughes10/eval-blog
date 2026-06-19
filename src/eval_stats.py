"""
Bayesian eval statistics — worked examples on SIMULATED data.
We plant known ground-truth parameters, generate eval outcomes, and check
that the inference recovers what we planted. No real model required.
"""
import numpy as np
import scipy.stats as st
import pymc as pm
from typing import Any

RNG = np.random.default_rng(7)     # seed for the planted data — any fixed value, for reproducibility
SAMPLE: dict[str, Any] = dict(draws=2000, tune=2000, chains=4, cores=1,   # 2000 draws after 2000 warm-up steps;
                              random_seed=7, progressbar=False)           # 4 chains, single-core -> stable, reproducible re-runs


def ci(samples, lo=2.5, hi=97.5):
    return np.percentile(samples, [lo, hi])


def shown_width(lo, hi, dp=3):                       # width from the *rounded* endpoints, so the printed
    return round(float(hi), dp) - round(float(lo), dp)   # interval and its width always add up on the page


def to_prob(logit):                # logit scale -> a plain 0..1 accuracy
    return 1 / (1 + np.exp(-logit))


# ----------------------------------------------------------------------
# EXAMPLE 1 — a single accuracy: Wald interval vs Beta-Binomial posterior
# ----------------------------------------------------------------------
print("=" * 64)
print("What can a single accuracy actually tell you?  (single accuracy, small n and at the boundary)")
print("=" * 64)

def wald(correct, total):                     # the textbook bar: symmetric, can fall off [0,1]
    p = correct / total                       # observed accuracy
    se = np.sqrt(p * (1 - p) / total)         # how much p would bounce on a fresh batch of questions
    return p, (p - 1.96 * se, p + 1.96 * se)  # ±1.96 SE (the 95% z-score) — nothing stops this exceeding 1

def beta_posterior(correct, total, prior_wins=2, prior_losses=2):
    losses = total - correct                          # the rest were wrong
    post = st.beta(prior_wins + correct,              # imagined wins  + real wins
                   prior_losses + losses)             # imagined losses + real losses
    return post.mean(), post.ppf([0.025, 0.975])      # point estimate, then 95% range — can't leave [0,1]

for correct, total in [(47, 50), (50, 50), (940, 1000)]:
    p, (wlo, whi) = wald(correct, total)
    bmean, (blo, bhi) = beta_posterior(correct, total)
    print(f"\n {correct}/{total}:")
    print(f"   Wald     point={p:.3f}  95% CI=[{wlo:.3f}, {whi:.3f}]"
          f"{'   <-- exceeds 1!' if whi > 1 else ''}")
    print(f"   Beta(2,2) mean={bmean:.3f}  95% CrI=[{blo:.3f}, {bhi:.3f}]")


# ----------------------------------------------------------------------
# CLUSTERING — questions nested in catalogue records: your effective sample size
#   300 question-scores, but they lean on 50 correlated catalogue records. Treat
#   them as 300 independent questions and your error bars come out too tight.
#   Uses a LOCAL rng so the global RNG (and Examples 2-3) are unaffected.
# ----------------------------------------------------------------------
print("\n" + "=" * 64)
print("How many questions do you actually have?  (correlated: 300 scores, ~50 records' worth of information)")
print("=" * 64)

# GENERATE fake eval data. The `true_*` values are the hidden ground truth;
# `passes_per_record` is the only thing the inference below will see.
rng_cluster = np.random.default_rng(202)
n_records, questions_per_record = 50, 6               # 50 records, 6 questions each = 300 question-scores
true_overall_acc, true_concentration = 0.74, 2.0      # overall 74%; low concentration -> record quality varies widely
true_record_acc = rng_cluster.beta(                   # each record's own true accuracy, drawn from the shared family
    true_overall_acc * true_concentration, (1 - true_overall_acc) * true_concentration, size=n_records)
passes_per_record = rng_cluster.binomial(questions_per_record, true_record_acc)   # passes out of 6 for each record (300 questions in all)

# INFERENCE: record-level variation is folded into the equivalent Beta-Binomial likelihood.
CLUSTER_SAMPLE = SAMPLE | dict(draws=4000, tune=4000, chains=4)  # more draws for stable interval/effective-n estimates
with pm.Model() as cluster_model:
    overall_accuracy = pm.Beta("overall_accuracy", alpha=2, beta=2)      # the headline number we want to estimate
    concentration = pm.Gamma("concentration", alpha=2, beta=0.1)         # how tightly records cluster — learned, not assumed
    # Collapsed form of: record_accuracy ~ Beta(...), then passes ~ Binomial(...).
    pm.BetaBinomial("obs", n=questions_per_record,
                    alpha=overall_accuracy * concentration,
                    beta=(1 - overall_accuracy) * concentration,
                    observed=passes_per_record)
    cluster_trace = pm.sample(**CLUSTER_SAMPLE, target_accept=0.95)

# overall accuracy reads straight off the posterior — no logit, and record accuracies are integrated out
overall_acc_draws = cluster_trace.posterior["overall_accuracy"].values.ravel()
concentration_draws = cluster_trace.posterior["concentration"].values.ravel()

n_questions_correct = int(passes_per_record.sum())
naive_cluster = st.beta(2 + n_questions_correct, 2 + n_records * questions_per_record - n_questions_correct)   # pretend all 300 questions are independent (Beta(2,2))
naive_lo, naive_hi = naive_cluster.ppf([0.025, 0.975])
clustered_lo, clustered_hi = ci(overall_acc_draws)
design_effect = (overall_acc_draws.std() / naive_cluster.std()) ** 2   # how much the variance inflates
effective_n = n_records * questions_per_record / design_effect         # variance-equivalent question count

print(f"\n true overall accuracy = {true_overall_acc:.3f}   "
      f"observed question rate = {passes_per_record.sum() / (n_records * questions_per_record):.3f} ({n_questions_correct}/{n_records * questions_per_record})")
print(f" concentration posterior mean = {concentration_draws.mean():.2f} (planted {true_concentration})")
print(f"\n {'analysis':<20}{'mean':>7}{'95% interval':>20}{'width':>8}{'n_eff':>7}")
print(f" {'naive (300 iid)':<20}{naive_cluster.mean():>7.3f}"
      f"   [{naive_lo:.3f}, {naive_hi:.3f}]{shown_width(naive_lo, naive_hi):>7.3f}{300:>7}")
print(f" {'clustered (50 rec)':<20}{overall_acc_draws.mean():>7.3f}"
      f"   [{clustered_lo:.3f}, {clustered_hi:.3f}]{shown_width(clustered_lo, clustered_hi):>7.3f}{effective_n:>7.0f}")
print(f"\n clustered interval is {shown_width(clustered_lo, clustered_hi) / shown_width(naive_lo, naive_hi):.2f}x as wide; "
      f"design effect = {design_effect:.2f}")


# ----------------------------------------------------------------------
# EXAMPLE 2 — categories/slices: no-pooling vs partial pooling
# ----------------------------------------------------------------------
print("\n" + "=" * 64)
print("Can you trust a slice of only five examples?  (sparse slices: partial pooling vs no pooling)")
print("=" * 64)

# GENERATE fake eval data. `true_slice_acc` is the hidden ground truth;
# `slice_correct` (the counts) is the only thing the inference below will see.
true_pop_mean, true_concentration = 0.80, 15.0
n_slices = 8
slice_sizes = np.array([60, 60, 50, 40, 12, 8, 6, 5])   # examples per slice — note the thin tail
true_slice_acc = RNG.beta(true_pop_mean * true_concentration,           # each slice's true accuracy
                          (1 - true_pop_mean) * true_concentration, size=n_slices)
slice_correct = RNG.binomial(slice_sizes, true_slice_acc)   # correct count per slice

# INFERENCE: each slice's accuracy is drawn from a shared family — all LEARNED from the data.
with pm.Model() as pooling_model:
    pop_mean = pm.Beta("pop_mean", alpha=2, beta=2)                   # the overall accuracy all slices share
    concentration = pm.Gamma("concentration", alpha=2, beta=0.1)   # how tightly slices hug it — learned (prior mean ~20)
    slice_acc = pm.Beta("slice_acc", alpha=pop_mean * concentration,         # each slice's own accuracy, tied to the family above
                        beta=(1 - pop_mean) * concentration, shape=n_slices)
    # likelihood: each slice's correct count follows its accuracy; `observed=` feeds in the data
    pm.Binomial("correct", n=slice_sizes, p=slice_acc, observed=slice_correct)
    pooling_trace = pm.sample(**SAMPLE)                    # that tie is what anchors the thin slices

slice_acc_draws = pooling_trace.posterior["slice_acc"].values.reshape(-1, n_slices)
partial_pool = slice_acc_draws.mean(axis=0)               # each slice, borrowing from the rest
partial_ci = np.percentile(slice_acc_draws, [2.5, 97.5], axis=0).T
no_pool = slice_correct / slice_sizes                     # each slice alone — trusts 5 examples too much
complete_pool = slice_correct.sum() / slice_sizes.sum()   # the opposite extreme: ignore the slices entirely

print(f"\n complete-pool estimate (one number for all): {complete_pool:.3f}")
print(f"\n {'slice':>5} {'n':>4} {'true':>6} {'no-pool':>8} {'partial':>8} {'95% interval':>18}")
for i in range(n_slices):
    print(f" {i:>5} {slice_sizes[i]:>4} {true_slice_acc[i]:>6.3f}"
          f" {no_pool[i]:>8.3f} {partial_pool[i]:>8.3f}"
          f"   [{partial_ci[i, 0]:.3f}, {partial_ci[i, 1]:.3f}]")

rmse = lambda est: np.sqrt(np.mean((est - true_slice_acc) ** 2))
is_sparse = slice_sizes < 15
print(f"\n RMSE vs truth   no-pool={rmse(no_pool):.4f}   partial={rmse(partial_pool):.4f}")
print(f" RMSE on sparse slices (n<15)"
      f"   no-pool={np.sqrt(np.mean((no_pool[is_sparse]-true_slice_acc[is_sparse])**2)):.4f}"
      f"   partial={np.sqrt(np.mean((partial_pool[is_sparse]-true_slice_acc[is_sparse])**2)):.4f}")


# ----------------------------------------------------------------------
# EXAMPLE 3 — comparing two models, paired on the same questions
# ----------------------------------------------------------------------
print("\n" + "=" * 64)
print("Is the new version actually better?  (two models, paired: P(B better than A))")
print("=" * 64)

# GENERATE fake eval data: both models on the SAME questions, B truly a little better.
# `scores_a`, `scores_b` (the 0/1 outcomes) are the only thing the inference below will see.
n_questions = 100
true_base_logit, true_gap_logit, true_question_spread = 0.5, 0.50, 2.5   # gap=0.5 logit -> B a bit better; spread=2.5 -> questions vary a LOT
question_difficulty = RNG.normal(0, true_question_spread, size=n_questions)
scores_a = RNG.binomial(1, to_prob(true_base_logit + question_difficulty))
scores_b = RNG.binomial(1, to_prob(true_base_logit + question_difficulty + true_gap_logit))

# stack A's rows then B's into one long vector, tagging which question and which model each row is
question_of_row = np.tile(np.arange(n_questions), 2)  # which question each row is: q-ids 0..n-1 for A's rows, then again for B's
is_model_b = np.concatenate([np.zeros(n_questions), np.ones(n_questions)])          # 0 for an A row, 1 for a B row
scores = np.concatenate([scores_a, scores_b]).astype(float)

# INFERENCE on the log-odds (logit) scale — the natural scale for a difference between two rates.
# Every pm.* line declares an unknown; pm.sample() works backwards from `scores`.
with pm.Model() as paired_model:
    base_logit = pm.Normal("base_logit", mu=0, sigma=1.5)          # overall difficulty; σ=1.5 logits, so ±2σ ≈ 5-95% accuracy
    gap_logit = pm.Normal("gap_logit", mu=0, sigma=1.0)            # the prize: how much better B is — centred on 0, no edge assumed
    question_spread = pm.HalfNormal("question_spread", sigma=2.5)   # how widely questions vary in difficulty — learned (data pins it down)
    question_effect = pm.Normal("question_effect", mu=0, sigma=question_spread, shape=n_questions)  # each question's own difficulty, shared by A and B
    logit_p = base_logit + question_effect[question_of_row] + gap_logit * is_model_b   # B's rows get the extra gap; A's don't
    # likelihood: each row's 0/1 follows logit_p; `observed=` feeds in the data
    pm.Bernoulli("obs", logit_p=logit_p, observed=scores)
    paired_trace = pm.sample(**SAMPLE, target_accept=0.95)

post = paired_trace.posterior
base_draws = post["base_logit"].values.ravel()
gap_draws = post["gap_logit"].values.ravel()
question_draws = post["question_effect"].values.reshape(-1, n_questions)
# turn the paired model into an interpretable accuracy-gap posterior:
acc_a = to_prob(base_draws[:, None] + question_draws).mean(axis=1)
acc_b = to_prob(base_draws[:, None] + question_draws + gap_draws[:, None]).mean(axis=1)
paired_gap = acc_b - acc_a

print(f"\n true gap (logit) = {true_gap_logit:.2f}   "
      f"observed A={scores_a.mean():.3f}  B={scores_b.mean():.3f}")
print(f"\n PAIRED model:")
print(f"   accuracy gap (B-A): mean={paired_gap.mean():.3f}  "
      f"95% CrI=[{ci(paired_gap)[0]:.3f}, {ci(paired_gap)[1]:.3f}]"
      f"  width={shown_width(ci(paired_gap)[0], ci(paired_gap)[1]):.3f}")
print(f"   P(B better than A) = {(gap_draws > 0).mean():.3f}")

# naive UNPAIRED comparison: two independent Beta-Binomials on totals
naive_a = st.beta(1 + scores_a.sum(), 1 + (n_questions - scores_a.sum()))
naive_b = st.beta(1 + scores_b.sum(), 1 + (n_questions - scores_b.sum()))
unpaired_gap = naive_b.rvs(40000, random_state=1) - naive_a.rvs(40000, random_state=2)
print(f"\n UNPAIRED Beta-Binomial:")
print(f"   accuracy gap (B-A): mean={unpaired_gap.mean():.3f}  "
      f"95% CrI=[{ci(unpaired_gap)[0]:.3f}, {ci(unpaired_gap)[1]:.3f}]  width={shown_width(ci(unpaired_gap)[0], ci(unpaired_gap)[1]):.3f}")
print(f"   P(B better than A) = {(unpaired_gap > 0).mean():.3f}")
print(f"\n correlation of A,B outcomes across questions = "
      f"{np.corrcoef(scores_a, scores_b)[0,1]:.3f}  (this is what pairing exploits)")


# ----------------------------------------------------------------------
# EXAMPLE 4 — the judge is a fallible instrument (measurement error)
# ----------------------------------------------------------------------
print("\n" + "=" * 64)
print("Can you trust the model doing the grading?  (correcting for an imperfect LLM judge)")
print("=" * 64)

# GENERATE fake data. The `true_*` values are the hidden ground truth; the inference below
# sees only the counts: judge_positives, judge_hits_good, judge_hits_bad.
rng_judge = np.random.default_rng(3)            # local seed: a representative draw
true_acc, true_sensitivity, true_specificity = 0.85, 0.92, 0.85
n_eval = 400
judge_rate_true = true_sensitivity * true_acc + (1 - true_specificity) * (1 - true_acc)
judge_positives = rng_judge.binomial(n_eval, judge_rate_true)   # judge's positive count on the full eval

# small human-labelled calibration set
n_known_good, n_known_bad = 80, 60
judge_hits_good = rng_judge.binomial(n_known_good, true_sensitivity)   # judge agrees on truly-correct
judge_hits_bad = rng_judge.binomial(n_known_bad, true_specificity)     # judge agrees on truly-incorrect

# TABLE ROW 1 (naive): take the judge's count as truth — the same Beta(2,2) update as Example 1, correcting for the judge not at all
naive_mean, (naive_lo, naive_hi) = beta_posterior(judge_positives, n_eval)

# INFERENCE only — the data enters through the three `observed=` arguments below;
# accuracy/sensitivity/specificity are all LEARNED.
with pm.Model() as judge_model:
    accuracy = pm.Beta("accuracy", alpha=2, beta=2)            # true accuracy — what we want (weak centred prior, as in Example 1)
    # sensitivity/specificity stay uniform Beta(1,1): the 140 calibration labels dominate them, and a
    # prior pulling them toward 0.5 would lean toward the near-chance-judge region this section warns about.
    sensitivity = pm.Beta("sensitivity", alpha=1, beta=1)      # judge's hit rate on genuinely good answers (uniform prior)
    specificity = pm.Beta("specificity", alpha=1, beta=1)      # judge's hit rate on genuinely bad answers (uniform prior)
    # likelihoods 1 & 2 — pin the judge's two habits against the human-labelled calibration set:
    pm.Binomial("cal_good", n=n_known_good, p=sensitivity, observed=judge_hits_good)  # 80 known-good answers
    pm.Binomial("cal_bad", n=n_known_bad, p=specificity, observed=judge_hits_bad)     # 60 known-bad answers
    judge_rate = sensitivity * accuracy + (1 - specificity) * (1 - accuracy)   # what a fallible judge ends up reporting
    # likelihood 3 — tie that to the judge's actual count on the full eval:
    pm.Binomial("obs", n=n_eval, p=judge_rate, observed=judge_positives)
    judge_trace = pm.sample(**SAMPLE)               # uncertainty in the judge flows through into accuracy

# TABLE ROW 2 (corrected): read the accuracy posterior the model learned, working back through the judge
acc_draws = judge_trace.posterior["accuracy"].values.ravel()
print(f"\n true accuracy = {true_acc:.3f}   judge reports rate ~ {judge_rate_true:.3f}")
print(f" observed judge-positive count = {judge_positives}/{n_eval} = {judge_positives/n_eval:.3f}")
print(f" calibration: judge passed {judge_hits_good}/{n_known_good} known-good = {judge_hits_good/n_known_good:.3f} "
      f"(true sens {true_sensitivity});  caught {judge_hits_bad}/{n_known_bad} known-bad = {judge_hits_bad/n_known_bad:.3f} (true spec {true_specificity})")
print(f"\n naive (judge=truth):   mean={naive_mean:.3f}  "
      f"95% CrI=[{naive_lo:.3f}, {naive_hi:.3f}]  width={shown_width(naive_lo, naive_hi):.3f}")
print(f" corrected (modelled):  mean={acc_draws.mean():.3f}  "
      f"95% CrI=[{ci(acc_draws)[0]:.3f}, {ci(acc_draws)[1]:.3f}]  width={shown_width(ci(acc_draws)[0], ci(acc_draws)[1]):.3f}")
print(f"\n true value {true_acc} inside naive CrI?     "
      f"{naive_lo <= true_acc <= naive_hi}")
print(f" true value {true_acc} inside corrected CrI? "
      f"{ci(acc_draws)[0] <= true_acc <= ci(acc_draws)[1]}")

# ----------------------------------------------------------------------
# REPEATED SAMPLING — how many times to ask each question (the K knob)
# ----------------------------------------------------------------------
print("\n" + "=" * 64)
print("How many times should you ask each question?  (uncertainty in overall accuracy vs samples-per-question K)")
print("=" * 64)

# GENERATE the question bank. `true_question_acc` is the hidden ground truth.
rng_repeat = np.random.default_rng(21)
n_question_bank = 80
true_mean_rep, true_concentration_rep = 0.75, 6.0
gen_a, gen_b = true_mean_rep * true_concentration_rep, (1 - true_mean_rep) * true_concentration_rep
true_question_acc = rng_repeat.beta(gen_a, gen_b, size=n_question_bank)   # each question's true success prob
pop_var = gen_a * gen_b / ((gen_a + gen_b) ** 2 * (gen_a + gen_b + 1))
floor_sd = np.sqrt(pop_var / n_question_bank)        # irreducible: set by n questions
# floor_sd uses the generating Beta's variance, not the realised variance of the 80 drawn accuracies;
# the two agree to ~0.0002 here, so the floor we plot is effectively the one in the data.
mean_within_var = float(np.mean(true_question_acc * (1 - true_question_acc)))

K_values = [1, 2, 3, 5, 10, 30]
posterior_sd = []
for K in K_values:                       # re-run each question K times, watch error shrink
    question_scores = rng_repeat.binomial(K, true_question_acc)   # observed passes out of K — all the inference sees
    # INFERENCE: each question's accuracy comes from a shared family — all LEARNED from the data.
    with pm.Model() as repeat_model:
        pop_mean = pm.Beta("pop_mean", alpha=2, beta=2)         # overall accuracy — the thing we're pinning down
        concentration = pm.Gamma("concentration", alpha=2, beta=0.1)   # how alike the questions are — learned (prior mean ~20)
        # collapsed Beta-Binomial: integrates each question's own accuracy out (same model as the clustering example)
        pm.BetaBinomial("obs", n=K, alpha=pop_mean * concentration,
                        beta=(1 - pop_mean) * concentration, observed=question_scores)
        repeat_trace = pm.sample(draws=1200, tune=1200, chains=4, cores=1,
                     random_seed=100 + K, progressbar=False, target_accept=0.95)
    posterior_sd.append(float(repeat_trace.posterior["pop_mean"].values.std()))  # uncertainty in accuracy — it plateaus

print(f"\n true mean = {true_question_acc.mean():.3f}   floor SD (set by n={n_question_bank}) = {floor_sd:.4f}")
print(f"\n {'K':>3} {'posterior SD of accuracy':>26}")
for K, sd in zip(K_values, posterior_sd):
    print(f" {K:>3} {sd:>26.4f}")


# ----------------------------------------------------------------------
# DESIGN BY SIMULATION — how many questions to reliably see a real gap?
# ----------------------------------------------------------------------
print("\n" + "=" * 64)
print("How big an eval do you actually need?  (how many questions to be 95% sure B > A?)")
print("=" * 64)

rng_design = np.random.default_rng(11)

def design_power(acc_a, acc_b, n_questions, trials=3000, draws=800, threshold=0.95):
    """Fraction of n-question evals that reach P(B>A) >= threshold given the
    true accuracies. i.e. if B really is better by (acc_b - acc_a), how often
    would an eval this size notice? Conjugate Beta-Binomial, no MCMC, so it's fast.
    trials = whole evals simulated; draws = posterior draws per eval; threshold = the bar you'd act on."""
    # GENERATE many whole evals at the planted gap (each row is one simulated eval):
    sim_a = rng_design.binomial(n_questions, acc_a, trials)   # model A's correct count in each eval
    sim_b = rng_design.binomial(n_questions, acc_b, trials)   # model B's correct count in each eval
    # For each eval, form the Beta-Binomial posterior belief about each model's accuracy (as in Example 1):
    belief_a = np.asarray(st.beta.rvs(1 + sim_a[:, None], 1 + n_questions - sim_a[:, None],
                                      size=(trials, draws), random_state=rng_design))
    belief_b = np.asarray(st.beta.rvs(1 + sim_b[:, None], 1 + n_questions - sim_b[:, None],
                                      size=(trials, draws), random_state=rng_design))
    return float(((belief_b > belief_a).mean(axis=1) >= threshold).mean())  # how often P(B > A) clears the bar

question_counts = [100, 200, 400, 800, 1600, 3200]
power_big_gap, power_small_gap = [], []
for n in question_counts:
    power_big_gap.append(design_power(0.70, 0.75, n))      # 5-point true gap
    power_small_gap.append(design_power(0.70, 0.725, n))   # 2.5-point true gap

print(f"\n {'n':>5} {'5pt gap':>9} {'2.5pt gap':>10}")
for n, p5, p25 in zip(question_counts, power_big_gap, power_small_gap):
    print(f" {n:>5} {p5:>9.3f} {p25:>10.3f}")


# ----------------------------------------------------------------------
# PRIOR SENSITIVITY — do the conclusions survive a different prior?
# ----------------------------------------------------------------------
print("\n" + "=" * 64)
print("PRIOR SENSITIVITY  Judge model (true acc = 0.85) under varied priors on acc")
print("=" * 64)

priors = {   # each prior, as (imagined wins, imagined losses) on the accuracy
    "uniform Beta(1,1)":      (1, 1),
    "Jeffreys Beta(.5,.5)":   (0.5, 0.5),
    "weak centred Beta(2,2)": (2, 2),
    "strong opt. Beta(8,2)":  (8, 2),
    "strong pess. Beta(2,8)": (2, 8),
}
prior_rows = []
for name, (prior_wins, prior_losses) in priors.items():
    with pm.Model() as prior_test_model:
        accuracy = pm.Beta("accuracy", alpha=prior_wins, beta=prior_losses)
        sensitivity = pm.Beta("sensitivity", alpha=1, beta=1)
        specificity = pm.Beta("specificity", alpha=1, beta=1)
        pm.Binomial("cal_good", n=n_known_good, p=sensitivity, observed=judge_hits_good)
        pm.Binomial("cal_bad", n=n_known_bad, p=specificity, observed=judge_hits_bad)
        pm.Binomial("obs", n=n_eval, p=sensitivity * accuracy + (1 - specificity) * (1 - accuracy), observed=judge_positives)
        prior_test_trace = pm.sample(draws=1600, tune=1600, chains=4, cores=1,
                         random_seed=7, progressbar=False, target_accept=0.99)
    s = prior_test_trace.posterior["accuracy"].values.ravel()
    prior_rows.append((name, s.mean(), np.percentile(s, 2.5), np.percentile(s, 97.5)))

print(f"\n {'prior on acc':24s} {'post mean':>9} {'95% CrI':>20}")
for name, m, lo, hi in prior_rows:
    print(f" {name:24s} {m:>9.3f}   [{lo:.3f}, {hi:.3f}]")


# ----------------------------------------------------------------------
# CALIBRATION — does a nominal 95% interval actually contain the truth 95%?
# ----------------------------------------------------------------------
print("\n" + "=" * 64)
print("CALIBRATION  Coverage of nominal 95% intervals (closed form, many trials)")
print("=" * 64)

rng_cal = np.random.default_rng(123)

def wald_interval(correct, total):
    p = correct / total
    se = np.sqrt(p * (1 - p) / total)
    return p - 1.96 * se, p + 1.96 * se

def beta_interval(correct, total, prior_wins=1, prior_losses=1):
    d = st.beta(prior_wins + correct, prior_losses + total - correct)
    return d.ppf(0.025), d.ppf(0.975)

def coverage(true_acc, total, trials=20000):
    correct = rng_cal.binomial(total, true_acc, trials)
    wlo, whi = wald_interval(correct, total)
    blo, bhi = beta_interval(correct, total)
    w = float(np.mean((wlo <= true_acc) & (true_acc <= whi)))
    b = float(np.mean((blo <= true_acc) & (true_acc <= bhi)))
    return w, b

sample_sizes = [25, 50, 100]
true_accs = [0.5, 0.8, 0.95]
coverage_by_case = {}   # (total, true_acc) -> (wald_cov, bayes_cov)
print(f"\n {'n':>5} {'true_p':>7} {'Wald':>8} {'Bayes':>8}")
for total in sample_sizes:
    for true_p in true_accs:
        w, b = coverage(true_p, total)
        coverage_by_case[(total, true_p)] = (w, b)
        print(f" {total:>5} {true_p:>7} {w:>8.3f} {b:>8.3f}")


# ----------------------------------------------------------------------
# FIGURES — reuse the computations above so plots match the numbers
# ----------------------------------------------------------------------
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
from matplotlib.lines import Line2D
from pathlib import Path

# Write figures to <project root>/figures regardless of the working directory.
FIGDIR = Path(__file__).resolve().parent.parent / "figures"
FIGDIR.mkdir(exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 130, "font.size": 11, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25,
    "grid.linewidth": 0.6, "font.family": "DejaVu Sans",
})
NAVY, ORANGE, GREY = "#1f3a5f", "#d1701a", "#8a8f98"

# Figure 1: partial-pooling forest plot (Example 2)
order = np.argsort(slice_sizes)             # smallest n at the top
lo = np.percentile(slice_acc_draws, 2.5, axis=0)
hi = np.percentile(slice_acc_draws, 97.5, axis=0)

fig, ax = plt.subplots(figsize=(8.2, 5.0))
ax.axvline(complete_pool, color=GREY, ls="--", lw=1.2)
for row, i in enumerate(order):
    ax.annotate("", xy=(float(partial_pool[i]), row), xytext=(float(no_pool[i]), row),
                arrowprops=dict(arrowstyle="->", color=GREY, lw=1.0, alpha=0.7))
    ax.errorbar(partial_pool[i], row,
                xerr=[[partial_pool[i] - lo[i]], [hi[i] - partial_pool[i]]],
                fmt="o", color=NAVY, ecolor=NAVY, elinewidth=1.6,
                capsize=3, ms=6, zorder=3)
    ax.plot(no_pool[i], row, "X", color=ORANGE, ms=8, zorder=3)
    ax.plot(true_slice_acc[i], row, "|", color="black", ms=16, mew=2, zorder=4)
ax.set_yticks(range(n_slices))
ax.set_yticklabels([f"slice {i}  (n={slice_sizes[i]})" for i in order])
ax.set_xlabel("accuracy")
# x-limits from the data (lowest no-pool point or lower CrI bound, minus a margin) so a different seed can't clip
x_low = min(float(no_pool.min()), float(lo.min())) - 0.05
ax.set_xlim(x_low, 1.02)
ax.set_title("Partial pooling pulls noisy slices toward the population",
             loc="left", fontsize=12.5, weight="bold")
ax.legend(handles=[
    Line2D([], [], color=ORANGE, marker="X", ls="", ms=8, label="no-pool estimate"),
    Line2D([], [], color=NAVY, marker="o", ls="", ms=6, label="partial-pool (95% CrI)"),
    Line2D([], [], color="black", marker="|", ls="", ms=12, mew=2, label="true value"),
    Line2D([], [], color=GREY, ls="--", label="population mean"),
], loc="upper left", frameon=False, fontsize=9.5)
fig.tight_layout(); fig.savefig(FIGDIR / "partial-pooling-forest.png", bbox_inches="tight")
print(f"saved {FIGDIR / 'partial-pooling-forest.png'}")

# Figure 2: posterior of the accuracy gap B - A (Example 3)
xs = np.linspace(min(paired_gap.min(), unpaired_gap.min()),
                 max(paired_gap.max(), unpaired_gap.max()), 400)
kde_p, kde_u = gaussian_kde(paired_gap)(xs), gaussian_kde(unpaired_gap)(xs)

fig, ax = plt.subplots(figsize=(8.2, 5.0))
ax.axvline(0, color="black", lw=1.0, alpha=0.7)
ax.plot(xs, kde_u, color=ORANGE, lw=2.0, label=f"unpaired   P(B>A)={(unpaired_gap>0).mean():.2f}")
ax.fill_between(xs, kde_u, color=ORANGE, alpha=0.10)
ax.plot(xs, kde_p, color=NAVY, lw=2.2, label=f"paired      P(B>A)={(paired_gap>0).mean():.2f}")
ax.fill_between(xs[xs >= 0], kde_p[xs >= 0], color=NAVY, alpha=0.22)
ax.set_xlabel("accuracy gap  (model B − model A)")
ax.set_ylabel("posterior density"); ax.set_yticks([])
ax.set_title("How much better is B?  The whole posterior, not a point",
             loc="left", fontsize=12.5, weight="bold")
ax.annotate("shaded mass = P(B better than A)",
            xy=(0.03, gaussian_kde(paired_gap)(0.03)[0] * 0.5),
            xytext=(0.14, max(kde_p) * 0.72), fontsize=9.5, color=NAVY,
            arrowprops=dict(arrowstyle="->", color=NAVY, lw=1.0))
ax.legend(loc="upper left", frameon=False, fontsize=10)
fig.tight_layout(); fig.savefig(FIGDIR / "model-comparison-posterior.png", bbox_inches="tight")
print(f"saved {FIGDIR / 'model-comparison-posterior.png'}")

# Figure 3: design-by-simulation power curve (Design section)
fig, ax = plt.subplots(figsize=(8.2, 5.0))
ax.plot(question_counts, power_big_gap, "o-", color=NAVY, lw=2.2, ms=6,
        label="true gap = 5 points  (0.70 vs 0.75)")
ax.plot(question_counts, power_small_gap, "s--", color=ORANGE, lw=2.0, ms=6,
        label="true gap = 2.5 points  (0.70 vs 0.725)")
ax.set_xscale("log")
ax.set_xticks(question_counts); ax.set_xticklabels([str(n) for n in question_counts])
ax.set_ylim(0, 1.02)
ax.set_xlabel("number of eval questions (n)")
ax.set_ylabel("P(reaching 95% confidence that B > A)")
ax.set_title("How big an eval do you need to see a real improvement?",
             loc="left", fontsize=12.5, weight="bold")
ax.legend(loc="upper left", frameon=False, fontsize=9.5)
fig.tight_layout(); fig.savefig(FIGDIR / "design-power-curve.png", bbox_inches="tight")
print(f"saved {FIGDIR / 'design-power-curve.png'}")

# Figure 4: repeated-sampling diminishing returns (Repeated-sampling section)
samples_dense = np.linspace(1, 30, 200)
analytic_se = np.sqrt(pop_var / n_question_bank + mean_within_var / (n_question_bank * samples_dense))
fig, ax = plt.subplots(figsize=(8.2, 5.0))
ax.axhline(floor_sd, color=GREY, ls="--", lw=1.2,
           label=f"floor set by n={n_question_bank} questions")
ax.plot(samples_dense, analytic_se, color=ORANGE, lw=1.8, alpha=0.85,
        label="analytic standard error")
ax.plot(K_values, posterior_sd, "o", color=NAVY, ms=7, zorder=3,
        label="Bayesian posterior SD")
ax.set_xlabel("samples per question (K)")
ax.set_ylabel("uncertainty in overall accuracy (SD)")
ax.set_ylim(0, max(posterior_sd) * 1.12)
ax.set_title("More re-runs per question hit a floor",
             loc="left", fontsize=12.5, weight="bold")
ax.legend(loc="upper right", frameon=False, fontsize=9.5)
fig.tight_layout(); fig.savefig(FIGDIR / "repeated-sampling-floor.png", bbox_inches="tight")
print(f"saved {FIGDIR / 'repeated-sampling-floor.png'}")

# Figure 5: calibration — coverage of nominal 95% intervals at the boundary case
fig, ax = plt.subplots(figsize=(8.2, 5.0))
wald_cov = [coverage_by_case[(n, 0.95)][0] for n in sample_sizes]
bayes_cov = [coverage_by_case[(n, 0.95)][1] for n in sample_sizes]
x = np.arange(len(sample_sizes)); w = 0.36
ax.axhline(0.95, color=GREY, ls="--", lw=1.2, label="nominal 95%")
ax.bar(x - w/2, wald_cov, w, color=ORANGE, label="Wald interval")
ax.bar(x + w/2, bayes_cov, w, color=NAVY, label="Bayesian interval")
for xi, v in zip(x - w/2, wald_cov):
    ax.text(xi, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=9, color=ORANGE)
for xi, v in zip(x + w/2, bayes_cov):
    ax.text(xi, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=9, color=NAVY)
ax.set_xticks(x); ax.set_xticklabels([f"n={n}" for n in sample_sizes])
ax.set_ylim(0.6, 1.0)
ax.set_ylabel("actual coverage of a '95%' interval")
ax.set_title("Does a 95% interval contain the truth 95% of the time? (true acc = 0.95)",
             loc="left", fontsize=12, weight="bold")
ax.legend(loc="lower right", frameon=True, fontsize=9.5,
          facecolor="white", edgecolor=GREY, framealpha=1.0).set_zorder(10)
fig.tight_layout(); fig.savefig(FIGDIR / "calibration-coverage.png", bbox_inches="tight")
print(f"saved {FIGDIR / 'calibration-coverage.png'}")

print("\nDONE.")
