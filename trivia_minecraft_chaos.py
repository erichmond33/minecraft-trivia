#!/usr/bin/env python3
"""Adaptive trivia game that punishes wrong answers in local Minecraft via RCON.

Enable RCON in your Minecraft Java server, then run this script in a terminal.
No third-party Python packages are required.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import random
import re
import socket
import ssl
import struct
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Protocol


SERVERDATA_AUTH = 3
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0
STARTING_DIFFICULTY = 4
PUNISHMENT_MULTIPLIER = 10


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


LOCAL_QUESTION_BANK: list[Question] = [
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


@dataclasses.dataclass(frozen=True)
class Judgement:
    correct: bool
    message: str
    expected_answer: str


class TextGenerator(Protocol):
    def generate(self, prompt: str) -> str:
        ...


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def get_gemini_key() -> str | None:
    for key_name in ("GEMINI_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(key_name)
        if value:
            return normalize_api_key(value)
    return None


def get_ollama_key() -> str | None:
    for key_name in ("OLLAMA_API_KEY", "OLLAMA_KEY"):
        value = os.environ.get(key_name)
        if value:
            return normalize_api_key(value)
    return None


def normalize_api_key(value: str) -> str:
    cleaned = value.strip().strip('"').strip("'")
    if cleaned.lower().startswith("bearer "):
        return cleaned[7:].strip()
    return cleaned


def extract_json_object(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"Gemini did not return a JSON object: {text[:200]}")
    loaded = json.loads(stripped[start : end + 1])
    if not isinstance(loaded, dict):
        raise ValueError("Gemini returned JSON, but it was not an object.")
    return loaded


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        ca_file: str | None = None,
        insecure_skip_verify: bool = False,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.ca_file = ca_file
        self.insecure_skip_verify = insecure_skip_verify

    def generate(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.9,
                "maxOutputTokens": 600,
                "responseMimeType": "application/json",
            },
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        context = self._ssl_context()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=context) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini HTTP {error.code}: {body[:400]}") from error
        except urllib.error.URLError as error:
            reason = str(error.reason)
            if "CERTIFICATE_VERIFY_FAILED" in reason:
                reason += (
                    ". Your Python install cannot find trusted CA certificates. "
                    "Fix the local certificate store, pass --llm-ca-file, or use "
                    "--llm-insecure-skip-verify for local testing."
                )
            raise RuntimeError(f"Could not reach Gemini: {reason}") from error

        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError(f"Unexpected Gemini response: {json.dumps(data)[:400]}") from error

    def _ssl_context(self) -> ssl.SSLContext:
        if self.insecure_skip_verify:
            return ssl._create_unverified_context()
        if self.ca_file:
            return ssl.create_default_context(cafile=self.ca_file)
        return ssl.create_default_context()


class OllamaCloudClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        host: str = "https://ollama.com",
        timeout: float = 30.0,
        ca_file: str | None = None,
        insecure_skip_verify: bool = False,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.ca_file = ca_file
        self.insecure_skip_verify = insecure_skip_verify

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.7, "top_p": 0.9},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self._ssl_context()) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if error.code == 401:
                raise RuntimeError(
                    "Ollama rejected the API key with HTTP 401. Check that OLLAMA_API_KEY "
                    "is an Ollama Cloud API key from ollama.com, not a Gemini key, and that "
                    "it has no extra quotes, spaces, or label text."
                ) from error
            raise RuntimeError(f"Ollama HTTP {error.code}: {body[:400]}") from error
        except urllib.error.URLError as error:
            reason = str(error.reason)
            if "CERTIFICATE_VERIFY_FAILED" in reason:
                reason += (
                    ". Your Python install cannot find trusted CA certificates. "
                    "Fix the local certificate store, pass --llm-ca-file, or use "
                    "--llm-insecure-skip-verify for local testing."
                )
            raise RuntimeError(f"Could not reach Ollama: {reason}") from error

        try:
            return str(data["message"]["content"])
        except (KeyError, TypeError) as error:
            raise RuntimeError(f"Unexpected Ollama response: {json.dumps(data)[:400]}") from error

    def check_auth(self) -> None:
        try:
            self.generate('Return only JSON: {"ok": true}')
        except RuntimeError as error:
            message = str(error)
            if "HTTP 401" in message:
                raise RuntimeError(
                    "Ollama rejected OLLAMA_API_KEY on /api/chat. Generate a fresh Ollama "
                    "Cloud API key at ollama.com, then put exactly that token in .env as "
                    "OLLAMA_API_KEY=... . Do not reuse your Gemini key."
                ) from error
            raise

    def _ssl_context(self) -> ssl.SSLContext:
        if self.insecure_skip_verify:
            return ssl._create_unverified_context()
        if self.ca_file:
            return ssl.create_default_context(cafile=self.ca_file)
        return ssl.create_default_context()


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


@dataclasses.dataclass(frozen=True)
class ChatMessage:
    player: str
    message: str


class MinecraftChatReader:
    CHAT_PATTERNS = (
        re.compile(r"\]: <([^>]+)> (.*)$"),
        re.compile(r"\[CHAT\]\s+<([^>]+)>\s+(.*)$"),
    )

    def __init__(
        self,
        log_path: str,
        player: str | None = None,
        poll_seconds: float = 0.5,
        start_at_end: bool = True,
    ) -> None:
        self.log_path = log_path
        self.player = player
        self.poll_seconds = poll_seconds
        self.position = 0
        if start_at_end and os.path.exists(log_path):
            self.position = os.path.getsize(log_path)

    def discard_pending(self) -> None:
        if os.path.exists(self.log_path):
            self.position = os.path.getsize(self.log_path)

    def wait_for_answer(self) -> ChatMessage:
        if not os.path.exists(self.log_path):
            raise RuntimeError(f"Chat log does not exist: {self.log_path}")

        while True:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as log_file:
                log_file.seek(self.position)
                while True:
                    line = log_file.readline()
                    if not line:
                        break
                    parsed = parse_chat_log_line(line)
                    if parsed and self._accepts(parsed):
                        self.position = log_file.tell()
                        return parsed
                self.position = log_file.tell()
            time.sleep(self.poll_seconds)

    def _accepts(self, message: ChatMessage) -> bool:
        if self.player and message.player.lower() != self.player.lower():
            return False
        return bool(message.message.strip())


def parse_chat_log_line(line: str) -> ChatMessage | None:
    stripped = line.rstrip()
    for pattern in MinecraftChatReader.CHAT_PATTERNS:
        match = pattern.search(stripped)
        if match:
            return ChatMessage(player=match.group(1), message=match.group(2).strip())
    return None


class MinecraftChaos:
    def __init__(
        self,
        send_command: Callable[[str], str],
        target: str,
        dry_run: bool,
        punishment_mode: str = "brutal",
    ) -> None:
        self.send_command = send_command
        self.target = target
        self.dry_run = dry_run
        self.punishment_mode = punishment_mode
        self.wrong_answers = 0
        self.mob_wave_size = 2 * PUNISHMENT_MULTIPLIER
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
            ("Charged creeper cameo", self.charged_creepers),
            ("Zombie office party", self.zombie_party),
            ("Skeleton firing squad", self.skeleton_squad),
            ("Pillager pop quiz", self.pillagers),
            ("Vex paperwork", self.vexes),
            ("Ravager surprise", self.ravager),
            ("Blaze drill", self.blazes),
            ("Magma cube bounce house", self.magma_cubes),
            ("Slime audit", self.slimes),
            ("Endermite ankle biters", self.endermites),
            ("Hoglin hallway", self.hoglins),
            ("Zoglin chaos", self.zoglin),
            ("Guardian laser pointer", self.guardians),
            ("Elder guardian tax", self.elder_guardian_curse),
            ("Arrow rain", self.arrow_rain),
            ("Trident rain", self.trident_rain),
            ("Egg storm", self.egg_storm),
            ("Chicken flood", self.chicken_flood),
            ("Bat cave mode", self.bats),
            ("Rabbit distraction", self.rabbits),
            ("Cod flop", self.cod_flop),
            ("Goat headbutt convention", self.goats),
            ("Cobweb trap", self.cobweb_trap),
            ("Ice cube prison", self.ice_prison),
            ("Glass timeout box", self.glass_box),
            ("Dirt timeout box", self.dirt_box),
            ("Waterlogged boots", self.water_cube),
            ("Lava moat", self.lava_moat),
            ("Powder snow pocket", self.powder_snow),
            ("Soul sand stumble field", self.soul_sand_field),
            ("Cactus hug circle", self.cactus_circle),
            ("Berry bush inconvenience", self.berry_bushes),
            ("Hunger pang", self.hunger),
            ("Poison nibble", self.poison),
            ("Wither warning", self.wither_warning),
            ("Levitation oops", self.levitation),
            ("Glow of shame", self.glowing),
            ("Thunderstorm button", self.thunderstorm),
            ("Night shift", self.night_shift),
            ("Rotten flesh consolation prize", self.rotten_flesh),
        ]
        if punishment_mode == "wacky":
            self.punishments = self.build_wacky_punishments()

    def build_wacky_punishments(self) -> list[tuple[str, Callable[[], list[str]]]]:
        return [
            ("Cobweb escape room with spectators", self.wacky_cobweb_escape_room),
            ("Aquarium of poor decisions", self.wacky_aquarium),
            ("Goat court summons", self.wacky_goat_court),
            ("Anvil elevator with no permit", self.wacky_anvil_elevator),
            ("Boat DMV appointment", self.wacky_boat_dmv),
            ("Minecart bureaucracy spiral", self.wacky_minecart_spiral),
            ("Creeper confessional booth", self.wacky_creeper_confessional),
            ("Powder snow smoothie chamber", self.wacky_powder_snow_smoothie),
            ("Enderman staring contest", self.wacky_enderman_staring_contest),
            ("Witch soup kitchen", self.wacky_witch_soup_kitchen),
            ("Pufferfish board meeting", self.wacky_pufferfish_meeting),
            ("Chicken ceiling collapse", self.wacky_chicken_ceiling),
            ("Lava moat speed dating", self.wacky_lava_moat),
            ("Phantom air traffic control", self.wacky_phantom_airport),
            ("Bee lawsuit", self.wacky_bee_lawsuit),
            ("Slime trampoline subpoena", self.wacky_slime_trampoline),
            ("Magma cube paperwork pit", self.wacky_magma_pit),
            ("Cactus gallery opening", self.wacky_cactus_gallery),
            ("The pumpkin HR incident", self.wacky_pumpkin_hr),
            ("Tiny apocalypse sampler platter", self.wacky_sampler_platter),
        ]

    def announce(self, text: str) -> None:
        for line in split_chat_message(text):
            self.run(f"say {line}")

    def punish(self, announcement: str | None = None) -> str:
        self.wrong_answers += 1
        name, command_factory = random.choice(self.punishments)
        commands = command_factory()
        if announcement:
            self.announce(announcement)
        for command in commands:
            self.run(command)
            time.sleep(0.05)
        return name

    def roll_punishment(self) -> tuple[str, list[str]]:
        name, command_factory = random.choice(self.punishments)
        return name, command_factory()

    def run_punishment(self, commands: list[str]) -> None:
        self.wrong_answers += 1
        for command in commands:
            self.run(command)
            time.sleep(0.05)

    def run(self, command: str) -> None:
        if self.dry_run:
            print(f"[minecraft] {command}")
            return
        self.send_command(command)

    def at_target(self, command: str) -> str:
        return f"execute at {self.target} run {command}"

    def as_target(self, command: str) -> str:
        return f"execute as {self.target} at @s run {command}"

    def scaled_count(self, count: int) -> int:
        return count * PUNISHMENT_MULTIPLIER

    def scaled_radius(self, radius: int) -> int:
        return max(radius + PUNISHMENT_MULTIPLIER, radius * 2)

    def summon_many(self, entity: str, count: int, radius: int = 6, y: str = "~", nbt: str = "") -> list[str]:
        scaled_radius = self.scaled_radius(radius)
        return [
            self.at_target(
                f"summon minecraft:{entity} ~{random.randint(-scaled_radius, scaled_radius)} {y} ~{random.randint(-scaled_radius, scaled_radius)} {nbt}".strip()
            )
            for _ in range(self.scaled_count(count))
        ]

    def fill_nearby(self, xz_radius: int, y1: int, y2: int, block: str, replace: str | None = None) -> str:
        command = f"fill ~-{xz_radius} ~{y1} ~-{xz_radius} ~{xz_radius} ~{y2} ~{xz_radius} minecraft:{block}"
        if replace:
            command += f" replace minecraft:{replace}"
        return self.at_target(command)

    def duplicate_nearby_hostiles(self) -> list[str]:
        count = self.mob_wave_size
        self.mob_wave_size = min(self.mob_wave_size * 2, 64 * PUNISHMENT_MULTIPLIER)
        mob = random.choice(HOSTILE_MOBS)
        duplicate_commands = [
            f"execute at {self.target} as @e[type=minecraft:{mob_type},distance=..64,limit=320] at @s run summon minecraft:{mob_type} ~ ~ ~"
            for mob_type in HOSTILE_MOBS
        ]
        escalating_wave = [
            self.at_target(f"summon minecraft:{mob} ~{random.randint(-16, 16)} ~ ~{random.randint(-16, 16)}")
            for _ in range(count)
        ]
        return duplicate_commands + escalating_wave

    def twenty_creepers(self) -> list[str]:
        return [self.at_target(f"summon minecraft:creeper ~{random.randint(-18, 18)} ~ ~{random.randint(-18, 18)}") for _ in range(200)]

    def lightning_ring(self) -> list[str]:
        offsets = [(-5, 0), (5, 0), (0, -5), (0, 5), (-4, -4), (4, 4), (-4, 4), (4, -4)]
        return [self.at_target(f"summon minecraft:lightning_bolt ~{x * 2} ~ ~{z * 2}") for _ in range(PUNISHMENT_MULTIPLIER) for x, z in offsets]

    def anvil_rain(self) -> list[str]:
        return [self.at_target(f"setblock ~{random.randint(-12, 12)} ~24 ~{random.randint(-12, 12)} minecraft:anvil") for _ in range(120)]

    def silverfish_confetti(self) -> list[str]:
        return self.summon_many("silverfish", 18, 4)

    def clumsy_curse(self) -> list[str]:
        return [
            f"effect give {self.target} minecraft:slowness 200 5 true",
            f"effect give {self.target} minecraft:mining_fatigue 200 5 true",
        ]

    def floor_is_lava(self) -> list[str]:
        return [
            self.at_target("fill ~-8 ~-1 ~-8 ~8 ~-1 ~8 minecraft:lava replace minecraft:air"),
            self.at_target("fill ~-8 ~-1 ~-8 ~8 ~-1 ~8 minecraft:magma_block replace minecraft:grass_block"),
        ]

    def pumpkin_helmet(self) -> list[str]:
        return [
            f"item replace entity {self.target} armor.head with minecraft:carved_pumpkin",
            f"effect give {self.target} minecraft:blindness 60 0 true",
            f"effect give {self.target} minecraft:darkness 60 0 true",
        ]

    def launch_player(self) -> list[str]:
        return [
            self.as_target("tp @s ~ ~120 ~"),
            f"effect give {self.target} minecraft:slow_falling 4 0 true",
        ]

    def angry_bees(self) -> list[str]:
        return self.summon_many("bee", 12, 4, "~", "{AngerTime:6000}")

    def cave_spiders(self) -> list[str]:
        return self.summon_many("cave_spider", 10, 5)

    def witches(self) -> list[str]:
        return self.summon_many("witch", 4, 6)

    def blindness(self) -> list[str]:
        return [
            f"effect give {self.target} minecraft:blindness 120 0 true",
            f"effect give {self.target} minecraft:darkness 120 0 true",
        ]

    def phantoms(self) -> list[str]:
        return self.summon_many("phantom", 6, 8, "~16")

    def ghast(self) -> list[str]:
        return self.summon_many("ghast", 3, 12, "~16")

    def tnt_cough(self) -> list[str]:
        return self.summon_many("tnt", 5, 6, "~2", "{Fuse:30}")

    def chicken_jockey(self) -> list[str]:
        return [self.at_target("summon minecraft:chicken ~ ~ ~ {Passengers:[{id:\"minecraft:zombie\",IsBaby:1b}]}") for _ in range(50)]

    def snowball_storm(self) -> list[str]:
        return self.summon_many("snowball", 24, 5, "~10", "{Motion:[0.0,-1.0,0.0]}")

    def suspicious_stew(self) -> list[str]:
        return [
            f"give {self.target} minecraft:suspicious_stew 10",
            f"effect give {self.target} minecraft:nausea 60 1 true",
            f"effect give {self.target} minecraft:hunger 120 5 true",
        ]

    def chunk_bite(self) -> list[str]:
        return [
            self.at_target("fill ~-10 ~-8 ~-10 ~10 ~8 ~10 minecraft:air replace minecraft:stone"),
            self.at_target("fill ~-10 ~-8 ~-10 ~10 ~8 ~10 minecraft:air replace minecraft:dirt"),
            self.at_target("fill ~-10 ~-8 ~-10 ~10 ~8 ~10 minecraft:air replace minecraft:deepslate"),
        ]

    def charged_creepers(self) -> list[str]:
        return self.summon_many("creeper", 6, 7, "~", "{powered:1b,Fuse:25}")

    def zombie_party(self) -> list[str]:
        return self.summon_many("zombie", 24, 8)

    def skeleton_squad(self) -> list[str]:
        return self.summon_many("skeleton", 14, 8)

    def pillagers(self) -> list[str]:
        return self.summon_many("pillager", 8, 9)

    def vexes(self) -> list[str]:
        return self.summon_many("vex", 7, 5)

    def ravager(self) -> list[str]:
        return self.summon_many("ravager", 1, 5)

    def blazes(self) -> list[str]:
        return self.summon_many("blaze", 8, 7)

    def magma_cubes(self) -> list[str]:
        return self.summon_many("magma_cube", 8, 7, "~", "{Size:6}")

    def slimes(self) -> list[str]:
        return self.summon_many("slime", 10, 7, "~", "{Size:6}")

    def endermites(self) -> list[str]:
        return self.summon_many("endermite", 20, 5)

    def hoglins(self) -> list[str]:
        return self.summon_many("hoglin", 4, 7)

    def zoglin(self) -> list[str]:
        return self.summon_many("zoglin", 1, 5)

    def guardians(self) -> list[str]:
        return self.summon_many("guardian", 5, 6)

    def elder_guardian_curse(self) -> list[str]:
        return [
            f"effect give {self.target} minecraft:mining_fatigue 600 5 true",
            f"effect give {self.target} minecraft:slowness 120 3 true",
        ]

    def arrow_rain(self) -> list[str]:
        return self.summon_many("arrow", 30, 8, "~22", "{Motion:[0.0,-2.0,0.0]}")

    def trident_rain(self) -> list[str]:
        return self.summon_many("trident", 12, 8, "~22", "{Motion:[0.0,-2.1,0.0]}")

    def egg_storm(self) -> list[str]:
        return self.summon_many("egg", 28, 8, "~12", "{Motion:[0.0,-1.4,0.0]}")

    def chicken_flood(self) -> list[str]:
        return self.summon_many("chicken", 32, 8)

    def bats(self) -> list[str]:
        return self.summon_many("bat", 28, 10, "~4")

    def rabbits(self) -> list[str]:
        return self.summon_many("rabbit", 18, 7)

    def cod_flop(self) -> list[str]:
        return self.summon_many("cod", 18, 10, "~2")

    def goats(self) -> list[str]:
        return self.summon_many("goat", 8, 7)

    def cobweb_trap(self) -> list[str]:
        return [self.fill_nearby(8, 0, 5, "cobweb", "air")]

    def ice_prison(self) -> list[str]:
        return [
            self.fill_nearby(5, -2, 7, "packed_ice", "air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
        ]

    def glass_box(self) -> list[str]:
        return [
            self.fill_nearby(5, -2, 7, "glass", "air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
        ]

    def dirt_box(self) -> list[str]:
        return [
            self.fill_nearby(5, -2, 7, "dirt", "air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
        ]

    def water_cube(self) -> list[str]:
        return [self.fill_nearby(7, 0, 5, "water", "air")]

    def lava_moat(self) -> list[str]:
        return [
            self.at_target("fill ~-12 ~-1 ~-12 ~12 ~0 ~12 minecraft:lava replace minecraft:air"),
            self.at_target("fill ~-3 ~-1 ~-3 ~3 ~0 ~3 minecraft:air replace minecraft:lava"),
        ]

    def powder_snow(self) -> list[str]:
        return [self.fill_nearby(7, 0, 5, "powder_snow", "air")]

    def soul_sand_field(self) -> list[str]:
        return [self.fill_nearby(12, -1, -1, "soul_sand")]

    def cactus_circle(self) -> list[str]:
        offsets = [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)]
        return [self.at_target(f"setblock ~{x * 3} ~ ~{z * 3} minecraft:cactus") for _ in range(PUNISHMENT_MULTIPLIER) for x, z in offsets]

    def berry_bushes(self) -> list[str]:
        return [self.at_target(f"setblock ~{random.randint(-12, 12)} ~ ~{random.randint(-12, 12)} minecraft:sweet_berry_bush") for _ in range(160)]

    def hunger(self) -> list[str]:
        return [f"effect give {self.target} minecraft:hunger 350 5 true"]

    def poison(self) -> list[str]:
        return [f"effect give {self.target} minecraft:poison 120 2 true"]

    def wither_warning(self) -> list[str]:
        return [f"effect give {self.target} minecraft:wither 80 1 true"]

    def levitation(self) -> list[str]:
        return [
            f"effect give {self.target} minecraft:levitation 20 5 true",
            f"effect give {self.target} minecraft:slow_falling 4 0 true",
        ]

    def glowing(self) -> list[str]:
        return [
            f"effect give {self.target} minecraft:glowing 600 0 true",
            f"effect give {self.target} minecraft:weakness 120 2 true",
        ]

    def thunderstorm(self) -> list[str]:
        return ["weather thunder 600"]

    def night_shift(self) -> list[str]:
        return ["time set midnight"]

    def rotten_flesh(self) -> list[str]:
        return [
            f"give {self.target} minecraft:rotten_flesh 160",
            f"effect give {self.target} minecraft:hunger 160 4 true",
        ]

    def wacky_cobweb_escape_room(self) -> list[str]:
        return [
            self.as_target("tp @s ~ ~1 ~"),
            self.at_target("fill ~-5 ~-1 ~-5 ~5 ~6 ~5 minecraft:glass replace minecraft:air"),
            self.at_target("fill ~-4 ~ ~-4 ~4 ~4 ~4 minecraft:cobweb replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:mining_fatigue 90 4 true",
            *self.summon_many("armor_stand", 12, 5, "~", "{CustomName:'\"Disappointed Witness\"',NoGravity:1b}"),
        ]

    def wacky_aquarium(self) -> list[str]:
        return [
            self.at_target("fill ~-5 ~-1 ~-5 ~5 ~7 ~5 minecraft:glass replace minecraft:air"),
            self.at_target("fill ~-4 ~ ~-4 ~4 ~6 ~4 minecraft:water replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:water"),
            f"effect give {self.target} minecraft:water_breathing 45 0 true",
            *self.summon_many("pufferfish", 18, 4, "~1"),
            *self.summon_many("guardian", 3, 4, "~1"),
        ]

    def wacky_goat_court(self) -> list[str]:
        return [
            self.at_target("fill ~-6 ~-1 ~-6 ~6 ~-1 ~6 minecraft:polished_diorite"),
            self.at_target("fill ~-6 ~ ~-6 ~6 ~4 ~6 minecraft:iron_bars replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:slowness 80 3 true",
            *self.summon_many("goat", 18, 5),
            *self.summon_many("villager", 6, 4, "~", "{VillagerData:{profession:\"minecraft:cleric\"}}"),
        ]

    def wacky_anvil_elevator(self) -> list[str]:
        return [
            self.as_target("tp @s ~ ~35 ~"),
            f"effect give {self.target} minecraft:slow_falling 3 0 true",
            self.at_target("fill ~-3 ~-2 ~-3 ~3 ~-2 ~3 minecraft:slime_block replace minecraft:air"),
            *[self.at_target(f"setblock ~{random.randint(-4, 4)} ~16 ~{random.randint(-4, 4)} minecraft:anvil") for _ in range(80)],
        ]

    def wacky_boat_dmv(self) -> list[str]:
        return [
            self.at_target("fill ~-7 ~-1 ~-7 ~7 ~-1 ~7 minecraft:blue_ice"),
            f"effect give {self.target} minecraft:slowness 45 2 true",
            *self.summon_many("boat", 20, 7),
            *self.summon_many("zombie", 10, 6, "~", "{IsBaby:1b}"),
        ]

    def wacky_minecart_spiral(self) -> list[str]:
        return [
            self.at_target("fill ~-6 ~-1 ~-6 ~6 ~-1 ~6 minecraft:rail replace minecraft:air"),
            f"effect give {self.target} minecraft:nausea 45 1 true",
            *self.summon_many("minecart", 24, 5),
            *self.summon_many("tnt_minecart", 6, 5),
        ]

    def wacky_creeper_confessional(self) -> list[str]:
        return [
            self.at_target("fill ~-3 ~-1 ~-3 ~3 ~4 ~3 minecraft:glass replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:weakness 60 4 true",
            *self.summon_many("creeper", 8, 2, "~", "{powered:1b,Fuse:80}"),
        ]

    def wacky_powder_snow_smoothie(self) -> list[str]:
        return [
            self.at_target("fill ~-6 ~-2 ~-6 ~6 ~5 ~6 minecraft:powder_snow replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:slowness 100 4 true",
            f"effect give {self.target} minecraft:blindness 35 0 true",
            *self.summon_many("stray", 10, 6),
        ]

    def wacky_enderman_staring_contest(self) -> list[str]:
        return [
            "time set midnight",
            f"effect give {self.target} minecraft:glowing 120 0 true",
            f"effect give {self.target} minecraft:blindness 12 0 true",
            *self.summon_many("enderman", 16, 6),
            *self.summon_many("endermite", 24, 4),
        ]

    def wacky_witch_soup_kitchen(self) -> list[str]:
        return [
            f"give {self.target} minecraft:suspicious_stew 32",
            f"effect give {self.target} minecraft:nausea 90 1 true",
            f"effect give {self.target} minecraft:hunger 160 5 true",
            *self.summon_many("witch", 12, 8),
            *self.summon_many("cat", 20, 8),
        ]

    def wacky_pufferfish_meeting(self) -> list[str]:
        return [
            self.at_target("fill ~-5 ~-1 ~-5 ~5 ~4 ~5 minecraft:water replace minecraft:air"),
            self.at_target("fill ~-5 ~5 ~-5 ~5 ~5 ~5 minecraft:glass replace minecraft:air"),
            f"effect give {self.target} minecraft:water_breathing 60 0 true",
            *self.summon_many("pufferfish", 40, 5, "~1"),
        ]

    def wacky_chicken_ceiling(self) -> list[str]:
        return [
            self.at_target("fill ~-5 ~7 ~-5 ~5 ~7 ~5 minecraft:glass replace minecraft:air"),
            *self.summon_many("chicken", 80, 5, "~8"),
            *self.summon_many("egg", 80, 5, "~12", "{Motion:[0.0,-1.5,0.0]}"),
        ]

    def wacky_lava_moat(self) -> list[str]:
        return [
            self.at_target("fill ~-10 ~-1 ~-10 ~10 ~1 ~10 minecraft:lava replace minecraft:air"),
            self.at_target("fill ~-4 ~-1 ~-4 ~4 ~1 ~4 minecraft:air replace minecraft:lava"),
            self.at_target("fill ~-3 ~-1 ~-3 ~3 ~-1 ~3 minecraft:soul_sand"),
            f"effect give {self.target} minecraft:jump_boost 45 128 true",
            *self.summon_many("strider", 12, 8),
        ]

    def wacky_phantom_airport(self) -> list[str]:
        return [
            self.as_target("tp @s ~ ~60 ~"),
            f"effect give {self.target} minecraft:slow_falling 25 0 true",
            f"effect give {self.target} minecraft:glowing 80 0 true",
            *self.summon_many("phantom", 18, 12, "~8"),
        ]

    def wacky_bee_lawsuit(self) -> list[str]:
        return [
            self.at_target("fill ~-6 ~-1 ~-6 ~6 ~4 ~6 minecraft:honey_block replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:slowness 80 5 true",
            *self.summon_many("bee", 36, 6, "~", "{AngerTime:6000}"),
        ]

    def wacky_slime_trampoline(self) -> list[str]:
        return [
            self.at_target("fill ~-8 ~-1 ~-8 ~8 ~-1 ~8 minecraft:slime_block"),
            f"effect give {self.target} minecraft:levitation 8 8 true",
            f"effect give {self.target} minecraft:slow_falling 20 0 true",
            *self.summon_many("slime", 18, 8, "~", "{Size:8}"),
        ]

    def wacky_magma_pit(self) -> list[str]:
        return [
            self.at_target("fill ~-7 ~-3 ~-7 ~7 ~-1 ~7 minecraft:magma_block"),
            self.at_target("fill ~-3 ~ ~-3 ~3 ~4 ~3 minecraft:cobweb replace minecraft:air"),
            f"effect give {self.target} minecraft:fire_resistance 8 0 true",
            *self.summon_many("magma_cube", 14, 7, "~", "{Size:7}"),
        ]

    def wacky_cactus_gallery(self) -> list[str]:
        return [
            self.at_target("fill ~-9 ~-1 ~-9 ~9 ~-1 ~9 minecraft:sand"),
            *[self.at_target(f"setblock ~{random.randint(-9, 9)} ~ ~{random.randint(-9, 9)} minecraft:cactus") for _ in range(90)],
            f"effect give {self.target} minecraft:speed 25 4 true",
        ]

    def wacky_pumpkin_hr(self) -> list[str]:
        return [
            f"item replace entity {self.target} armor.head with minecraft:carved_pumpkin",
            f"effect give {self.target} minecraft:darkness 80 0 true",
            f"effect give {self.target} minecraft:nausea 60 1 true",
            *self.summon_many("armor_stand", 24, 6, "~", "{CustomName:'\"HR Representative\"',NoGravity:1b}"),
        ]

    def wacky_sampler_platter(self) -> list[str]:
        return [
            self.at_target("fill ~-4 ~-1 ~-4 ~4 ~3 ~4 minecraft:cobweb replace minecraft:air"),
            self.as_target("tp @s ~ ~8 ~"),
            f"effect give {self.target} minecraft:blindness 25 0 true",
            f"effect give {self.target} minecraft:hunger 120 4 true",
            *self.summon_many("creeper", 4, 5, "~", "{powered:1b,Fuse:60}"),
            *self.summon_many("witch", 4, 5),
            *self.summon_many("phantom", 5, 8, "~8"),
            *self.summon_many("tnt", 4, 4, "~2", "{Fuse:50}"),
        ]


def split_chat_message(text: str, limit: int = 220) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) > limit:
            lines.append(current)
            current = word
        else:
            current += f" {word}"
    lines.append(current)
    return lines


class LocalTriviaAgent:
    def __init__(self, questions: list[Question]) -> None:
        self.questions = questions
        self.asked: set[str] = set()
        self.streak = 0
        self.turn = 0
        self.difficulty = STARTING_DIFFICULTY

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

    def judge_answer(self, question: Question, user_answer: str) -> Judgement:
        correct = answer_matches(user_answer, question.answers)
        return Judgement(
            correct=correct,
            message="Correct." if correct else "Wrong.",
            expected_answer=", ".join(question.answers[:2]),
        )

    def punishment_message(self, punishment_name: str, question: Question, user_answer: str, expected_answer: str) -> str:
        return f"Punishment rolled: {punishment_name}."


class LlmTriviaAgent:
    def __init__(self, client: TextGenerator, category: str) -> None:
        self.client = client
        self.category = category
        self.streak = 0
        self.turn = 0
        self.difficulty = STARTING_DIFFICULTY
        self.history: list[str] = []

    def next_question(self) -> Question:
        self.turn += 1
        if self.turn % 3 == 0 and self.difficulty < 10:
            self.difficulty += 1

        prompt = f"""
