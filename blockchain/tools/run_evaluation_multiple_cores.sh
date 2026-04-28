#!/usr/bin/env bash
# Parallel evaluation runner with bounded concurrency.
# Default behavior mirrors the current file:
#   - stages A/B/C disabled
#   - stages D/E enabled
#
# Examples:
#   MAX_JOBS=16 ./run_evaluation_multiple_cores.sh
#   ENABLE_STAGE_C=1 MAX_JOBS=32 ./run_evaluation_multiple_cores.sh

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
ROOT_OUT="${REPO_ROOT}/reports/ccs_eval"
SEEDS=(42 43 44 45 46)
NODES_SWEEP=(10 25 50 100 200)
ROUNDS_SWEEP=(250 1000 2500 5000)
ATTACKER_FRACTIONS=(0.0 0.1 0.2 0.33 0.4 0.49)
OUTAGE_PROBABILITIES=(0.1 0.25 0.5)
WITHHOLDING_PROBABILITIES=(0.1 0.25 0.5)
LONG_HORIZON_ATTACKER_FRACTIONS=(0.0 0.2 0.33 0.4)

COMMITTEE_K=7
METADATA="clustered_attackers"

ENABLE_STAGE_A="${ENABLE_STAGE_A:-0}"
ENABLE_STAGE_B="${ENABLE_STAGE_B:-0}"
ENABLE_STAGE_C="${ENABLE_STAGE_C:-0}"
ENABLE_STAGE_D="${ENABLE_STAGE_D:-1}"
ENABLE_STAGE_E="${ENABLE_STAGE_E:-1}"

if command -v nproc >/dev/null 2>&1; then
  DEFAULT_JOBS="$(nproc)"
else
  DEFAULT_JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
fi
MAX_JOBS="${MAX_JOBS:-${DEFAULT_JOBS}}"

mkdir -p "${ROOT_OUT}"
echo "Repo root: ${REPO_ROOT}"
echo "Writing all outputs under ${ROOT_OUT}"
echo "Seeds: ${SEEDS[*]}"
echo "Max parallel jobs: ${MAX_JOBS}"
echo "Enabled stages: A=${ENABLE_STAGE_A} B=${ENABLE_STAGE_B} C=${ENABLE_STAGE_C} D=${ENABLE_STAGE_D} E=${ENABLE_STAGE_E}"
echo

job_count() {
  jobs -pr | wc -l | tr -d ' '
}

run_limited() {
  local label="$1"
  shift
  echo "[launch] ${label}"
  "$@" &
  while [ "$(job_count)" -ge "${MAX_JOBS}" ]; do
    wait -n
  done
}

drain_stage() {
  local stage_name="$1"
  echo "[wait] ${stage_name}"
  while [ "$(job_count)" -gt 0 ]; do
    wait -n
  done
}

cleanup_jobs() {
  local running
  running="$(jobs -pr || true)"
  if [ -n "${running}" ]; then
    echo "[cleanup] terminating background jobs"
    kill ${running} 2>/dev/null || true
  fi
}
trap cleanup_jobs EXIT

# ==================================================================
# STAGE A: Solver study
# Parallelization granularity here is per seed. The inner candidate-size
# and trial loops still live inside evaluation_overhaul.py.
# ==================================================================
if [ "${ENABLE_STAGE_A}" = "1" ]; then
  echo "===== STAGE A: solver study ====="
  for seed in "${SEEDS[@]}"; do
    out="${ROOT_OUT}/solver_study/seed_${seed}"
    run_limited "A seed=${seed}" \
      python -m tools.evaluation_overhaul \
        --skip-strategy-comparison \
        --solver-study \
        --solver-study-candidate-sizes 8 10 12 14 16 \
        --solver-study-seed-count 20 \
        --committee-k "${COMMITTEE_K}" \
        --exact-oracle-max-candidates 16 \
        --metadata-profile "${METADATA}" \
        --attacker-fraction 0.33 \
        --seed "${seed}" \
        --output-dir "${out}"
  done
  drain_stage "stage A"
