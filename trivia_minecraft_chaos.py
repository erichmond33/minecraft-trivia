#!/usr/bin/env python3
"""Adaptive trivia game that punishes wrong answers in local Minecraft via RCON.

Enable RCON in your Minecraft Java server, then run this script in a terminal.
No third-party Python packages are required.
"""

from __future__ import annotations

import argparse
import dataclasses
import getpass
import random
import re
import socket
import struct
import sys
import time
from typing import Callable


SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


HOSTILE_MOBS = [
    "zombie",
    "skeleton",
    "spider",
    "creeper",
    "husk",
    "stray",
    "drowned",
    "witch",
    "cave_spider",
]


@dataclasses.dataclass(frozen=True)
class Question:
    prompt: str
    answers: tuple[str, ...]
    difficulty: int
    note: str = ""


QUESTION_BANK: list[Question] = [
    Question("What color is the sky on a clear day?", ("blue",), 1),
    Question("How many legs does a spider have?", ("8", "eight"), 1),
    Question("What planet do humans live on?", ("earth",), 1),
    Question("What do bees make?", ("honey",), 1),
    Question("What is 2 + 2?", ("4", "four"), 1),
    Question("What animal says 'meow'?", ("cat", "a cat"), 1),
    Question("What gas do humans need to breathe?", ("oxygen",), 2),
    Question("How many days are in a leap year?", ("366", "three hundred sixty six"), 2),
    Question("What is the capital of France?", ("paris",), 2),
    Question("What is H2O commonly called?", ("water",), 2),
    Question("How many sides does a triangle have?", ("3", "three"), 2),
    Question("Which ocean is the largest?", ("pacific", "pacific ocean"), 2),
    Question("Who wrote Romeo and Juliet?", ("shakespeare", "william shakespeare"), 3),
    Question("What is the chemical symbol for gold?", ("au",), 3),
    Question("What is the square root of 144?", ("12", "twelve"), 3),
    Question("What is the largest organ in the human body?", ("skin", "the skin"), 3),
    Question("Which planet is known as the Red Planet?", ("mars",), 3),
    Question("What is the main language spoken in Brazil?", ("portuguese",), 3),
    Question("In Minecraft, what item is needed to enter the Nether?", ("flint and steel", "flint steel"), 4),
    Question("What is the hardest natural vanilla Minecraft block to mine?", ("obsidian",), 4),
    Question("What year did the first iPhone release?", ("2007",), 4),
    Question("What is the powerhouse of the cell?", ("mitochondria", "the mitochondria"), 4),
    Question("Which element has atomic number 6?", ("carbon",), 4),
    Question("What is the capital of Canada?", ("ottawa",), 4),
    Question("What is the speed of light in vacuum, rounded to the nearest million km/s?", ("300000", "300,000", "three hundred thousand"), 5),
    Question("Who painted The Persistence of Memory?", ("salvador dali", "dali"), 5),
    Question("What is the smallest prime number?", ("2", "two"), 5),
    Question("What is the longest river in Africa?", ("nile", "the nile", "nile river"), 5),
    Question("What protocol does a browser usually use for secure websites?", ("https",), 5),
    Question("What is the SI unit of electric current?", ("ampere", "amp", "amps"), 5),
    Question("What is the capital of Kazakhstan?", ("astana",), 6),
    Question("What is the derivative of x squared?", ("2x", "two x"), 6),
    Question("What molecule carries genetic instructions in most living organisms?", ("dna",), 6),
    Question("Which artist cut off part of his ear?", ("vincent van gogh", "van gogh"), 6),
    Question("What is the only even prime number?", ("2", "two"), 6),
    Question("What is the Minecraft mob cap category for zombies and skeletons?", ("monster", "hostile", "monsters"), 6),
    Question("What is Avogadro's number rounded to three significant figures?", ("6.02 x 10^23", "6.02e23", "6.02*10^23"), 7),
    Question("Which treaty ended World War I?", ("treaty of versailles", "versailles"), 7),
    Question("What is the first book of the Iliad's sequel cycle by Virgil called?", ("aeneid", "the aeneid"), 7),
    Question("What is the name of the paradox involving a barber who shaves all who do not shave themselves?", ("russell's paradox", "russell paradox"), 7),
    Question("What is the time complexity of binary search on a sorted array?", ("o(log n)", "log n", "logarithmic"), 7),
    Question("In chess notation, what does O-O-O mean?", ("queenside castling", "long castling", "castle queenside"), 7),
    Question("Who formulated the incompleteness theorems?", ("kurt godel", "godel"), 8),
    Question("What is the capital of Burkina Faso?", ("ouagadougou",), 8),
    Question("What isotope is commonly used in radiocarbon dating?", ("carbon 14", "c14", "carbon-14"), 8),
    Question("What is the term for a word that is spelled the same forwards and backwards?", ("palindrome",), 8),
    Question("Which sorting algorithm is stable and has O(n log n) worst-case time but usually needs extra memory?", ("merge sort", "mergesort"), 8),
    Question("What Minecraft gamerule disables mob griefing?", ("mobgriefing", "do mobgriefing false"), 8),
    Question("What is the Feigenbaum constant delta rounded to three decimals?", ("4.669",), 9),
    Question("Which mathematician proved Fermat's Last Theorem?", ("andrew wiles", "wiles"), 9),
    Question("What is the capital of Nauru?", ("yaren", "yaren district"), 9),
    Question("What is the Linux syscall commonly used to duplicate a file descriptor?", ("dup", "dup2", "dup3"), 9),
    Question("What is the canonical IUPAC name of table salt?", ("sodium chloride",), 9),
    Question("In vanilla Java commands, what selector argument limits entities by distance?", ("distance",), 9),
    Question("What is the Monster group order's first prime factor?", ("2", "two"), 10),
    Question("Who coined the term 'quark' in particle physics?", ("murray gell-mann", "gell-mann", "gell mann"), 10),
    Question("What is the smallest sporadic simple group?", ("mathieu group m11", "m11", "mathieu m11"), 10),
    Question("Which RFC originally specified HTTP/1.1 in 1997?", ("rfc 2068", "2068"), 10),
    Question("What is the name of the smallest named Graham's number-style up-arrow operation using Knuth notation for 3 up-arrow 3?", ("tetration",), 10),
    Question("In Minecraft Java, what NBT tag controls whether a mob can pick up loot?", ("canpickuploot",), 10),
]


