# -------------------------------------------------------
# tests/test_ml_pipeline.py
# -------------------------------------------------------
# Unit tests for the ML pipeline:
#   - Training data generation (generate_training_data.py)
#   - Label computation (domain rules)
#   - Feature extraction (ml_model.py)
#   - Model prediction (ml_model.py)
# -------------------------------------------------------

import pytest
from validator.generate_training_data import (
    compute_labels,
    generate_one_sample,
    generate_dataset,
    FEATURE_NAMES,
    LABEL_NAMES,
)
from validator.ml_model import extract_features


# -------------------------------------------------------
# Label Computation Tests (Domain Rules)
# -------------------------------------------------------

class TestComputeLabels:
    """Tests for compute_labels() — the expert rules."""

    def test_perfect_compliance_low_risk(self):
        """All controls enabled + all tasks complete → LOW risk."""
        features = {
            "mfa_enabled": 1,
            "firewall_active": 1,
            "password_min_length": 16,
            "special_chars_required": 1,
            "total_tasks": 5,
            "completed_tasks": 5,
            "evidence_complete_tasks": 5,
        }
        risk, score = compute_labels(features)
        assert risk == 0  # LOW
        assert score >= 85

    def test_both_critical_down_always_critical(self):
        """MFA off + firewall off → always CRITICAL, even with tasks done."""
        features = {
            "mfa_enabled": 0,
            "firewall_active": 0,
            "password_min_length": 16,
            "special_chars_required": 1,
            "total_tasks": 5,
            "completed_tasks": 5,
            "evidence_complete_tasks": 5,
        }
        risk, score = compute_labels(features)
        assert risk == 3  # CRITICAL — override rule

    def test_weak_password_lower_score(self):
        """Password length 6 → no credit, lower score."""
        strong = {
            "mfa_enabled": 1, "firewall_active": 1,
            "password_min_length": 14, "special_chars_required": 1,
            "total_tasks": 3, "completed_tasks": 3,
            "evidence_complete_tasks": 3,
        }
        weak = {**strong, "password_min_length": 6, "special_chars_required": 0}

        _, strong_score = compute_labels(strong)
        _, weak_score = compute_labels(weak)
        assert strong_score > weak_score

    def test_no_tasks_defined(self):
        """Zero total tasks → task score is 0 but should not crash."""
        features = {
            "mfa_enabled": 1, "firewall_active": 1,
            "password_min_length": 12, "special_chars_required": 1,
            "total_tasks": 0, "completed_tasks": 0,
            "evidence_complete_tasks": 0,
        }
        risk, score = compute_labels(features)
        assert score >= 0  # Should not crash or go negative

    def test_score_clamped_0_to_100(self):
        """Score should never go below 0 or above 100."""
        features = {
            "mfa_enabled": 0, "firewall_active": 0,
            "password_min_length": 4, "special_chars_required": 0,
            "total_tasks": 10, "completed_tasks": 0,
            "evidence_complete_tasks": 0,
        }
        risk, score = compute_labels(features)
        assert 0 <= score <= 100

    def test_risk_levels_range(self):
        """risk_level should always be 0, 1, 2, or 3."""
        for _ in range(50):
            sample = generate_one_sample()
            assert sample["risk_level"] in (0, 1, 2, 3)


# -------------------------------------------------------
# Data Generation Tests
# -------------------------------------------------------

class TestDataGeneration:
    """Tests for generate_one_sample() and generate_dataset()."""

    def test_sample_has_all_features(self):
        """Each sample should have all feature columns."""
        sample = generate_one_sample()
        for col in FEATURE_NAMES:
            assert col in sample

    def test_sample_has_labels(self):
        """Each sample should have both labels."""
        sample = generate_one_sample()
        for col in LABEL_NAMES:
            assert col in sample

    def test_completed_lte_total(self):
        """completed_tasks should never exceed total_tasks."""
        for _ in range(100):
            sample = generate_one_sample()
            assert sample["completed_tasks"] <= sample["total_tasks"]

    def test_evidence_lte_completed(self):
        """evidence_complete_tasks should never exceed completed_tasks."""
        for _ in range(100):
            sample = generate_one_sample()
            assert sample["evidence_complete_tasks"] <= sample["completed_tasks"]

    def test_dataset_correct_size(self):
        """generate_dataset() should return the requested number of samples."""
        dataset = generate_dataset(n_samples=50)
        assert len(dataset) == 50

    def test_dataset_reproducible(self):
        """Same seed should produce same dataset (reproducibility)."""
        d1 = generate_dataset(n_samples=10)
        d2 = generate_dataset(n_samples=10)
        assert d1 == d2  # RANDOM_SEED ensures determinism


# -------------------------------------------------------
# Feature Extraction Tests
# -------------------------------------------------------

class TestFeatureExtraction:
    """Tests for extract_features() in ml_model.py."""

    def test_correct_length(self):
        """Should return exactly 7 features."""
        infra = [
            {"check": "MFA", "verdict": "VERIFIED"},
            {"check": "Firewall", "verdict": "NON-COMPLIANT"},
            {"check": "Password", "verdict": "VERIFIED"},
        ]
        tasks = [{"verdict": "PASS"}, {"verdict": "FAIL"}]

        features = extract_features(infra, tasks)
        assert len(features) == 7

    def test_mfa_verified_maps_to_1(self):
        """MFA VERIFIED should map to feature value 1."""
        infra = [{"check": "MFA", "verdict": "VERIFIED"}]
        features = extract_features(infra, [])
        assert features[0] == 1  # mfa_enabled

    def test_firewall_non_compliant_maps_to_0(self):
        """Firewall NON-COMPLIANT should map to 0."""
        infra = [{"check": "Firewall", "verdict": "NON-COMPLIANT"}]
        features = extract_features(infra, [])
        assert features[1] == 0  # firewall_active

    def test_task_counting(self):
        """PASS/FAIL/NEEDS_REVIEW should be counted correctly."""
        tasks = [
            {"verdict": "PASS"},
            {"verdict": "PASS"},
            {"verdict": "FAIL"},
            {"verdict": "NEEDS_REVIEW"},
        ]
        features = extract_features([], tasks)
        assert features[4] == 4  # total_tasks
        assert features[5] == 3  # completed_tasks (PASS + FAIL)
        assert features[6] == 2  # evidence_complete_tasks (PASS only)

    def test_empty_inputs(self):
        """Empty inputs should return defaults, not crash."""
        features = extract_features([], [])
        assert features is not None
        assert len(features) == 7