fi

# ==================================================================
# STAGE B: Ablation
# Parallelization granularity: seed x rounds
# ==================================================================
if [ "${ENABLE_STAGE_B}" = "1" ]; then
  echo "===== STAGE B: ablation ====="
  for seed in "${SEEDS[@]}"; do
    for rounds in 250 1000 5000; do
      out="${ROOT_OUT}/ablation/rounds_${rounds}/seed_${seed}"
      run_limited "B seed=${seed} rounds=${rounds}" \
        python -m tools.evaluation_overhaul \
          --skip-strategy-comparison \
          --committee-ablation-study \
          --committee-ablation-ids full_objective lambda_zero w_freq_zero no_fallback score_only \
          --nodes 100 \
          --rounds "${rounds}" \
          --committee-k "${COMMITTEE_K}" \
          --metadata-profile "${METADATA}" \
          --attacker-fraction 0.33 \
          --seed "${seed}" \
          --output-dir "${out}"
    done
  done
  drain_stage "stage B"
fi

# ==================================================================
# STAGE C: Baseline comparison sweep
#
# To make seed * nodes * rounds * attacker_fraction independent, this
# stage is split into:
#   C1 literature-only jobs
#   C2 witness-collusion jobs
#   C3 attacker-sweep jobs (1 attacker fraction per process)
#   C4 correlated-failure jobs (1 outage probability per process)
#   C5 block-withholding jobs (1 withholding probability per process)
#
# NOTE:
# - security_experiments.py does not expose metadata_profile on its CLI.
#   This script matches your current METADATA only because the default
#   there is also "clustered_attackers".
# ==================================================================
if [ "${ENABLE_STAGE_C}" = "1" ]; then
  echo "===== STAGE C1: literature comparison ====="
  for seed in "${SEEDS[@]}"; do
    for nodes in "${NODES_SWEEP[@]}"; do
      for rounds in "${ROUNDS_SWEEP[@]}"; do
        out="${ROOT_OUT}/comparison/N${nodes}_R${rounds}/seed_${seed}/literature"
        run_limited "C1 seed=${seed} nodes=${nodes} rounds=${rounds}" \
          python -m tools.committee_comparative_evaluation \
            --skip-reduced \
            --skip-solver \
            --skip-security \
            --literature-nodes "${nodes}" \
            --literature-rounds "${rounds}" \
            --committee-k "${COMMITTEE_K}" \
            --metadata-profile "${METADATA}" \
            --attacker-fraction 0.2 \
            --seed "${seed}" \
            --output-dir "${out}" \
            --skip-plots
      done
    done
  done
  drain_stage "stage C1"

  echo "===== STAGE C2: witness collusion ====="
  for seed in "${SEEDS[@]}"; do
    for nodes in "${NODES_SWEEP[@]}"; do
      for rounds in "${ROUNDS_SWEEP[@]}"; do
        out="${ROOT_OUT}/comparison/N${nodes}_R${rounds}/seed_${seed}/security_witness"
        run_limited "C2 seed=${seed} nodes=${nodes} rounds=${rounds}" \
          python -m tools.security_experiments \
            --experiments witness_collusion \
            --witness-collusion-nodes "${nodes}" \
            --attacker-fraction 0.2 \
            --seed "${seed}" \
            --output-dir "${out}"
      done
    done
  done
  drain_stage "stage C2"

  echo "===== STAGE C3: attacker-fraction sweep ====="
  for seed in "${SEEDS[@]}"; do
    for nodes in "${NODES_SWEEP[@]}"; do
      for rounds in "${ROUNDS_SWEEP[@]}"; do
        for af in "${ATTACKER_FRACTIONS[@]}"; do
          out="${ROOT_OUT}/comparison/N${nodes}_R${rounds}/seed_${seed}/security_attacker/af_${af}"
          run_limited "C3 seed=${seed} nodes=${nodes} rounds=${rounds} af=${af}" \
            python -m tools.security_experiments \
              --experiments attacker_sweep \
              --sweep-nodes "${nodes}" \
              --sweep-rounds "${rounds}" \
              --sweep-fractions "${af}" \
              --sweep-committee-k "${COMMITTEE_K}" \
              --include-exact-when-safe \
              --seed "${seed}" \
              --output-dir "${out}"
        done
      done
    done
  done
  drain_stage "stage C3"

  echo "===== STAGE C4: correlated failure ====="
  for seed in "${SEEDS[@]}"; do
    for nodes in "${NODES_SWEEP[@]}"; do
      for rounds in "${ROUNDS_SWEEP[@]}"; do
        for outage in "${OUTAGE_PROBABILITIES[@]}"; do
          out="${ROOT_OUT}/comparison/N${nodes}_R${rounds}/seed_${seed}/security_correlated/p_${outage}"
          run_limited "C4 seed=${seed} nodes=${nodes} rounds=${rounds} outage=${outage}" \
            python -m tools.security_experiments \
              --experiments correlated_failure \
              --corr-nodes "${nodes}" \
              --corr-rounds "${rounds}" \
              --corr-outage-probs "${outage}" \
              --corr-committee-k "${COMMITTEE_K}" \
              --attacker-fraction 0.2 \
              --include-exact-when-safe \
              --seed "${seed}" \
              --output-dir "${out}"
        done
      done
    done
  done
  drain_stage "stage C4"

  echo "===== STAGE C5: block withholding ====="
  for seed in "${SEEDS[@]}"; do
    for nodes in "${NODES_SWEEP[@]}"; do
      for rounds in "${ROUNDS_SWEEP[@]}"; do
        for withholding in "${WITHHOLDING_PROBABILITIES[@]}"; do
          out="${ROOT_OUT}/comparison/N${nodes}_R${rounds}/seed_${seed}/security_withholding/p_${withholding}"
          run_limited "C5 seed=${seed} nodes=${nodes} rounds=${rounds} withholding=${withholding}" \
            python -m tools.security_experiments \
              --experiments block_withholding \
              --withholding-nodes "${nodes}" \
              --withholding-rounds "${rounds}" \
              --withholding-probs "${withholding}" \
              --withholding-committee-k "${COMMITTEE_K}" \
              --include-exact-when-safe \
              --seed "${seed}" \
              --output-dir "${out}"
        done
      done
    done
  done
  drain_stage "stage C5"
