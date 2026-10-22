from dataclasses import dataclass
from typing import Dict, List

@dataclass
class AuditMetrics:
    total_cases: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float
    recall: float
    f1_score: float
    evidence_localization_accuracy: float

def calculate_metrics(
    predictions: List[str],  # 'contradiction' or 'not_contradiction'
    ground_truth: List[str],  # 'contradiction' or 'not_contradiction'
    evidence_verified_flags: List[bool],
) -> AuditMetrics:
    """
    Computes precision, recall, F1, false positives, and evidence localization accuracy.
    """
    assert len(predictions) == len(ground_truth) == len(evidence_verified_flags)

    tp = 0
    fp = 0
    fn = 0
    tn = 0
    correct_evidence = 0
    total_contradiction_preds = 0

    for pred, truth, ev_ok in zip(predictions, ground_truth, evidence_verified_flags):
        is_pred_c = (pred == "contradiction")
        is_true_c = (truth == "contradiction")

        if is_pred_c and is_true_c:
            tp += 1
            total_contradiction_preds += 1
            if ev_ok:
                correct_evidence += 1
        elif is_pred_c and not is_true_c:
            fp += 1
            total_contradiction_preds += 1
            if ev_ok:
                correct_evidence += 1
        elif not is_pred_c and is_true_c:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    ev_acc = (correct_evidence / total_contradiction_preds) if total_contradiction_preds > 0 else 1.0

    return AuditMetrics(
        total_cases=len(predictions),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1_score=round(f1, 4),
        evidence_localization_accuracy=round(ev_acc, 4),
    )
