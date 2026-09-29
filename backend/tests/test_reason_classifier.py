import pytest

from classifier_agent.ML import reason_classifier


def test_evaluate_scores_only_unique_texts(monkeypatch):
    monkeypatch.setattr(
        reason_classifier,
        "load_labeled_examples",
        lambda: (["a1", "a1", "a2", "b1", "b1", "b2"],
                 ["A", "A", "A", "B", "B", "B"]),
    )

    def predict_once_per_text(pipeline, texts, labels, cv):
        assert texts == ["a1", "a2", "b1", "b2"]
        assert labels == ["A", "A", "B", "B"]
        assert cv.n_splits == 2
        return ["A", "B", "B", "B"]

    monkeypatch.setattr(reason_classifier, "cross_val_predict", predict_once_per_text)
    result = reason_classifier.evaluate()

    assert result["n_examples"] == 4
    assert result["n_labeled_examples"] == 6
    assert result["accuracy"] == 0.75
    assert result["per_class"]["A"] == {
        "precision": 1.0, "recall": 0.5, "f1": 2 / 3, "support": 2,
    }
    assert result["confusion_matrix"] == {
        "labels": ["A", "B"], "counts": [[1, 1], [0, 2]],
    }


def test_evaluate_rejects_conflicting_labels_without_exposing_text(monkeypatch):
    monkeypatch.setattr(reason_classifier, "load_labeled_examples", lambda: (["private", "private"], ["A", "B"]))

    with pytest.raises(ValueError, match="서로 다른 라벨") as error:
        reason_classifier.evaluate()

    assert "private" not in str(error.value)


def test_evaluate_requires_two_unique_texts_per_class(monkeypatch):
    monkeypatch.setattr(
        reason_classifier, "load_labeled_examples",
        lambda: (["a", "a", "b", "c"], ["A", "A", "B", "B"]),
    )

    with pytest.raises(RuntimeError, match="고유 텍스트"):
        reason_classifier.evaluate()