fi

# ==================================================================
# STAGE D: Long-horizon fairness
# Parallelization granularity: seed x attacker_fraction
# ==================================================================
if [ "${ENABLE_STAGE_D}" = "1" ]; then
  echo "===== STAGE D: long-horizon fairness ====="
  for seed in "${SEEDS[@]}"; do
    for af in "${LONG_HORIZON_ATTACKER_FRACTIONS[@]}"; do
      out="${ROOT_OUT}/long_horizon/seed_${seed}/af_${af}"
      run_limited "D seed=${seed} af=${af}" \
        python -m tools.committee_comparative_evaluation \
          --skip-reduced \
          --skip-literature \
          --skip-solver \
          --skip-security \
          --run-long-horizon \
          --long-horizon-rounds 5000 \
          --long-horizon-trace-interval 250 \
          --long-horizon-attacker-fractions "${af}" \
          --long-horizon-strategies committee_quantum committee_vrf_stake \
                                    committee_reputation committee_composite_greedy \
                                    committee_uniform committee_fairness_only \
          --security-nodes 100 \
          --committee-k "${COMMITTEE_K}" \
          --metadata-profile "${METADATA}" \
          --seed "${seed}" \
          --output-dir "${out}" \
          --skip-plots
    done
  done
  drain_stage "stage D"
fi