You are the snarky host of a Minecraft trivia punishment game.
Create exactly one general trivia question in the requested difficulty.

Difficulty scale:
1 = extremely easy for almost anyone.
3 = easy school/common knowledge.
5 = medium pub trivia.
7 = hard.
10 = ridiculously hard but still objectively answerable.

Requirements:
- Category preference: {self.category}
- Current difficulty: {self.difficulty}/10
- Avoid repeating these recent questions: {self.history[-12:]}
- Make the question concise.
- The answer must be a short factual answer.
- Keep the question itself clear and answerable; save the attitude for judgement messages.
- Return only JSON with keys: question, expected_answer, difficulty.
"""
        try:
            data = extract_json_object(self.client.generate(prompt))
        except ValueError as error:
            raise RuntimeError(str(error)) from error
        question_text = str(data.get("question", "")).strip()
        expected_answer = str(data.get("expected_answer", "")).strip()
        if not question_text or not expected_answer:
            raise RuntimeError(f"LLM produced an incomplete question: {data}")
        try:
            difficulty = int(data.get("difficulty", self.difficulty))
        except (TypeError, ValueError):
            difficulty = self.difficulty
        difficulty = min(max(difficulty, 1), 10)
        self.history.append(question_text)
        return Question(question_text, (expected_answer,), difficulty)

    def judge_answer(self, question: Question, user_answer: str) -> Judgement:
        prompt = f"""
