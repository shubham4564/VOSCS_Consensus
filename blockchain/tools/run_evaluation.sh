#!/usr/bin/env bash
# run_evaluation.sh
# Comprehensive evaluation: ablation + baseline comparison
# Sweeps: alpha in [0, 0.49], N in [10, 200], rounds in [250, 5000]
# Multi-seed for confidence intervals.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
ROOT_OUT="${REPO_ROOT}/reports/ccs_eval"
SEEDS=(42 43 44 45 46)        # 5 seeds for CIs; bump to 10+ for camera-ready
NODES_SWEEP=(10 25 50 100 200)
ROUNDS_SWEEP=(250 1000 2500 5000)
ATTACKER_FRACTIONS=(0.0 0.1 0.2 0.33 0.4 0.49)
COMMITTEE_K=7                  # maps to BFT f=2 (3f+1=7)
METADATA="clustered_attackers"

mkdir -p "${ROOT_OUT}"
echo "Repo root: ${REPO_ROOT}"
echo "Writing all outputs under ${ROOT_OUT}"
echo "Seeds: ${SEEDS[*]}"
echo

# ==================================================================
# STAGE A: Solver study (small M, exact oracle is tractable)
#   Answers RQ5: how close is SA to exact, and does it beat greedy?
# ==================================================================
# echo "===== STAGE A: solver study ====="
# for seed in "${SEEDS[@]}"; do
#   python -m tools.evaluation_overhaul \
#     --skip-strategy-comparison \
#     --solver-study \
#     --solver-study-candidate-sizes 8 10 12 14 16 \
#     --solver-study-seed-count 20 \
#     --committee-k "${COMMITTEE_K}" \
#     --exact-oracle-max-candidates 16 \
#     --metadata-profile "${METADATA}" \
#     --attacker-fraction 0.33 \
#     --seed "${seed}" \
#     --output-dir "${ROOT_OUT}/solver_study/seed_${seed}"
# done

# ==================================================================
# STAGE B: Ablation of objective terms (RQ3)
#   Isolates which component of the objective drives diversity.
#   Use evaluation_overhaul.py directly because comparative_evaluation
#   doesn't expose ablation flags via CLI.
# ==================================================================
# echo "===== STAGE B: ablation ====="
# for seed in "${SEEDS[@]}"; do
#   for rounds in 250 1000 5000; do
#     python -m tools.evaluation_overhaul \
#       --skip-strategy-comparison \
#       --committee-ablation-study \
#       --committee-ablation-ids full_objective lambda_zero w_freq_zero no_fallback score_only \
#       --nodes 100 --rounds "${rounds}" \
#       --committee-k "${COMMITTEE_K}" \
#       --metadata-profile "${METADATA}" \
#       --attacker-fraction 0.33 \
#       --seed "${seed}" \
#       --output-dir "${ROOT_OUT}/ablation/rounds_${rounds}/seed_${seed}"
#   done
# done

# ==================================================================
# STAGE C: Baseline comparison sweep over (N, rounds)
#   The "literature" stage in committee_comparative_evaluation runs
#   the full baseline comparison. We sweep N and rounds externally.
# ==================================================================
# echo "===== STAGE C: baseline comparison sweep ====="
# for seed in "${SEEDS[@]}"; do
#   for nodes in "${NODES_SWEEP[@]}"; do
#     for rounds in "${ROUNDS_SWEEP[@]}"; do
#       # Skip combinations that are needlessly expensive or pointless:
#       #   - 200 nodes x 5000 rounds with 5 seeds is the budget killer;
#       #     keep it but only at one rounds value if you're tight.
#       #   - 10 nodes x 5000 rounds is fine but adds little signal.
#       python -m tools.committee_comparative_evaluation \
#         --skip-reduced --skip-solver \
#         --literature-nodes "${nodes}" \
#         --literature-rounds "${rounds}" \
#         --security-nodes "${nodes}" \
#         --security-rounds "${rounds}" \
#         --committee-k "${COMMITTEE_K}" \
#         --metadata-profile "${METADATA}" \
#         --attacker-fraction 0.2 \
#         --security-attacker-fractions "${ATTACKER_FRACTIONS[@]}" \
#         --security-outage-probabilities 0.1 0.25 0.5 \
#         --security-withholding-probabilities 0.1 0.25 0.5 \
#         --seed "${seed}" \
#         --output-dir "${ROOT_OUT}/comparison/N${nodes}_R${rounds}/seed_${seed}" \
#         --skip-plots
#     done
#   done
# done

# ==================================================================
# STAGE D: Long-horizon fairness study (per CCS reviewer item #6)
#   5000 rounds with proposer-share Gini trace.
#   This is the regime where reputation should drift / collapse.
# ==================================================================
echo "===== STAGE D: long-horizon fairness ====="
for seed in "${SEEDS[@]}"; do
  python -m tools.committee_comparative_evaluation \
    --skip-reduced --skip-literature --skip-solver --skip-security \
    --run-long-horizon \
    --long-horizon-rounds 5000 \
    --long-horizon-trace-interval 250 \
    --long-horizon-attacker-fractions 0.0 0.2 0.33 0.4 \
    --long-horizon-strategies committee_quantum committee_vrf_stake \
                              committee_reputation committee_composite_greedy \
                              committee_uniform committee_fairness_only \
    --security-nodes 100 \
    --committee-k "${COMMITTEE_K}" \
    --metadata-profile "${METADATA}" \
    --seed "${seed}" \
    --output-dir "${ROOT_OUT}/long_horizon/seed_${seed}" \
    --skip-plots
done

# ==================================================================
# STAGE E: BFT-threshold k sweep (per CCS reviewer item: k=4,7,10,13)
#   Run only one (N, rounds, seed) point per k; k itself is the variable.
# ==================================================================
echo "===== STAGE E: committee-size sweep ====="
for seed in "${SEEDS[@]}"; do
  for k in 4 7 10 13; do
    python -m tools.committee_comparative_evaluation \
      --skip-reduced --skip-solver \
      --literature-nodes 100 --literature-rounds 1000 \
      --security-nodes 100 --security-rounds 1000 \
      --committee-k "${k}" \
      --committee-k-values "${k}" \
      --metadata-profile "${METADATA}" \
      --attacker-fraction 0.33 \
      --security-attacker-fractions "${ATTACKER_FRACTIONS[@]}" \
      --seed "${seed}" \
      --output-dir "${ROOT_OUT}/k_sweep/k${k}/seed_${seed}" \
      --skip-plots
  done
done

echo
echo "===== DONE ====="
echo "Outputs under: ${ROOT_OUT}"
echo "Per-stage summaries: ${ROOT_OUT}/{solver_study,ablation,comparison,long_horizon,k_sweep}/"s