# ==================================================================
# STAGE E: BFT-threshold k sweep
#
# This is split similarly to Stage C so that each k and attacker fraction
# can run independently.
# ==================================================================
if [ "${ENABLE_STAGE_E}" = "1" ]; then
  echo "===== STAGE E1: literature comparison by k ====="
  for seed in "${SEEDS[@]}"; do
    for k in 4 7 10 13; do
      out="${ROOT_OUT}/k_sweep/k${k}/seed_${seed}/literature"
      run_limited "E1 seed=${seed} k=${k}" \
        python -m tools.committee_comparative_evaluation \
          --skip-reduced \
          --skip-solver \
          --skip-security \
          --literature-nodes 100 \
          --literature-rounds 1000 \
          --committee-k "${k}" \
          --committee-k-values "${k}" \
          --metadata-profile "${METADATA}" \
          --attacker-fraction 0.33 \
          --seed "${seed}" \
          --output-dir "${out}" \
          --skip-plots
    done
  done
  drain_stage "stage E1"

  echo "===== STAGE E2: witness collusion by k ====="
  for seed in "${SEEDS[@]}"; do
    for k in 4 7 10 13; do
      out="${ROOT_OUT}/k_sweep/k${k}/seed_${seed}/security_witness"
      run_limited "E2 seed=${seed} k=${k}" \
        python -m tools.security_experiments \
          --experiments witness_collusion \
          --witness-collusion-nodes 100 \
          --attacker-fraction 0.33 \
          --seed "${seed}" \
          --output-dir "${out}"
    done
  done
  drain_stage "stage E2"

  echo "===== STAGE E3: attacker-fraction sweep by k ====="
  for seed in "${SEEDS[@]}"; do
    for k in 4 7 10 13; do
      for af in "${ATTACKER_FRACTIONS[@]}"; do
        out="${ROOT_OUT}/k_sweep/k${k}/seed_${seed}/security_attacker/af_${af}"
        run_limited "E3 seed=${seed} k=${k} af=${af}" \
          python -m tools.security_experiments \
            --experiments attacker_sweep \
            --sweep-nodes 100 \
            --sweep-rounds 1000 \
            --sweep-fractions "${af}" \
            --sweep-committee-k "${k}" \
            --include-exact-when-safe \
            --seed "${seed}" \
            --output-dir "${out}"
      done
    done
  done
  drain_stage "stage E3"

  echo "===== STAGE E4: correlated failure by k ====="
  for seed in "${SEEDS[@]}"; do
    for k in 4 7 10 13; do
      for outage in "${OUTAGE_PROBABILITIES[@]}"; do
        out="${ROOT_OUT}/k_sweep/k${k}/seed_${seed}/security_correlated/p_${outage}"
        run_limited "E4 seed=${seed} k=${k} outage=${outage}" \
          python -m tools.security_experiments \
            --experiments correlated_failure \
            --corr-nodes 100 \
            --corr-rounds 1000 \
            --corr-outage-probs "${outage}" \
            --corr-committee-k "${k}" \
            --attacker-fraction 0.33 \
            --include-exact-when-safe \
            --seed "${seed}" \
            --output-dir "${out}"
      done
    done
  done
  drain_stage "stage E4"

  echo "===== STAGE E5: block withholding by k ====="
  for seed in "${SEEDS[@]}"; do
    for k in 4 7 10 13; do
      for withholding in "${WITHHOLDING_PROBABILITIES[@]}"; do
        out="${ROOT_OUT}/k_sweep/k${k}/seed_${seed}/security_withholding/p_${withholding}"
        run_limited "E5 seed=${seed} k=${k} withholding=${withholding}" \
          python -m tools.security_experiments \
            --experiments block_withholding \
            --withholding-nodes 100 \
            --withholding-rounds 1000 \
            --withholding-probs "${withholding}" \
            --withholding-committee-k "${k}" \
            --include-exact-when-safe \
            --seed "${seed}" \
            --output-dir "${out}"
      done
    done
  done
  drain_stage "stage E5"
fi

echo
echo "===== DONE ====="
echo "Outputs under: ${ROOT_OUT}"
echo "Use visualize_findings.py with --all-security to merge the split security runs."