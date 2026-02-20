import unittest

from worker_plan_api.llm_class_filter import is_llm_class_allowed, parse_llm_class_whitelist


class TestLlmClassFilter(unittest.TestCase):
    def test_parse_returns_none_for_blank(self):
        self.assertIsNone(parse_llm_class_whitelist(None))
        self.assertIsNone(parse_llm_class_whitelist(""))
        self.assertIsNone(parse_llm_class_whitelist(" ,  , "))

    def test_parse_normalizes_values(self):
        whitelist = parse_llm_class_whitelist("OpenRouter, Ollama , lmstudio")
        self.assertEqual(whitelist, {"openrouter", "ollama", "lmstudio"})

    def test_is_allowed_without_whitelist(self):
        self.assertTrue(is_llm_class_allowed("OpenRouter", None))
        self.assertTrue(is_llm_class_allowed("Anything", None))

    def test_is_allowed_with_whitelist(self):
        whitelist = {"openrouter", "ollama"}
        self.assertTrue(is_llm_class_allowed("OpenRouter", whitelist))
        self.assertTrue(is_llm_class_allowed("ollama", whitelist))
        self.assertFalse(is_llm_class_allowed("OpenAI", whitelist))
        self.assertFalse(is_llm_class_allowed(None, whitelist))


if __name__ == "__main__":
    unittest.main()
