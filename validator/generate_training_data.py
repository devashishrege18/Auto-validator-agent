# -------------------------------------------------------
# validator/generate_training_data.py
# -------------------------------------------------------
# Generates synthetic compliance training data for the
# Auto-Auditor's ML model.
#
# Each row represents one "compliance snapshot" — a
# combination of infrastructure controls and task
# completion metrics that a real bank might have at
# any point in time.
#
# The labels (risk_level, compliance_score) are computed
# using domain rules that encode real banking compliance
# logic, so the ML model learns to mimic expert judgment.
#
# Run this script to create/refresh the training data:
#   python -m validator.generate_training_data
# -------------------------------------------------------

import csv
import random
import pathlib

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------
NUM_SAMPLES = 1000          # Number of training scenarios
OUTPUT_DIR = pathlib.Path(__file__).parent.parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "training_data.csv"

# Seed for reproducibility — same seed = same dataset
RANDOM_SEED = 42


# -------------------------------------------------------
# Feature Definitions
# -------------------------------------------------------
# These mirror the fields our compliance APIs return
# and the task validation results.
FEATURE_NAMES = [
    "mfa_enabled",              # 0 or 1
    "firewall_active",          # 0 or 1
    "password_min_length",      # 4 to 20
    "special_chars_required",   # 0 or 1
    "total_tasks",              # 1 to 20
    "completed_tasks",          # 0 to total_tasks
    "evidence_complete_tasks",  # 0 to completed_tasks
]

LABEL_NAMES = [
    "risk_level",       # 0=LOW, 1=MEDIUM, 2=HIGH, 3=CRITICAL
    "compliance_score",  # 0 to 100
]


# -------------------------------------------------------
# Domain Rules for Label Generation
# -------------------------------------------------------
# These rules encode how a real compliance expert would
# assess risk. The ML model will learn to approximate
# these rules from the data alone.
# -------------------------------------------------------

def compute_labels(features: dict) -> tuple[int, float]:
    """
    Given a set of compliance features, compute the
    risk level and compliance score using domain rules.

    Parameters
    ----------
    features : dict
        The feature values for one compliance scenario.

    Returns
    -------
    (risk_level, compliance_score) : tuple[int, float]
        risk_level: 0=LOW, 1=MEDIUM, 2=HIGH, 3=CRITICAL
        compliance_score: 0.0 to 100.0
    """

    # --------------------------------------------------
    # Score each control area independently (0-25 each)
    # Total possible = 100
    # --------------------------------------------------

    score = 0.0

    # --- MFA (25 points) ---
    # MFA is critical — full points only if enabled
    if features["mfa_enabled"] == 1:
        score += 25.0
    # No partial credit for MFA — it's either on or off

    # --- Firewall (25 points) ---
    # Firewall is critical — full points only if active
    if features["firewall_active"] == 1:
        score += 25.0
    # No partial credit — firewall must be running

    # --- Password Policy (20 points) ---
    # Minimum length >= 12 is the baseline (NIST SP 800-63B)
    pwd_len = features["password_min_length"]
    if pwd_len >= 12:
        score += 15.0
    elif pwd_len >= 8:
        # Partial credit for reasonable but sub-standard
        score += 8.0
    else:
        # Very weak password policy — no credit
        score += 0.0

    # Special characters bonus (5 points)
    if features["special_chars_required"] == 1:
        score += 5.0

    # --- Task Completion (30 points) ---
    # Based on what percentage of tasks have full evidence
    total = features["total_tasks"]
    if total > 0:
        # Completion rate: completed / total
        completion_rate = features["completed_tasks"] / total

        # Evidence rate: fully evidenced / total
        evidence_rate = features["evidence_complete_tasks"] / total

        # Tasks with evidence matter more than just completion
        task_score = (completion_rate * 10.0) + (evidence_rate * 20.0)
        score += task_score
    else:
        # No tasks defined — can't assess
        score += 0.0

    # --------------------------------------------------
    # Add a small random noise to make training realistic
    # (real-world scores aren't perfectly deterministic)
    # --------------------------------------------------
    noise = random.uniform(-3, 3)
    score = max(0.0, min(100.0, score + noise))

    # --------------------------------------------------
    # Determine risk level from the score
    # --------------------------------------------------
    # Additional critical-override rules:
    # If BOTH MFA and firewall are down, it's always
    # CRITICAL regardless of score (attack surface is
    # wide open).
    both_critical_down = (
        features["mfa_enabled"] == 0
        and features["firewall_active"] == 0
    )

    if both_critical_down:
        risk_level = 3  # CRITICAL — override
    elif score >= 80:
        risk_level = 0  # LOW risk
    elif score >= 60:
        risk_level = 1  # MEDIUM risk
    elif score >= 40:
        risk_level = 2  # HIGH risk
    else:
        risk_level = 3  # CRITICAL risk

    return risk_level, round(score, 1)


# -------------------------------------------------------
# Data Generation
# -------------------------------------------------------

def generate_one_sample() -> dict:
    """
    Generate one random compliance scenario with
    realistic feature values and computed labels.
    """

    # Random feature values with realistic distributions
    total_tasks = random.randint(1, 20)
    completed_tasks = random.randint(0, total_tasks)
    evidence_complete = random.randint(0, completed_tasks)

    features = {
        "mfa_enabled": random.choices([0, 1], weights=[30, 70])[0],
        "firewall_active": random.choices([0, 1], weights=[25, 75])[0],
        "password_min_length": random.choices(
            [4, 6, 8, 10, 12, 14, 16],
            weights=[5, 10, 20, 15, 25, 15, 10]
        )[0],
        "special_chars_required": random.choices([0, 1], weights=[35, 65])[0],
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "evidence_complete_tasks": evidence_complete,
    }

    # Compute labels using domain rules
    risk_level, compliance_score = compute_labels(features)

    return {**features, "risk_level": risk_level, "compliance_score": compliance_score}


def generate_dataset(n_samples: int = NUM_SAMPLES) -> list[dict]:
    """
    Generate a full training dataset of n_samples
    compliance scenarios.
    """
    random.seed(RANDOM_SEED)
    return [generate_one_sample() for _ in range(n_samples)]


# -------------------------------------------------------
# Main — run this to generate the CSV
# -------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  GENERATING COMPLIANCE TRAINING DATA")
    print("=" * 60)
    print()

    # Generate the dataset
    dataset = generate_dataset()

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write to CSV
    fieldnames = FEATURE_NAMES + LABEL_NAMES
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dataset)

    # Print summary statistics
    risk_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for row in dataset:
        risk_counts[row["risk_level"]] += 1

    risk_labels = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "CRITICAL"}

    print(f"  Generated {len(dataset)} samples")
    print(f"  Saved to: {OUTPUT_FILE}")
    print()
    print(f"  {'Risk Level':<20} {'Count':<10} {'Percentage':<10}")
    print(f"  {'-'*20} {'-'*10} {'-'*10}")
    for level in range(4):
        count = risk_counts[level]
        pct = count / len(dataset) * 100
        print(f"  {risk_labels[level]:<20} {count:<10} {pct:.1f}%")

    print()
    print("  Done! Ready for training.")
    print("=" * 60)
