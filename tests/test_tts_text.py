import unittest

from app.voice.text_utils import clean_text, transcribe_latin_for_russian_tts


class TtsTextTests(unittest.TestCase):
    def test_known_english_terms_are_written_for_russian_voice(self) -> None:
        result = transcribe_latin_for_russian_tts(
            "Открываю Steam и Cyberpunk в Windows",
        )

        self.assertEqual(
            result,
            "Открываю стим и сайберпанк в уиндоус",
        )

    def test_acronyms_and_unknown_words_get_a_phonetic_fallback(self) -> None:
        result = transcribe_latin_for_russian_tts("VPN включён, hello")

        self.assertEqual(result, "ви-пи-эн включён, хелло")

    def test_urls_emails_and_paths_keep_their_exact_text(self) -> None:
        source = "Открой https://ziren.store, test@example.com и C:\\Ziren\\app.exe"

        self.assertEqual(transcribe_latin_for_russian_tts(source), source)

    def test_phonetic_hyphens_become_spoken_pauses(self) -> None:
        self.assertEqual(clean_text("эй-ай и ви-пи-эн"), "эй ай и ви пи эн")


if __name__ == "__main__":
    unittest.main()
