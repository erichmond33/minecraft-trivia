import unittest

from trivia_minecraft_chaos import (
    AdaptiveTriviaAgent,
    MinecraftChaos,
    QUESTION_BANK,
    answer_matches,
)


class TriviaChaosTests(unittest.TestCase):
    def test_answer_matching_ignores_case_and_punctuation(self) -> None:
        self.assertTrue(answer_matches("  William Shakespeare! ", ("shakespeare", "william shakespeare")))
        self.assertTrue(answer_matches("300,000", ("300000",)))
        self.assertFalse(answer_matches("shakes pear", ("shakespeare",)))

    def test_agent_ramps_difficulty_every_three_questions(self) -> None:
        agent = AdaptiveTriviaAgent(QUESTION_BANK)
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


if __name__ == "__main__":
    unittest.main()
