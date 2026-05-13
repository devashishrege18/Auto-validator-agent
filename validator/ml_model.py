# -------------------------------------------------------
# validator/ml_model.py
# -------------------------------------------------------
# Runtime ML inference module.
#
# Loads the trained model from disk and provides
# predictions for new compliance data.
#
# This module is used by the smart audit endpoint to
# get ML-based risk assessments instantly (<10ms).
# -------------------------------------------------------

import pathlib
import joblib
import pandas as pd
from typing import Any, Optional

# -------------------------------------------------------
# Model File Path
# -------------------------------------------------------
MODEL_FILE = pathlib.Path(__file__).parent.parent / "data" / "compliance_model.pkl"

# -------------------------------------------------------
# Cached model (loaded once, reused for every request)
# -------------------------------------------------------
_cached_model: Optional[dict] = None


def load_model() -> Optional[dict]:
    """
    Load the trained model from disk.

    Uses a module-level cache so the model is only
    loaded once, even if this function is called
    multiple times.

    Returns
    -------
    dict | None
        The model package containing the classifier,
        regressor, feature columns, and metadata.
        Returns None if the model file doesn't exist
        (model hasn't been trained yet).
    """
    global _cached_model

    # Return cached model if already loaded
    if _cached_model is not None:
        return _cached_model

    # Check if model file exists
    if not MODEL_FILE.exists():
        print(
            "[ML MODEL] Model file not found. "
            "Train the model first with: python -m validator.train_model"
        )
        return None

    # Load and cache the model
    try:
        _cached_model = joblib.load(MODEL_FILE)
        print("[ML MODEL] Model loaded successfully.")
        return _cached_model
    except Exception as exc:
        print(f"[ML MODEL] Failed to load model: {exc}")
        return None


def extract_features(
    infrastructure_checks: list[dict],
    task_results: list[dict],
) -> Optional[list[float]]:
    """
    Convert raw check results into the feature vector
    that our trained model expects.

    Parameters
    ----------
    infrastructure_checks : list[dict]
        Results from the compliance API checks
        (mfa, firewall, password policy).

    task_results : list[dict]
        Results from task validation (PASS/FAIL/NEEDS_REVIEW).

    Returns
    -------
    list[float] | None
        Feature vector in the order the model expects,
        or None if the data can't be converted.
    """

    try:
        # -------------------------------------------------
        # Extract infrastructure features from check results
        # -------------------------------------------------
        # Default values (worst case) in case a check is missing
        mfa_enabled = 0
        firewall_active = 0
        password_min_length = 8
        special_chars_required = 0

        for check in infrastructure_checks:
            name = check.get("check", "")
            verdict = check.get("verdict", "")

            if "MFA" in name or "mfa" in name.lower():
                mfa_enabled = 1 if verdict == "VERIFIED" else 0

            elif "Firewall" in name or "firewall" in name.lower():
                firewall_active = 1 if verdict == "VERIFIED" else 0

            elif "Password" in name or "password" in name.lower():
                if verdict == "VERIFIED":
                    # Extract the actual length from details if possible
                    details = check.get("details", "")
                    # Try to find the number in the details string
                    import re
                    nums = re.findall(r"(\d+)\s*characters", details)
                    if nums:
                        password_min_length = int(nums[0])
                    else:
                        password_min_length = 12
                    special_chars_required = 1
                else:
                    password_min_length = 6
                    special_chars_required = 0

        # -------------------------------------------------
        # Extract task features from validation results
        # -------------------------------------------------
        total_tasks = len(task_results) if task_results else 0
        completed_tasks = 0
        evidence_complete_tasks = 0

        for task in task_results:
            verdict = task.get("verdict", "")
            if verdict == "PASS":
                completed_tasks += 1
                evidence_complete_tasks += 1
            elif verdict == "FAIL":
                # Status is "completed" but evidence is missing
                completed_tasks += 1
            # NEEDS_REVIEW = not completed, so we don't count it

        # -------------------------------------------------
        # Build the feature vector in the expected order
        # -------------------------------------------------
        features = [
            mfa_enabled,
            firewall_active,
            password_min_length,
            special_chars_required,
            total_tasks,
            completed_tasks,
            evidence_complete_tasks,
        ]

        return features

    except Exception as exc:
        print(f"[ML MODEL] Feature extraction failed: {exc}")
        return None


def predict(
    infrastructure_checks: list[dict],
    task_results: list[dict],
) -> Optional[dict[str, Any]]:
    """
    Run the ML model on compliance check results to get
    a risk prediction and compliance score.

    Parameters
    ----------
    infrastructure_checks : list[dict]
        Results from check_mfa(), check_firewall(), etc.

    task_results : list[dict]
        Results from validate_task() for each task.

    Returns
    -------
    dict | None
        Prediction containing:
        - risk_level: str (LOW/MEDIUM/HIGH/CRITICAL)
        - risk_level_numeric: int (0-3)
        - compliance_score: float (0-100)
        - confidence: float (0-1, from Random Forest)
        - feature_importances: dict (which features matter most)
        - features_used: dict (actual feature values fed to model)
        Returns None if the model is not loaded or prediction fails.
    """

    # Load the model (uses cache after first call)
    model = load_model()
    if model is None:
        return None

    # Extract features from the raw check results
    features = extract_features(infrastructure_checks, task_results)
    if features is None:
        return None

    try:
        # -------------------------------------------------
        # Convert features to DataFrame so sklearn gets
        # the column names it was trained with (avoids
        # the "X does not have valid feature names" warning)
        # -------------------------------------------------
        feature_cols = model["feature_columns"]
        features_df = pd.DataFrame([features], columns=feature_cols)

        # -------------------------------------------------
        # Get the risk level prediction
        # -------------------------------------------------
        classifier = model["risk_classifier"]
        risk_numeric = int(classifier.predict(features_df)[0])
        risk_label = model["risk_level_names"][risk_numeric]

        # Get prediction probabilities (confidence)
        probabilities = classifier.predict_proba(features_df)[0]
        confidence = float(max(probabilities))

        # -------------------------------------------------
        # Get the compliance score prediction
        # -------------------------------------------------
        regressor = model["score_regressor"]
        compliance_score = float(regressor.predict(features_df)[0])
        compliance_score = max(0.0, min(100.0, compliance_score))

        # -------------------------------------------------
        # Build feature importance breakdown
        # -------------------------------------------------
        importances = model["feature_importances"]

        # Map feature names to their actual values
        features_used = dict(zip(feature_cols, features))

        return {
            "risk_level": risk_label,
            "risk_level_numeric": risk_numeric,
            "compliance_score": round(compliance_score, 1),
            "confidence": round(confidence, 2),
            "feature_importances": importances,
            "features_used": features_used,
            "model_metrics": model.get("metrics", {}),
        }

    except Exception as exc:
        print(f"[ML MODEL] Prediction failed: {exc}")
        return None
