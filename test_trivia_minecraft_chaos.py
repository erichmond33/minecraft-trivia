import unittest

from trivia_minecraft_chaos import (
    GeminiTriviaAgent,
    LocalTriviaAgent,
    MinecraftChaos,
    LOCAL_QUESTION_BANK,
    answer_matches,
)


class TriviaChaosTests(unittest.TestCase):
    def test_answer_matching_ignores_case_and_punctuation(self) -> None:
        self.assertTrue(answer_matches("  William Shakespeare! ", ("shakespeare", "william shakespeare")))
        self.assertTrue(answer_matches("300,000", ("300000",)))
        self.assertFalse(answer_matches("shakes pear", ("shakespeare",)))

    def test_agent_ramps_difficulty_every_three_questions(self) -> None:
        agent = LocalTriviaAgent(LOCAL_QUESTION_BANK)
        self.assertEqual(agent.difficulty, 1)
        agent.next_question()
        agent.next_question()
        agent.next_question()
        self.assertEqual(agent.difficulty, 2)

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

    def test_gemini_agent_generates_and_judges_question_from_json(self) -> None:
        class FakeGemini:
            def __init__(self) -> None:
                self.calls = 0

            def generate(self, prompt: str) -> str:
                self.calls += 1
                if self.calls == 1:
                    return '{"question":"What is 2 + 2?","expected_answer":"4","difficulty":1}'
                return '{"correct":true,"message":"Correct. Good job.","expected_answer":"4"}'

        agent = GeminiTriviaAgent(FakeGemini(), "general trivia")  # type: ignore[arg-type]
        question = agent.next_question()
        judgement = agent.judge_answer(question, "four")

        self.assertEqual(question.prompt, "What is 2 + 2?")
        self.assertTrue(judgement.correct)
        self.assertEqual(judgement.expected_answer, "4")


if __name__ == "__main__":
    unittest.main()
