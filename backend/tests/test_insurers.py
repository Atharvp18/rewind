"""Mock insurer prescription benefits: recognizing the insurer and the pharmacist tip."""
from payments import insurers
from speech import compose


def test_known_insurers_are_recognized_from_card_text():
    assert insurers.find("UnitedHealthcare Choice Plus")["id"] == "unitedhealthcare"
    assert insurers.find("AETNA PPO")["id"] == "aetna"
    assert insurers.find("Cigna Open Access")["id"] == "cigna"
    assert insurers.find("Some Local Plan") is None and insurers.find(None) is None


def test_tip_sends_the_shopper_to_the_pharmacist_and_never_promises_a_copay():
    tip = insurers.pharmacist_tip("Aetna")
    assert "ask the pharmacist to confirm your copay" in tip and "often around $10.00" in tip
    assert insurers.pharmacist_tip("Some Local Plan") is None


def test_strength_confirmed_with_and_without_a_tip():
    plain = compose.strength_confirmed("Omeprazole", "20mg").text
    tipped = compose.strength_confirmed("Omeprazole", "20mg", insurers.pharmacist_tip("Cigna")).text
    assert "The pharmacist will tell you your share" in plain
    assert "Your Cigna plan may cover part of this" in tipped and "confirm your copay" in tipped