You are the snarky host of a Minecraft trivia punishment game.

Question: {question.prompt}
Expected answer: {question.answers[0]}
Player answer: {user_answer}

Judge generously for spelling, capitalization, abbreviations, and equivalent wording.
Do not accept a joke answer, contradiction, or answer that is merely related.
Write the message in a playful, snarky voice. Keep it short, Minecraft-chat friendly, and not genuinely cruel.
Return only JSON with keys:
- correct: boolean
- message: one short snarky sentence for the player that clearly says whether they were correct
- expected_answer: the canonical correct answer
"""
        try:
            data = extract_json_object(self.client.generate(prompt))
        except ValueError as error:
            raise RuntimeError(str(error)) from error
        correct = bool(data.get("correct", False))
        message = str(data.get("message", "Correct." if correct else "Wrong.")).strip()
        expected_answer = str(data.get("expected_answer", question.answers[0])).strip()
        return Judgement(correct=correct, message=message, expected_answer=expected_answer)

    def punishment_message(self, punishment_name: str, question: Question, user_answer: str, expected_answer: str) -> str:
        prompt = f"""
You are the snarky host of a Minecraft trivia punishment game.

The player got this question wrong:
Question: {question.prompt}
Expected answer: {expected_answer}
Player answer: {user_answer}

