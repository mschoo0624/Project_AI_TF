import pytest

from user.app.services.training import training_record_required_hours


@pytest.mark.parametrize("name,branch,expected", [
    ("기본훈련", "육군", 8),
    ("작계훈련(전·후반기)", "육군", 12),
    ("학생예비군", "육군", 8),
    ("동원훈련Ⅰ형", "육군", 28),
    ("동원훈련Ⅱ형", "육군", 32),
    ("동원훈련Ⅱ형", "해군", 28),
    ("동원훈련Ⅱ형", "공군", 28),
    ("훈련", "육군", 28),
    ("알 수 없는 훈련", "육군", None),
])
def test_record_requirement_uses_training_name(name, branch, expected):
    assert training_record_required_hours(name, 2, "동원지정", branch, "병장") == expected


def test_generic_record_with_multiple_components_is_not_guessed():
    assert training_record_required_hours("훈련", 5, "동원지정", "육군", "병장") is None