def normalize_answer(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = cleaned.replace("’", "'")
    cleaned = re.sub(r"[^a-z0-9+*^.\-\s]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def answer_matches(user_answer: str, accepted_answers: tuple[str, ...]) -> bool:
    normalized = normalize_answer(user_answer)
    return any(normalized == normalize_answer(answer) for answer in accepted_answers)


class RconClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._request_id = 100

    def __enter__(self) -> "RconClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def connect(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        auth_id = self._send_packet(SERVERDATA_AUTH, self.password)
        response_id, _, _ = self._read_packet()
        if response_id == -1:
            raise RuntimeError("RCON authentication failed. Check rcon.password.")
        if response_id != auth_id:
            raise RuntimeError("Unexpected RCON authentication response.")

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def command(self, command: str) -> str:
        if self._sock is None:
            raise RuntimeError("RCON client is not connected.")
        request_id = self._send_packet(SERVERDATA_EXECCOMMAND, command)
        chunks: list[str] = []
        while True:
            response_id, packet_type, body = self._read_packet()
            if response_id != request_id:
                break
            chunks.append(body)
            if packet_type == SERVERDATA_RESPONSE_VALUE:
                break
        return "".join(chunks)

    def _send_packet(self, packet_type: int, body: str) -> int:
        if self._sock is None:
            raise RuntimeError("RCON client is not connected.")
        self._request_id += 1
        encoded = body.encode("utf-8")
        payload = struct.pack("<ii", self._request_id, packet_type) + encoded + b"\x00\x00"
        packet = struct.pack("<i", len(payload)) + payload
        self._sock.sendall(packet)
        return self._request_id

    def _read_packet(self) -> tuple[int, int, str]:
        if self._sock is None:
            raise RuntimeError("RCON client is not connected.")
        raw_size = self._recv_exact(4)
        size = struct.unpack("<i", raw_size)[0]
        raw = self._recv_exact(size)
        request_id, packet_type = struct.unpack("<ii", raw[:8])
        body = raw[8:-2].decode("utf-8", errors="replace")
        return request_id, packet_type, body

    def _recv_exact(self, size: int) -> bytes:
        if self._sock is None:
            raise RuntimeError("RCON client is not connected.")
        chunks = bytearray()
        while len(chunks) < size:
            chunk = self._sock.recv(size - len(chunks))
            if not chunk:
                raise ConnectionError("RCON connection closed unexpectedly.")
            chunks.extend(chunk)
        return bytes(chunks)


class MinecraftChaos:
    def __init__(self, send_command: Callable[[str], str], target: str, dry_run: bool) -> None:
        self.send_command = send_command
        self.target = target
        self.dry_run = dry_run
        self.wrong_answers = 0
        self.mob_wave_size = 2
        self.punishments: list[tuple[str, Callable[[], list[str]]]] = [
            ("Duplicate nearby hostile mobs", self.duplicate_nearby_hostiles),
            ("Twenty creepers, because subtlety is gone", self.twenty_creepers),
            ("Lightning judgment", self.lightning_ring),
            ("Anvil rain", self.anvil_rain),
            ("Silverfish confetti", self.silverfish_confetti),
            ("Slowness and mining fatigue", self.clumsy_curse),
            ("The floor is lava, briefly", self.floor_is_lava),
            ("Inventory panic pumpkin", self.pumpkin_helmet),
            ("Launch pad", self.launch_player),
            ("Angry bee meeting", self.angry_bees),
            ("Cave spider tax", self.cave_spiders),
            ("Witch committee", self.witches),
            ("Blindness scare", self.blindness),
            ("Phantom audit", self.phantoms),
            ("Ghastly office hours", self.ghast),
            ("Tiny TNT cough", self.tnt_cough),
            ("Mob jockey mess", self.chicken_jockey),
            ("Snowball knockback storm", self.snowball_storm),
            ("Suspicious stew roulette", self.suspicious_stew),
            ("Chunk bite, not chunk delete", self.chunk_bite),
        ]

    def announce(self, text: str) -> None:
        self.run(f"say {text}")

    def punish(self) -> str:
        self.wrong_answers += 1
        name, command_factory = random.choice(self.punishments)
        commands = command_factory()
        self.announce(f"Wrong answer. Punishment rolled: {name}.")
        for command in commands:
            self.run(command)
            time.sleep(0.05)
        return name

    def reward(self) -> None:
        responses = [
            "Correct. Good job.",
            "Correct. You live another question.",
            "Good job. The mobs are disappointed.",
            "Correct. Suspiciously competent.",
        ]
        self.announce(random.choice(responses))

    def run(self, command: str) -> None:
        if self.dry_run:
            print(f"[minecraft] {command}")
            return
        self.send_command(command)

    def at_target(self, command: str) -> str:
        return f"execute at {self.target} run {command}"

    def as_target(self, command: str) -> str:
        return f"execute as {self.target} at @s run {command}"

    def duplicate_nearby_hostiles(self) -> list[str]:
        count = self.mob_wave_size
        self.mob_wave_size = min(self.mob_wave_size * 2, 64)
        mob = random.choice(HOSTILE_MOBS)
        duplicate_commands = [
            f"execute at {self.target} as @e[type=minecraft:{mob_type},distance=..24,limit=32] at @s run summon minecraft:{mob_type} ~ ~ ~"
            for mob_type in HOSTILE_MOBS
        ]
        escalating_wave = [
            self.at_target(f"summon minecraft:{mob} ~{random.randint(-6, 6)} ~ ~{random.randint(-6, 6)}")
            for _ in range(count)
        ]
        return duplicate_commands + escalating_wave

    def twenty_creepers(self) -> list[str]:
        return [self.at_target(f"summon minecraft:creeper ~{random.randint(-8, 8)} ~ ~{random.randint(-8, 8)}") for _ in range(20)]

    def lightning_ring(self) -> list[str]:
        offsets = [(-5, 0), (5, 0), (0, -5), (0, 5), (-4, -4), (4, 4), (-4, 4), (4, -4)]
        return [self.at_target(f"summon minecraft:lightning_bolt ~{x} ~ ~{z}") for x, z in offsets]

    def anvil_rain(self) -> list[str]:
        return [self.at_target(f"setblock ~{random.randint(-3, 3)} ~12 ~{random.randint(-3, 3)} minecraft:anvil") for _ in range(12)]

    def silverfish_confetti(self) -> list[str]:
        return [self.at_target(f"summon minecraft:silverfish ~{random.randint(-4, 4)} ~ ~{random.randint(-4, 4)}") for _ in range(18)]

    def clumsy_curse(self) -> list[str]:
        return [
            f"effect give {self.target} minecraft:slowness 20 2 true",
            f"effect give {self.target} minecraft:mining_fatigue 20 2 true",
        ]

    def floor_is_lava(self) -> list[str]:
        return [
            self.at_target("fill ~-2 ~-1 ~-2 ~2 ~-1 ~2 minecraft:lava replace minecraft:air"),
            self.at_target("fill ~-2 ~-1 ~-2 ~2 ~-1 ~2 minecraft:magma_block replace minecraft:grass_block"),
        ]

    def pumpkin_helmet(self) -> list[str]:
        return [f"item replace entity {self.target} armor.head with minecraft:carved_pumpkin"]

    def launch_player(self) -> list[str]:
        return [
            self.as_target("tp @s ~ ~18 ~"),
            f"effect give {self.target} minecraft:slow_falling 8 0 true",
        ]

    def angry_bees(self) -> list[str]:
        return [self.at_target(f"summon minecraft:bee ~{random.randint(-4, 4)} ~ ~{random.randint(-4, 4)} {{AngerTime:600}}") for _ in range(12)]

    def cave_spiders(self) -> list[str]:
        return [self.at_target(f"summon minecraft:cave_spider ~{random.randint(-5, 5)} ~ ~{random.randint(-5, 5)}") for _ in range(10)]

    def witches(self) -> list[str]:
        return [self.at_target(f"summon minecraft:witch ~{random.randint(-6, 6)} ~ ~{random.randint(-6, 6)}") for _ in range(4)]

    def blindness(self) -> list[str]:
        return [
            f"effect give {self.target} minecraft:blindness 12 0 true",
            f"effect give {self.target} minecraft:darkness 12 0 true",
        ]

    def phantoms(self) -> list[str]:
        return [self.at_target(f"summon minecraft:phantom ~{random.randint(-8, 8)} ~8 ~{random.randint(-8, 8)}") for _ in range(6)]

    def ghast(self) -> list[str]:
        return [self.at_target("summon minecraft:ghast ~ ~8 ~")]

    def tnt_cough(self) -> list[str]:
        return [self.at_target(f"summon minecraft:tnt ~{random.randint(-3, 3)} ~1 ~{random.randint(-3, 3)} {{Fuse:60}}") for _ in range(5)]

    def chicken_jockey(self) -> list[str]:
        return [self.at_target("summon minecraft:chicken ~ ~ ~ {Passengers:[{id:\"minecraft:zombie\",IsBaby:1b}]}") for _ in range(5)]

    def snowball_storm(self) -> list[str]:
        return [self.at_target(f"summon minecraft:snowball ~{random.randint(-5, 5)} ~5 ~{random.randint(-5, 5)}") for _ in range(24)]

    def suspicious_stew(self) -> list[str]:
        return [f"give {self.target} minecraft:suspicious_stew 1"]

    def chunk_bite(self) -> list[str]:
        return [
            self.at_target("fill ~-3 ~-2 ~-3 ~3 ~3 ~3 minecraft:air replace minecraft:stone"),
            self.at_target("fill ~-3 ~-2 ~-3 ~3 ~3 ~3 minecraft:air replace minecraft:dirt"),
            self.at_target("fill ~-3 ~-2 ~-3 ~3 ~3 ~3 minecraft:air replace minecraft:deepslate"),
        ]


class AdaptiveTriviaAgent:
    def __init__(self, questions: list[Question]) -> None:
        self.questions = questions
        self.asked: set[str] = set()
        self.streak = 0
        self.turn = 0
        self.difficulty = 1

    def next_question(self) -> Question:
        self.turn += 1
        if self.turn % 3 == 0 and self.difficulty < 10:
            self.difficulty += 1
        candidates = [
            question
            for question in self.questions
            if question.prompt not in self.asked and question.difficulty <= self.difficulty
        ]
        if not candidates:
            self.asked.clear()
            candidates = [question for question in self.questions if question.difficulty <= self.difficulty]
        question = random.choice(candidates)
        self.asked.add(question.prompt)
        return question

    def record_answer(self, correct: bool) -> None:
        if correct:
            self.streak += 1
            if self.streak >= 4 and self.difficulty < 10:
                self.difficulty += 1
                self.streak = 0
            return
        self.streak = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minecraft trivia chaos via RCON.")
    parser.add_argument("--host", default="127.0.0.1", help="Minecraft RCON host.")
    parser.add_argument("--port", type=int, default=25575, help="Minecraft RCON port.")
    parser.add_argument("--password", help="Minecraft RCON password. Prompts if omitted.")
    parser.add_argument("--target", default="@a", help="Minecraft target selector, e.g. @a, @p, or a username.")
    parser.add_argument("--questions", type=int, default=25, help="Number of trivia questions to ask.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands instead of connecting to Minecraft.")
    parser.add_argument("--seed", type=int, help="Random seed for repeatable testing.")
    return parser.parse_args()


def make_command_sender(args: argparse.Namespace) -> tuple[Callable[[str], str], RconClient | None]:
    if args.dry_run:
        return lambda command: print(f"[minecraft] {command}") or "", None
    password = args.password or getpass.getpass("RCON password: ")
    client = RconClient(args.host, args.port, password)
    client.connect()
    return client.command, client


def main() -> int:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    try:
        send_command, client = make_command_sender(args)
    except OSError as error:
        print(f"Could not connect to RCON at {args.host}:{args.port}: {error}", file=sys.stderr)
        return 2
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2

    chaos = MinecraftChaos(send_command=send_command, target=args.target, dry_run=args.dry_run)
    agent = AdaptiveTriviaAgent(QUESTION_BANK)

    try:
        chaos.announce("Trivia chaos is live. Wrong answers roll random punishments.")
        for index in range(1, args.questions + 1):
            question = agent.next_question()
            print(f"\nQuestion {index}/{args.questions} | Difficulty {agent.difficulty}/10")
            print(question.prompt)
            user_answer = input("> ")
            if user_answer.strip().lower() in {"quit", "exit"}:
                chaos.announce("Trivia chaos ended early.")
                break
            correct = answer_matches(user_answer, question.answers)
            agent.record_answer(correct)
            if correct:
                print("Correct.")
                chaos.reward()
            else:
                accepted = ", ".join(question.answers[:2])
                print(f"Wrong. Accepted answer: {accepted}")
                punishment = chaos.punish()
                print(f"Punishment: {punishment}")
        chaos.announce("Trivia chaos complete.")
    finally:
        if client is not None:
            client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