The random punishment selected by the game is: {punishment_name}

Write one short Minecraft-chat-friendly punishment announcement.
Requirements:
- Be playful and snarky, not genuinely cruel.
- Mention the punishment by name.
- Do not include commands or JSON markdown.
- Return only JSON with key: message
"""
        try:
            data = extract_json_object(self.client.generate(prompt))
        except ValueError as error:
            raise RuntimeError(str(error)) from error
        message = str(data.get("message", "")).strip()
        if not message:
            raise RuntimeError(f"LLM produced an incomplete punishment message: {data}")
        return message

    def record_answer(self, correct: bool) -> None:
        if correct:
            self.streak += 1
            if self.streak >= 4 and self.difficulty < 10:
                self.difficulty += 1
                self.streak = 0
            return
        self.streak = 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minecraft trivia chaos via RCON.")
    parser.add_argument("--host", default="127.0.0.1", help="Minecraft RCON host.")
    parser.add_argument("--port", type=int, default=25575, help="Minecraft RCON port.")
    parser.add_argument("--password", default="2006", help="Minecraft RCON password.")
    parser.add_argument("--target", default="@a", help="Minecraft target selector, e.g. @a, @p, or a username.")
    parser.add_argument("--answer-player", help="Only accept answers from this Minecraft username.")
    parser.add_argument("--chat-log", default="logs/latest.log", help="Minecraft server log to tail for player chat answers.")
    parser.add_argument("--chat-poll-seconds", type=float, default=0.5, help="Seconds between chat log polls.")
    parser.add_argument("--questions", type=int, default=100, help="Number of trivia questions to ask.")
    parser.add_argument("--delay-seconds", type=float, default=180.0, help="Seconds to wait between questions.")
    parser.add_argument("--punishment-mode", choices=("brutal", "wacky"), default="brutal", help="Punishment pool to roll from.")
    parser.add_argument("--wacky-punishments", action="store_true", help="Shortcut for --punishment-mode wacky.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands instead of connecting to Minecraft.")
    parser.add_argument("--seed", type=int, help="Random seed for repeatable testing.")
    parser.add_argument("--env-file", default=".env", help="Path to .env file containing API keys.")
    parser.add_argument("--llm-provider", choices=("gemini", "ollama"), default="ollama", help="LLM provider for live questions and judging.")
    parser.add_argument("--check-llm-auth", action="store_true", help="Check the selected LLM credentials and exit.")
    parser.add_argument("--llm-ca-file", help="Path to a CA bundle if Python cannot verify HTTPS certificates.")
    parser.add_argument("--llm-insecure-skip-verify", action="store_true", help="Disable LLM HTTPS certificate verification for local testing.")
    parser.add_argument("--gemini-model", default="gemini-3.7-flash", help="Gemini model used for question generation and judging.")
    parser.add_argument("--gemini-ca-file", help="Path to a CA bundle if Python cannot verify HTTPS certificates.")
    parser.add_argument("--gemini-insecure-skip-verify", action="store_true", help="Disable Gemini HTTPS certificate verification for local testing.")
    parser.add_argument("--ollama-model", default="gpt-oss:120b", help="Ollama model used when --llm-provider ollama.")
    parser.add_argument("--ollama-host", default="https://ollama.com", help="Ollama API host. Use http://localhost:11434 for local Ollama.")
    parser.add_argument("--category", default="general trivia", help="Question category preference.")
    parser.add_argument("--offline-questions", action="store_true", help="Use the built-in question bank instead of an LLM.")
    return parser.parse_args(argv)


def make_command_sender(args: argparse.Namespace) -> tuple[Callable[[str], str], RconClient | None]:
    if args.dry_run:
        return lambda command: print(f"[minecraft] {command}") or "", None
    client = RconClient(args.host, args.port, args.password)
    client.connect()
    return client.command, client


def make_llm_client(args: argparse.Namespace) -> TextGenerator:
    ca_file = args.llm_ca_file or args.gemini_ca_file
    insecure_skip_verify = args.llm_insecure_skip_verify or args.gemini_insecure_skip_verify
    if args.llm_provider == "gemini":
        gemini_key = get_gemini_key()
        if not gemini_key:
            raise RuntimeError("Missing Gemini API key. Add GEMINI_KEY=... to .env or run with --offline-questions.")
        return GeminiClient(
            gemini_key,
            args.gemini_model,
            ca_file=ca_file,
            insecure_skip_verify=insecure_skip_verify,
        )

    ollama_key = get_ollama_key()
    if args.ollama_host.startswith("https://ollama.com") and not ollama_key:
        raise RuntimeError("Missing Ollama API key. Add OLLAMA_API_KEY=... to .env or use --ollama-host http://localhost:11434.")
    return OllamaCloudClient(
        ollama_key or "",
        args.ollama_model,
        host=args.ollama_host,
        ca_file=ca_file,
        insecure_skip_verify=insecure_skip_verify,
    )


def check_llm_auth(client: TextGenerator) -> None:
    if isinstance(client, OllamaCloudClient):
        client.check_auth()
        return
    client.generate('Return only JSON: {"ok": true}')


def main() -> int:
    args = parse_args()
    if args.wacky_punishments:
        args.punishment_mode = "wacky"
    if args.seed is not None:
        random.seed(args.seed)
    load_dotenv(args.env_file)

    if args.offline_questions:
        agent: LocalTriviaAgent | LlmTriviaAgent = LocalTriviaAgent(LOCAL_QUESTION_BANK)
    else:
        try:
            llm_client = make_llm_client(args)
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
            return 2
        if args.check_llm_auth:
            try:
                check_llm_auth(llm_client)
            except RuntimeError as error:
                print(str(error), file=sys.stderr)
                return 2
            print(f"{args.llm_provider} auth check passed.")
            return 0
        agent = LlmTriviaAgent(llm_client, category=args.category)

    try:
        send_command, client = make_command_sender(args)
    except OSError as error:
        print(f"Could not connect to RCON at {args.host}:{args.port}: {error}", file=sys.stderr)
        return 2
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2

    chaos = MinecraftChaos(
        send_command=send_command,
        target=args.target,
        dry_run=args.dry_run,
        punishment_mode=args.punishment_mode,
    )
    chat_reader = MinecraftChatReader(
        args.chat_log,
        player=args.answer_player,
        poll_seconds=args.chat_poll_seconds,
    )

    try:
        chaos.announce("AI trivia chaos is live. Wrong answers roll random punishments.")
        if args.punishment_mode == "wacky":
            chaos.announce("Wacky punishments are enabled. Running away is now more of a suggestion.")
        if args.answer_player:
            chaos.announce(f"Only answers from {args.answer_player} will count.")
        else:
            chaos.announce("The next player chat message after each question counts as the answer.")
        for index in range(1, args.questions + 1):
            try:
                question = agent.next_question()
            except RuntimeError as error:
                print(f"Could not generate question: {error}", file=sys.stderr)
                return 2
            chat_reader.discard_pending()
            chaos.announce(f"Question {index}/{args.questions}. Difficulty {agent.difficulty}/10.")
            chaos.announce(question.prompt)
            try:
                chat_message = chat_reader.wait_for_answer()
            except RuntimeError as error:
                print(str(error), file=sys.stderr)
                return 2
            user_answer = chat_message.message
            if user_answer.strip().lower() in {"quit", "exit", "!quit", "!exit"}:
                chaos.announce("Trivia chaos ended early.")
                break
            try:
                judgement = agent.judge_answer(question, user_answer)
            except RuntimeError as error:
                print(f"Could not judge answer: {error}", file=sys.stderr)
                return 2
            agent.record_answer(judgement.correct)
            chaos.announce(f"{chat_message.player} answered: {user_answer}")
            chaos.announce(judgement.message)
            if not judgement.correct:
                chaos.announce(f"Expected answer: {judgement.expected_answer}")
                punishment_name, punishment_commands = chaos.roll_punishment()
                try:
                    punishment_message = agent.punishment_message(
                        punishment_name,
                        question,
                        user_answer,
                        judgement.expected_answer,
                    )
                except RuntimeError as error:
                    print(f"Could not generate punishment message: {error}", file=sys.stderr)
                    return 2
                chaos.announce(punishment_message)
                chaos.run_punishment(punishment_commands)
            if index < args.questions and args.delay_seconds > 0:
                chaos.announce(f"Next question in {args.delay_seconds:g} seconds.")
                time.sleep(args.delay_seconds)
        chaos.announce("Trivia chaos complete.")
    finally:
        if client is not None:
            client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
