import pytest

from app import safety


@pytest.mark.parametrize(
    "text,category",
    [
        ("i keep thinking about killing myself", "self_harm"),
        ("i don't want to be here anymore", "self_harm"),
        ("my partner hits me when he's angry, should I leave", "abuse"),
        ("i'm afraid for my safety at home", "abuse"),
        ("chest pain radiating down my arm, should I lie down", "medical"),
        ("should I take out a payday loan to cover rent", "financial"),
        ("thinking of cashing out my retirement to pay off the car", "financial"),
    ],
)
def test_flags_the_expected_category(text, category):
    flag = safety.screen(text)
    assert flag is not None
    assert flag["category"] == category


@pytest.mark.parametrize(
    "text",
    [
        "should I skip breakfast today",
        "this leg workout is killing me, should I push through",
        "i'm dying to see that movie this weekend",
        "should I buy the cheaper laptop or save for the better one",
        "should I quit this club",
    ],
)
def test_does_not_flag_ordinary_decisions(text):
    assert safety.screen(text) is None


def test_crisis_tier_vs_sensitive_tier():
    assert safety.screen("i want to end my life")["tier"] == "crisis"
    assert safety.screen("should I get a payday loan")["tier"] == "sensitive"


def test_screens_across_option_texts():
    flag = safety.screen("what to do this weekend", "go to the party", "just end it all")
    assert flag is not None and flag["tier"] == "crisis"


def test_flag_carries_message_and_resources():
    flag = safety.screen("i want to hurt myself")
    assert flag["message"]
    assert any("988" in r["detail"] for r in flag["resources"])
