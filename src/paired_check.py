import numpy as np, pandas as pd
import bayes_evals as be

# Reconstruct EXACTLY the Example 3 data from eval_stats.py (same seeds/order).
RNG = np.random.default_rng(7)
to_prob = lambda x: 1/(1+np.exp(-x))

# --- replay the RNG draws in the same order as eval_stats.py up to Example 3 ---
# Ex1 uses fixed counts (no RNG). Ex2 consumes two draws:
n_slices = 8; slice_sizes = np.array([60, 60, 50, 40, 12, 8, 6, 5])
true_slice_acc = RNG.beta(0.8*15, 0.2*15, size=n_slices)
slice_correct = RNG.binomial(slice_sizes, true_slice_acc)
# Ex3:
n_questions = 100; true_base_logit, true_gap_logit, true_question_spread = 0.5, 0.50, 2.5
question_difficulty = RNG.normal(0, true_question_spread, size=n_questions)
scores_a = RNG.binomial(1, to_prob(true_base_logit + question_difficulty))
scores_b = RNG.binomial(1, to_prob(true_base_logit + question_difficulty + true_gap_logit))

print(f"Example 3 data: A={scores_a.mean():.3f}, B={scores_b.mean():.3f}, corr={np.corrcoef(scores_a, scores_b)[0,1]:.3f}")

df = pd.DataFrame({"A": scores_a, "B": scores_b})
np.random.seed(0)
paired = be.paired_comparisons(df, num_samples=200000)
indep = be.independent_comparisons(df)
# entry [i,j] = P(model i better than model j)
print(f"\nbayes_evals paired   P(B>A) = {paired.loc['B','A']:.3f}")
print(f"bayes_evals indep    P(B>A) = {indep.loc['B','A']:.3f}")
print("\n(eval_stats.py should report roughly: paired P(B>A)=0.72, unpaired=0.66)")
