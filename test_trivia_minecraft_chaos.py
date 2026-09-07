import unittest

from trivia_minecraft_chaos import (
    ChatMessage,
    GeminiClient,
    LlmTriviaAgent,
    LocalTriviaAgent,
    MinecraftChaos,
    OllamaCloudClient,
    LOCAL_QUESTION_BANK,
    answer_matches,
    parse_args,
    parse_chat_log_line,
)


class TriviaChaosTests(unittest.TestCase):
    def test_answer_matching_ignores_case_and_punctuation(self) -> None:
        self.assertTrue(answer_matches("  William Shakespeare! ", ("shakespeare", "william shakespeare")))
        self.assertTrue(answer_matches("300,000", ("300000",)))
        self.assertFalse(answer_matches("shakes pear", ("shakespeare",)))

    def test_agent_ramps_difficulty_every_three_questions(self) -> None:
        agent = LocalTriviaAgent(LOCAL_QUESTION_BANK)
        self.assertEqual(agent.difficulty, 4)
        agent.next_question()
        agent.next_question()
        agent.next_question()
        self.assertEqual(agent.difficulty, 5)

    def test_wrong_answer_rolls_one_punishment(self) -> None:
        commands: list[str] = []
        chaos = MinecraftChaos(send_command=lambda command: commands.append(command) or "", target="@p", dry_run=False)

        punishment_name = chaos.punish()

        self.assertTrue(punishment_name)
        self.assertGreaterEqual(len(commands), 2)
        self.assertTrue(commands[0].startswith("say Wrong answer. Punishment rolled:"))

    def test_punishment_catalog_has_sixty_options(self) -> None:
        chaos = MinecraftChaos(send_command=lambda command: "", target="@p", dry_run=False)
        self.assertEqual(len(chaos.punishments), 60)

    def test_all_punishment_factories_return_commands(self) -> None:
        chaos = MinecraftChaos(send_command=lambda command: "", target="@p", dry_run=False)
        for name, factory in chaos.punishments:
            with self.subTest(name=name):
                commands = factory()
                self.assertTrue(commands)
                self.assertTrue(all(isinstance(command, str) and command for command in commands))

    def test_llm_agent_generates_and_judges_question_from_json(self) -> None:
        class FakeLlm:
            def __init__(self) -> None:
                self.calls = 0

            def generate(self, prompt: str) -> str:
                self.calls += 1
                if self.calls == 1:
                    return '{"question":"What is 2 + 2?","expected_answer":"4","difficulty":1}'
                return '{"correct":true,"message":"Correct. Good job.","expected_answer":"4"}'

        agent = LlmTriviaAgent(FakeLlm(), "general trivia")
        question = agent.next_question()
        judgement = agent.judge_answer(question, "four")

        self.assertEqual(question.prompt, "What is 2 + 2?")
        self.assertTrue(judgement.correct)
        self.assertEqual(judgement.expected_answer, "4")

    def test_default_delay_is_three_minutes(self) -> None:
        args = parse_args([])
        self.assertEqual(args.delay_seconds, 180.0)

    def test_default_question_count_is_one_hundred(self) -> None:
        args = parse_args([])
        self.assertEqual(args.questions, 100)

    def test_gemini_tls_flags_are_parsed(self) -> None:
        args = parse_args(["--gemini-ca-file", "certs.pem", "--gemini-insecure-skip-verify"])
        self.assertEqual(args.gemini_ca_file, "certs.pem")
        self.assertTrue(args.gemini_insecure_skip_verify)

    def test_ollama_flags_are_parsed(self) -> None:
        args = parse_args(["--llm-provider", "ollama", "--ollama-model", "gpt-oss:120b", "--ollama-host", "http://localhost:11434"])
        self.assertEqual(args.llm_provider, "ollama")
        self.assertEqual(args.ollama_model, "gpt-oss:120b")
        self.assertEqual(args.ollama_host, "http://localhost:11434")

    def test_gemini_client_can_build_unverified_ssl_context(self) -> None:
        client = GeminiClient("key", "model", insecure_skip_verify=True)
        context = client._ssl_context()
        self.assertFalse(context.check_hostname)
        self.assertEqual(context.verify_mode, 0)

    def test_ollama_client_can_build_unverified_ssl_context(self) -> None:
        client = OllamaCloudClient("key", "model", insecure_skip_verify=True)
        context = client._ssl_context()
        self.assertFalse(context.check_hostname)
        self.assertEqual(context.verify_mode, 0)

    def test_parse_chat_log_line(self) -> None:
        line = "[20:12:01] [Server thread/INFO]: <Steve> Mount Everest"
        self.assertEqual(parse_chat_log_line(line), ChatMessage("Steve", "Mount Everest"))

    def test_parse_chat_log_line_with_chat_marker(self) -> None:
        line = "[20:12:01] [Async Chat Thread - #1/INFO]: [CHAT] <Alex> Jupiter"
        self.assertEqual(parse_chat_log_line(line), ChatMessage("Alex", "Jupiter"))

    def test_parse_chat_log_line_ignores_non_chat(self) -> None:
        line = "[20:12:01] [Server thread/INFO]: Steve joined the game"
        self.assertIsNone(parse_chat_log_line(line))


if __name__ == "__main__":
    unittest.main()
