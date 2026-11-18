from app.domain.privacy import is_sensitive, public_title, redact
from app.domain.verification import ProofStrength, proof_hint


def test_redacts_contact_details_and_id_numbers() -> None:
    text = "Card for J. Doe, student #1004567890, call 416-555-0199 or jdoe@mail.utoronto.ca"
    out = redact(text)
    assert out is not None
    assert "1004567890" not in out
    assert "416-555-0199" not in out
    assert "jdoe@" not in out
    assert "J. Doe" in out  # names are not detectable by regex; sensitive types hide them


def test_short_numbers_survive() -> None:
    assert redact("Room 204, 3 stickers") == "Room 204, 3 stickers"


def test_sensitive_types_get_generic_titles() -> None:
    assert is_sensitive("student_card")
    assert public_title("Jane Doe's TCard", "student_card") == "Student / campus card"
    assert public_title("Blue umbrella", "umbrella") == "Blue umbrella"


def test_proof_hint_strengths() -> None:
    secret = "Pikachu sticker inside the lid and initials MK engraved"
    strong = proof_hint(secret, "there's a pikachu sticker on the inside of the lid, MK engraved")
    weak = proof_hint(secret, "it's a black case, pretty normal")
    assert strong.strength is ProofStrength.STRONG
    assert "pikachu" in strong.matched_terms
    assert weak.strength is ProofStrength.WEAK


def test_proof_hint_number_bonus() -> None:
    hint = proof_hint("lock screen code ends in 4471", "the case has a crack, ends 4471")
    assert hint.score >= 0.3
