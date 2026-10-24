from speech.sentences import split_sentences


def test_the_demo_advil_line_splits_into_four_spoken_sentences():
    text = ("I see Advil, ibuprofen 200mg, $12.99. HSA eligible. Your HSA balance is $340. "
            "Want to use your HSA card?")
    assert split_sentences(text) == [
        "I see Advil, ibuprofen 200mg, $12.99.", "HSA eligible.", "Your HSA balance is $340.",
        "Want to use your HSA card?"]


def test_a_price_is_never_split_at_its_decimal_point():
    assert split_sentences("Kettle corn, $4.99. Not HSA eligible, high confidence.") == [
        "Kettle corn, $4.99.", "Not HSA eligible, high confidence."]


def test_question_and_exclamation_marks_end_sentences():
    assert split_sentences("Ready? Go! Done.") == ["Ready?", "Go!", "Done."]


def test_text_without_punctuation_is_one_sentence():
    assert split_sentences("  checkout  ") == ["checkout"]


def test_blank_text_has_no_sentences():
    assert split_sentences("   ") == [] and split_sentences("") == []


def test_extra_whitespace_and_newlines_between_sentences_are_dropped():
    assert split_sentences("One.\n\n  Two.   Three.") == ["One.", "Two.", "Three."]
