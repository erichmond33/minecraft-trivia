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
from typing import Callable, Protocol, Union


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


@dataclasses.dataclass(frozen=True)
class CommandStep:
    command: str
    delay_fraction: float = 0.0


CommandPlan = list[Union[str, CommandStep]]


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
        command_pause_seconds: float = 0.05,
    ) -> None:
        self.send_command = send_command
        self.target = target
        self.dry_run = dry_run
        self.punishment_mode = punishment_mode
        self.command_pause_seconds = command_pause_seconds
        self.wrong_answers = 0
        self.mob_wave_size = 2 * PUNISHMENT_MULTIPLIER
        self.punishments: list[tuple[str, Callable[[], CommandPlan]]] = [
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
        elif punishment_mode == "wacky2":
            self.punishments = self.build_wacky2_punishments()
        elif punishment_mode == "wacky3":
            self.punishments = self.build_wacky3_punishments()

    def build_wacky_punishments(self) -> list[tuple[str, Callable[[], CommandPlan]]]:
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
            ("Shrinking quiz dome", self.wacky_shrinking_quiz_dome),
            ("Teleport debt collector", self.wacky_teleport_debt_collector),
            ("Nether customs checkpoint", self.wacky_nether_customs_checkpoint),
            ("Sky island repossession", self.wacky_sky_island_repossession),
            ("Raid boss paperwork stack", self.wacky_raid_boss_paperwork_stack),
        ]

    def build_wacky2_punishments(self) -> list[tuple[str, Callable[[], CommandPlan]]]:
        """High-complexity, low-lethality punishments: spectacle over player deletion."""
        return [
            ("Department of Incorrect Answers", self.wacky2_incorrect_answers_department),
            ("Chicken stock exchange collapse", self.wacky2_chicken_stock_exchange),
            ("Sheep color singularity", self.wacky2_sheep_color_singularity),
            ("Quantum rabbit census", self.wacky2_quantum_rabbit_census),
            ("Parrot disco emergency", self.wacky2_parrot_disco_emergency),
            ("Cow bell orchestra audit", self.wacky2_cow_bell_orchestra),
            ("Frog opera licensing dispute", self.wacky2_frog_opera),
            ("Cat tribunal appeals court", self.wacky2_cat_tribunal),
            ("Villager customer support escalation", self.wacky2_villager_customer_support),
            ("Possessed weather forecast", self.wacky2_weather_forecast),
            ("Inventory misfiling catastrophe", self.wacky2_inventory_misfile),
            ("Fake boss fight with no boss", self.wacky2_fake_boss_fight),
            ("Moon-gravity onboarding seminar", self.wacky2_moon_gravity_onboarding),
            ("Museum exhibit: YOU", self.wacky2_museum_exhibit),
            ("Minecart parking enforcement convention", self.wacky2_minecart_parking),
            ("Boat dealership on dry land", self.wacky2_dry_boat_dealership),
            ("Bee-free honey inspection", self.wacky2_honey_inspection),
            ("Snowman corporate retreat", self.wacky2_snowman_retreat),
            ("Horse committee carousel", self.wacky2_horse_committee),
            ("Llama telemarketing convention", self.wacky2_llama_telemarketing),
            ("Pig executive strategy summit", self.wacky2_pig_executive_summit),
            ("Bat radar outage drill", self.wacky2_bat_radar_outage),
            ("Armor-stand press conference", self.wacky2_armor_stand_press_conference),
            ("Village festival nobody approved", self.wacky2_village_festival),
            ("Reality compiler error grand finale", self.wacky2_reality_compiler_error),
        ]

    def build_wacky3_punishments(self) -> list[tuple[str, Callable[[], CommandPlan]]]:
        """Redstone-first spectacle: real mechanisms, absurd signal chains, low lethality."""
        return [
            ("Cathedral organ sequencer", self.wacky3_cathedral_organ),
            ("Piston wave parliament", self.wacky3_piston_wave_parliament),
            ("Hopper clock observatory", self.wacky3_hopper_clock_observatory),
            ("Minecart signal roundabout", self.wacky3_minecart_signal_roundabout),
            ("Flying machine inspection gantry", self.wacky3_flying_machine_inspection),
            ("Seven-segment 404 tribunal", self.wacky3_seven_segment_404),
            ("Observer domino serpent", self.wacky3_observer_domino_serpent),
            ("Dropper Rube Goldberg mailroom", self.wacky3_dropper_rube_goldberg),
            ("Item sorter appeals office", self.wacky3_item_sorter_appeals),
            ("Piston iris bureaucracy portal", self.wacky3_piston_iris_portal),
            ("Elevator to nowhere", self.wacky3_elevator_to_nowhere),
            ("Comparator analog mood laboratory", self.wacky3_comparator_mood_meter),
            ("RS latch argument chamber", self.wacky3_rs_latch_argument),
            ("Dropper T-flip-flop indecision hall", self.wacky3_t_flip_flop_hall),
            ("Four-bit binary shame counter", self.wacky3_binary_shame_counter),
            ("Comparator pulse-extender time tunnel", self.wacky3_pulse_extender_tunnel),
            ("Redstone randomizer casino audit", self.wacky3_randomizer_casino),
            ("Piston tape billboard malfunction", self.wacky3_piston_tape_billboard),
            ("Piston door factory acceptance test", self.wacky3_door_factory),
            ("Lamp matrix scanner overload", self.wacky3_lamp_matrix_scanner),
            ("Minecart logic junction committee", self.wacky3_minecart_logic_junction),
            ("Bell and note-block relay tower", self.wacky3_bell_relay_tower),
            ("Slime-block mechanical heart", self.wacky3_slime_mechanical_heart),
            ("Redstone logic-gate calculator cosplay", self.wacky3_logic_gate_calculator),
            ("Grand unified Rube Goldberg cathedral", self.wacky3_grand_rube_goldberg),
        ]

    def wacky2_tell(self, text: str, color: str = "aqua") -> str:
        payload = json.dumps({"text": text, "color": color})
        return f"tellraw {self.target} {payload}"

    def wacky2_sound(self, sound: str, pitch: float = 1.0, volume: float = 1.0) -> str:
        return self.as_target(f"playsound minecraft:{sound} master @s ~ ~ ~ {volume:g} {pitch:g}")

    def wacky2_particles(self, particle: str, count: int = 120, spread: float = 2.5, speed: float = 0.08) -> str:
        particle_id, separator, particle_args = particle.partition(" ")
        particle_spec = f"minecraft:{particle_id}"
        if separator:
            particle_spec += f" {particle_args}"
        return self.at_target(
            f"particle {particle_spec} ~ ~1 ~ {spread:g} {spread:g} {spread:g} {speed:g} {count} force"
        )

    def wacky2_temp_mobs(
        self,
        entity: str,
        count: int,
        radius: int = 7,
        y: str = "~",
        extra_nbt: str = "",
    ) -> list[str]:
        extra = extra_nbt.strip()
        if extra.startswith("{") and extra.endswith("}"):
            extra = extra[1:-1].strip()
        parts = ['Tags:["wacky2_temp"]']
        if extra:
            parts.append(extra)
        nbt = "{" + ",".join(parts) + "}"
        return [
            self.at_target(
                f"summon minecraft:{entity} ~{random.randint(-radius, radius)} {y} "
                f"~{random.randint(-radius, radius)} {nbt}"
            )
            for _ in range(count)
        ]

    def wacky2_opening(self, title: str, subtitle: str) -> CommandPlan:
        title_json = json.dumps({"text": title, "color": "light_purple", "bold": True})
        subtitle_json = json.dumps({"text": subtitle, "color": "yellow", "italic": True})
        return [
            f"effect give {self.target} minecraft:resistance 240 4 true",
            f"effect give {self.target} minecraft:regeneration 240 2 true",
            f"effect give {self.target} minecraft:absorption 240 4 true",
            f"effect give {self.target} minecraft:fire_resistance 240 0 true",
            f"effect give {self.target} minecraft:water_breathing 240 0 true",
            f"effect give {self.target} minecraft:slow_falling 240 0 true",
            f"effect give {self.target} minecraft:glowing 240 0 true",
            f"title {self.target} times 4 55 10",
            f"title {self.target} title {title_json}",
            f"title {self.target} subtitle {subtitle_json}",
            self.wacky2_sound("block.note_block.pling", 1.75),
            self.wacky2_particles("happy_villager", 90, 2.0, 0.1),
            self.wacky2_tell("WACKY-2 SAFETY PROTOCOL: spectacle has priority over homicide.", "green"),
        ]

    def wacky2_finale(self, final_line: str) -> CommandPlan:
        return [
            self.stage(0.92, self.wacky2_sound("entity.experience_orb.pickup", 1.8)),
            self.stage(0.93, self.wacky2_particles("totem_of_undying", 180, 3.0, 0.2)),
            self.stage(0.94, self.wacky2_tell(final_line, "gold")),
            self.stage(0.95, self.at_target("kill @e[tag=wacky2_temp,distance=..48]")),
            self.stage(0.96, f"effect clear {self.target} minecraft:nausea"),
            self.stage(0.965, f"effect clear {self.target} minecraft:darkness"),
            self.stage(0.97, f"effect clear {self.target} minecraft:levitation"),
            self.stage(0.972, f"effect clear {self.target} minecraft:speed"),
            self.stage(0.974, f"effect clear {self.target} minecraft:jump_boost"),
            self.stage(0.976, f"effect clear {self.target} minecraft:night_vision"),
            self.stage(0.978, f"effect clear {self.target} minecraft:haste"),
            self.stage(0.980, f"effect clear {self.target} minecraft:invisibility"),
            self.stage(0.982, f"effect clear {self.target} minecraft:glowing"),
            self.stage(0.984, f"effect clear {self.target} minecraft:slow_falling"),
            self.stage(0.986, f"effect clear {self.target} minecraft:water_breathing"),
            self.stage(0.988, f"effect clear {self.target} minecraft:fire_resistance"),
            self.stage(0.990, f"effect clear {self.target} minecraft:absorption"),
            self.stage(0.992, f"effect clear {self.target} minecraft:regeneration"),
            self.stage(0.994, f"effect clear {self.target} minecraft:resistance"),
            self.stage(0.996, f"title {self.target} clear"),
        ]

    def wacky3_at(self, command: str) -> str:
        return f"execute at @e[type=minecraft:marker,tag=wacky3_anchor] run {command}"

    def wacky3_set(self, x: int, y: int, z: int, block: str, mode: str = "replace") -> str:
        return self.wacky3_at(f"setblock ~{x} ~{y} ~{z} minecraft:{block} {mode}")

    def wacky3_fill(
        self,
        x1: int,
        y1: int,
        z1: int,
        x2: int,
        y2: int,
        z2: int,
        block: str,
        mode: str = "replace",
    ) -> str:
        return self.wacky3_at(
            f"fill ~{x1} ~{y1} ~{z1} ~{x2} ~{y2} ~{z2} minecraft:{block} {mode}"
        )

    def wacky3_item_replace(self, x: int, y: int, z: int, slot: int, item: str, count: int = 1) -> str:
        return self.wacky3_at(
            f"item replace block ~{x} ~{y} ~{z} container.{slot} with minecraft:{item} {count}"
        )

    def wacky3_pulse(self, x: int, y: int, z: int, start: float, duration: float = 0.025) -> CommandPlan:
        return [
            self.stage(start, self.wacky3_set(x, y, z, "redstone_block")),
            self.stage(min(0.90, start + duration), self.wacky3_set(x, y, z, "air")),
        ]

    def wacky3_temp_entity(self, entity: str, x: int, y: int, z: int, nbt: str = "") -> str:
        extra = nbt.strip()
        if extra.startswith("{") and extra.endswith("}"):
            extra = extra[1:-1].strip()
        tags = 'Tags:["wacky3_temp"]'
        payload = "{" + tags + ("," + extra if extra else "") + "}"
        return self.wacky3_at(f"summon minecraft:{entity} ~{x} ~{y} ~{z} {payload}")

    def wacky3_opening(self, title: str, subtitle: str) -> CommandPlan:
        title_json = json.dumps({"text": title, "color": "red", "bold": True})
        subtitle_json = json.dumps({"text": subtitle, "color": "gold", "italic": True})
        return [
            "kill @e[type=minecraft:marker,tag=wacky3_anchor]",
            "kill @e[tag=wacky3_temp]",
            f"effect give {self.target} minecraft:resistance 240 4 true",
            f"effect give {self.target} minecraft:regeneration 240 2 true",
            f"effect give {self.target} minecraft:absorption 240 4 true",
            f"effect give {self.target} minecraft:fire_resistance 240 0 true",
            f"effect give {self.target} minecraft:slow_falling 240 0 true",
            f"execute as {self.target} at @s run summon minecraft:marker ~ ~ ~ {{Tags:[\"wacky3_anchor\"]}}",
            f"title {self.target} times 3 60 8",
            f"title {self.target} title {title_json}",
            f"title {self.target} subtitle {subtitle_json}",
            self.wacky2_sound("block.piston.extend", 0.65, 1.2),
            self.wacky2_sound("block.note_block.bit", 1.45, 1.0),
            self.wacky2_tell("WACKY-3: REDSTONE ENGINEERING DEPARTMENT HAS ASSUMED CONTROL.", "red"),
            self.wacky3_fill(-18, 7, -18, 18, 7, 18, "smooth_quartz", "keep"),
            self.wacky3_fill(-18, 8, -18, 18, 8, 18, "redstone_lamp", "keep"),
            self.wacky3_fill(-17, 8, -17, 17, 8, 17, "smooth_quartz", "replace"),
        ]

    def wacky3_cleanup_commands(self) -> list[str]:
        blocks = [
            "redstone_wire", "redstone_torch", "redstone_wall_torch", "repeater", "comparator",
            "observer", "piston", "sticky_piston", "redstone_block", "redstone_lamp", "note_block",
            "hopper", "dropper", "dispenser", "rail", "powered_rail", "detector_rail", "activator_rail",
            "target", "bell", "barrel", "lever", "stone_button", "oak_button", "stone_pressure_plate",
            "oak_pressure_plate", "iron_trapdoor", "slime_block", "honey_block", "smooth_quartz",
            "tinted_glass", "glass", "white_stained_glass", "red_stained_glass", "blue_stained_glass",
            "lime_stained_glass", "black_concrete", "white_concrete", "red_concrete", "blue_concrete",
            "yellow_concrete", "lime_concrete", "orange_concrete", "purple_concrete", "magenta_concrete",
            "cyan_concrete", "gold_block", "clay", "packed_ice", "bone_block", "iron_block", "copper_block",
            "white_wool", "red_wool", "blue_wool", "lime_wool", "yellow_wool", "orange_wool",
            "magenta_wool", "purple_wool", "cyan_wool", "light_blue_wool", "composter",
        ]
        return [
            self.wacky3_at(f"fill ~-19 ~7 ~-19 ~19 ~25 ~19 minecraft:air replace minecraft:{block}")
            for block in blocks
        ]

    def wacky3_finale(self, line: str) -> CommandPlan:
        plan: CommandPlan = [
            self.stage(0.91, self.wacky2_particles("electric_spark", 220, 5.0, 0.22)),
            self.stage(0.92, self.wacky2_sound("block.note_block.pling", 1.9, 1.3)),
            self.stage(0.925, self.wacky2_tell(line, "gold")),
        ]
        plan.extend(self.stage(0.95, command) for command in self.wacky3_cleanup_commands())
        plan.extend([
            self.stage(0.975, "kill @e[tag=wacky3_temp]"),
            self.stage(0.98, "kill @e[type=minecraft:marker,tag=wacky3_anchor]"),
            self.stage(0.985, f"effect clear {self.target} minecraft:slow_falling"),
            self.stage(0.988, f"effect clear {self.target} minecraft:absorption"),
            self.stage(0.991, f"effect clear {self.target} minecraft:regeneration"),
            self.stage(0.994, f"effect clear {self.target} minecraft:resistance"),
            self.stage(0.996, f"effect clear {self.target} minecraft:fire_resistance"),
            self.stage(0.998, f"title {self.target} clear"),
        ])
        return plan

    def wacky3_support_line(self, x1: int, x2: int, y: int, z: int, block: str = "smooth_quartz") -> list[str]:
        return [self.wacky3_set(x, y, z, block) for x in range(x1, x2 + 1)]

    def wacky3_lamp_digit(self, origin_x: int, origin_y: int, z: int, digit: int) -> list[str]:
        segments = {
            0: "ab cdef".replace(" ", ""), 1: "bc", 2: "abdeg", 3: "abcdg", 4: "bcfg",
            5: "acdfg", 6: "acdefg", 7: "abc", 8: "abcdefg", 9: "abcdfg",
        }[digit]
        coords = {
            "a": [(1, 6), (2, 6), (3, 6)],
            "b": [(4, 5), (4, 4)],
            "c": [(4, 2), (4, 1)],
            "d": [(1, 0), (2, 0), (3, 0)],
            "e": [(0, 2), (0, 1)],
            "f": [(0, 5), (0, 4)],
            "g": [(1, 3), (2, 3), (3, 3)],
        }
        commands: list[str] = []
        for segment, points in coords.items():
            for dx, dy in points:
                block = "redstone_lamp[lit=true]" if segment in segments else "redstone_lamp[lit=false]"
                commands.append(self.wacky3_set(origin_x + dx, origin_y + dy, z, block))
                commands.append(self.wacky3_set(origin_x + dx, origin_y + dy, z + 1, "redstone_block" if segment in segments else "black_concrete"))
        return commands

    def announce(self, text: str) -> None:
        for line in split_chat_message(text):
            self.run(f"say {line}")

    def punish(self, announcement: str | None = None) -> str:
        name, command_factory = random.choice(self.punishments)
        commands = command_factory()
        if announcement:
            self.announce(announcement)
        self.run_punishment(commands)
        return name

    def roll_punishment(self) -> tuple[str, CommandPlan]:
        name, command_factory = random.choice(self.punishments)
        return name, command_factory()

    def run_punishment(self, commands: CommandPlan, delay_budget_seconds: float = 0.0) -> float:
        self.wrong_answers += 1
        started_at = time.monotonic()

        # Wacky-3 plans deliberately contain hundreds of construction commands plus timed
        # activations. Build the entire redstone machine first, then start its animation clock.
        # Stable sorting preserves author order for events with the same delay fraction.
        if self.punishment_mode == "wacky3":
            immediate = [step for step in commands if not isinstance(step, CommandStep)]
            staged = sorted(
                (step for step in commands if isinstance(step, CommandStep)),
                key=lambda step: step.delay_fraction,
            )
            for command in immediate:
                self.run(command)
                if self.command_pause_seconds > 0:
                    time.sleep(self.command_pause_seconds)
            animation_started_at = time.monotonic()
            for step in staged:
                target_elapsed = max(0.0, min(step.delay_fraction, 1.0)) * max(0.0, delay_budget_seconds)
                current_elapsed = time.monotonic() - animation_started_at
                if target_elapsed > current_elapsed:
                    time.sleep(target_elapsed - current_elapsed)
                self.run(step.command)
                if self.command_pause_seconds > 0:
                    time.sleep(self.command_pause_seconds)
            return time.monotonic() - started_at

        for step in commands:
            if isinstance(step, CommandStep):
                target_elapsed = max(0.0, min(step.delay_fraction, 1.0)) * max(0.0, delay_budget_seconds)
                current_elapsed = time.monotonic() - started_at
                if target_elapsed > current_elapsed:
                    time.sleep(target_elapsed - current_elapsed)
                command = step.command
            else:
                command = step
            self.run(command)
            if self.command_pause_seconds > 0:
                time.sleep(self.command_pause_seconds)
        return time.monotonic() - started_at

    def run(self, command: str) -> None:
        if self.dry_run:
            print(f"[minecraft] {command}")
            return
        self.send_command(command)

    def at_target(self, command: str) -> str:
        return f"execute at {self.target} run {command}"

    def as_target(self, command: str) -> str:
        return f"execute as {self.target} at @s run {command}"

    def stage(self, delay_fraction: float, command: str) -> CommandStep:
        return CommandStep(command=command, delay_fraction=delay_fraction)

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

    def wacky_cobweb_escape_room(self) -> CommandPlan:
        return [
            self.as_target("tp @s ~ ~1 ~"),
            self.at_target("fill ~-7 ~-1 ~-7 ~7 ~7 ~7 minecraft:tinted_glass replace minecraft:air"),
            self.at_target("fill ~-6 ~ ~-6 ~6 ~5 ~6 minecraft:cobweb replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:mining_fatigue 220 5 true",
            *self.summon_many("armor_stand", 6, 6, "~", "{CustomName:'\"Disappointed Witness\"',NoGravity:1b}"),
            self.stage(0.25, self.at_target("fill ~-4 ~ ~-4 ~4 ~4 ~4 minecraft:cobweb replace minecraft:air")),
            self.stage(0.50, self.at_target("fill ~-2 ~ ~-2 ~2 ~3 ~2 minecraft:powder_snow replace minecraft:air")),
            self.stage(0.75, self.at_target("summon minecraft:creeper ~ ~ ~ {powered:1b,Fuse:70,CustomName:'\"Escape Room Employee\"'}")),
            self.stage(0.95, self.at_target("fill ~-7 ~-1 ~-7 ~7 ~7 ~7 minecraft:air replace minecraft:tinted_glass")),
        ]

    def wacky_aquarium(self) -> CommandPlan:
        return [
            self.at_target("fill ~-6 ~-2 ~-6 ~6 ~7 ~6 minecraft:glass replace minecraft:air"),
            self.at_target("fill ~-5 ~-1 ~-5 ~5 ~6 ~5 minecraft:water replace minecraft:air"),
            f"effect give {self.target} minecraft:water_breathing 25 0 true",
            *self.summon_many("pufferfish", 10, 5, "~1"),
            self.stage(0.22, self.at_target("fill ~-5 ~-1 ~-5 ~5 ~1 ~5 minecraft:bubble_column replace minecraft:water")),
            self.stage(0.45, self.at_target("fill ~-5 ~-2 ~-5 ~5 ~-2 ~5 minecraft:magma_block")),
            self.stage(0.65, self.at_target("summon minecraft:elder_guardian ~ ~2 ~")),
            self.stage(0.82, self.at_target("fill ~-5 ~5 ~-5 ~5 ~6 ~5 minecraft:ice replace minecraft:water")),
            self.stage(0.96, f"effect clear {self.target} minecraft:water_breathing"),
        ]

    def wacky_goat_court(self) -> CommandPlan:
        return [
            self.at_target("fill ~-8 ~-1 ~-8 ~8 ~-1 ~8 minecraft:polished_diorite"),
            self.at_target("fill ~-8 ~ ~-8 ~8 ~5 ~8 minecraft:iron_bars replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:slowness 160 4 true",
            *self.summon_many("goat", 10, 6),
            *self.summon_many("villager", 4, 5, "~", "{VillagerData:{profession:\"minecraft:cleric\"}}"),
            self.stage(0.30, self.at_target("fill ~-5 ~ ~-5 ~5 ~3 ~5 minecraft:cobweb replace minecraft:air")),
            self.stage(0.55, self.as_target("tp @s ~ ~1 ~")),
            self.stage(0.56, self.at_target("summon minecraft:ravager ~ ~ ~")),
            self.stage(0.78, self.at_target("summon minecraft:lightning_bolt ~ ~ ~")),
        ]

    def wacky_anvil_elevator(self) -> CommandPlan:
        return [
            self.as_target("tp @s ~ ~55 ~"),
            f"effect give {self.target} minecraft:slow_falling 5 0 true",
            self.at_target("fill ~-3 ~-2 ~-3 ~3 ~-2 ~3 minecraft:slime_block replace minecraft:air"),
            *[self.at_target(f"setblock ~{random.randint(-5, 5)} ~22 ~{random.randint(-5, 5)} minecraft:anvil") for _ in range(45)],
            self.stage(0.20, f"effect clear {self.target} minecraft:slow_falling"),
            self.stage(0.35, self.as_target("tp @s ~ ~18 ~")),
            self.stage(0.50, self.at_target("fill ~-5 ~20 ~-5 ~5 ~20 ~5 minecraft:pointed_dripstone replace minecraft:air")),
            self.stage(0.72, self.at_target("summon minecraft:tnt ~ ~8 ~ {Fuse:60}")),
            self.stage(0.92, f"effect give {self.target} minecraft:slow_falling 8 0 true"),
        ]

    def wacky_boat_dmv(self) -> CommandPlan:
        return [
            self.at_target("fill ~-11 ~-1 ~-11 ~11 ~-1 ~11 minecraft:blue_ice"),
            self.at_target("fill ~-11 ~ ~-11 ~11 ~3 ~11 minecraft:glass_pane replace minecraft:air"),
            f"effect give {self.target} minecraft:slowness 160 3 true",
            *self.summon_many("boat", 16, 9),
            self.stage(0.25, self.at_target("fill ~-10 ~ ~-10 ~10 ~1 ~10 minecraft:water replace minecraft:air")),
            self.stage(0.42, self.as_target("tp @s ~9 ~ ~-9")),
            self.stage(0.58, self.as_target("tp @s ~-18 ~ ~18")),
            self.stage(0.72, self.summon_many("zombie", 6, 4, "~", "{IsBaby:1b}")[0]),
            self.stage(0.90, self.at_target("summon minecraft:warden ~ ~ ~")),
        ]

    def wacky_minecart_spiral(self) -> CommandPlan:
        return [
            self.at_target("fill ~-9 ~-1 ~-9 ~9 ~-1 ~9 minecraft:powered_rail replace minecraft:air"),
            f"effect give {self.target} minecraft:nausea 140 1 true",
            *self.summon_many("minecart", 14, 8),
            self.stage(0.18, self.at_target("fill ~-7 ~ ~-7 ~7 ~2 ~7 minecraft:cobweb replace minecraft:air")),
            self.stage(0.38, self.as_target("tp @s ~ ~2 ~")),
            self.stage(0.55, self.at_target("summon minecraft:tnt_minecart ~ ~ ~")),
            self.stage(0.74, self.at_target("summon minecraft:tnt_minecart ~2 ~ ~2")),
            self.stage(0.91, self.at_target("summon minecraft:creeper ~ ~ ~ {powered:1b,Fuse:50}")),
        ]

    def wacky_creeper_confessional(self) -> CommandPlan:
        return [
            self.at_target("fill ~-5 ~-1 ~-5 ~5 ~5 ~5 minecraft:glass replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:weakness 180 4 true",
            *self.summon_many("creeper", 4, 3, "~", "{powered:1b,Fuse:100}"),
            self.stage(0.20, self.at_target("fill ~-4 ~ ~-4 ~4 ~3 ~4 minecraft:cobweb replace minecraft:air")),
            self.stage(0.40, self.at_target("summon minecraft:creeper ~4 ~ ~ {powered:1b,Fuse:70}")),
            self.stage(0.60, self.at_target("summon minecraft:creeper ~-4 ~ ~ {powered:1b,Fuse:50}")),
            self.stage(0.80, self.at_target("summon minecraft:creeper ~ ~ ~4 {powered:1b,Fuse:35}")),
            self.stage(0.96, self.at_target("summon minecraft:tnt ~ ~2 ~ {Fuse:20}")),
        ]

    def wacky_powder_snow_smoothie(self) -> CommandPlan:
        return [
            self.at_target("fill ~-7 ~-2 ~-7 ~7 ~6 ~7 minecraft:powder_snow replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:slowness 180 5 true",
            f"effect give {self.target} minecraft:darkness 90 0 true",
            *self.summon_many("stray", 7, 6),
            self.stage(0.24, self.at_target("fill ~-3 ~ ~-3 ~3 ~4 ~3 minecraft:cobweb replace minecraft:air")),
            self.stage(0.48, self.at_target("fill ~-6 ~-2 ~-6 ~6 ~-2 ~6 minecraft:blue_ice")),
            self.stage(0.70, self.summon_many("skeleton", 4, 4)[0]),
            self.stage(0.90, self.at_target("setblock ~ ~4 ~ minecraft:powder_snow")),
        ]

    def wacky_enderman_staring_contest(self) -> CommandPlan:
        return [
            "time set midnight",
            f"effect give {self.target} minecraft:glowing 220 0 true",
            f"effect give {self.target} minecraft:darkness 90 0 true",
            *self.summon_many("enderman", 8, 6),
            self.stage(0.20, self.at_target("fill ~-6 ~-1 ~-6 ~6 ~-1 ~6 minecraft:soul_sand")),
            self.stage(0.35, self.as_target("tp @s ~8 ~ ~8")),
            self.stage(0.55, self.as_target("tp @s ~-16 ~ ~-16")),
            self.stage(0.75, self.summon_many("endermite", 8, 4)[0]),
            self.stage(0.93, self.at_target("summon minecraft:enderman ~ ~ ~ {CustomName:'\"Final Examiner\"'}")),
        ]

    def wacky_witch_soup_kitchen(self) -> CommandPlan:
        return [
            f"give {self.target} minecraft:suspicious_stew 32",
            f"effect give {self.target} minecraft:nausea 160 1 true",
            f"effect give {self.target} minecraft:hunger 160 5 true",
            *self.summon_many("witch", 7, 8),
            self.stage(0.25, f"effect give {self.target} minecraft:poison 18 1 true"),
            self.stage(0.45, f"effect give {self.target} minecraft:blindness 20 0 true"),
            self.stage(0.63, self.at_target("fill ~-5 ~ ~-5 ~5 ~2 ~5 minecraft:sweet_berry_bush replace minecraft:air")),
            self.stage(0.84, self.summon_many("cat", 8, 8)[0]),
        ]

    def wacky_pufferfish_meeting(self) -> CommandPlan:
        return [
            self.at_target("fill ~-7 ~-1 ~-7 ~7 ~5 ~7 minecraft:water replace minecraft:air"),
            self.at_target("fill ~-7 ~6 ~-7 ~7 ~6 ~7 minecraft:glass replace minecraft:air"),
            f"effect give {self.target} minecraft:water_breathing 40 0 true",
            *self.summon_many("pufferfish", 22, 6, "~1"),
            self.stage(0.25, self.at_target("fill ~-6 ~-1 ~-6 ~6 ~-1 ~6 minecraft:magma_block")),
            self.stage(0.50, self.at_target("summon minecraft:guardian ~ ~2 ~")),
            self.stage(0.75, f"effect give {self.target} minecraft:poison 12 1 true"),
            self.stage(0.92, f"effect clear {self.target} minecraft:water_breathing"),
        ]

    def wacky_chicken_ceiling(self) -> CommandPlan:
        return [
            self.at_target("fill ~-7 ~8 ~-7 ~7 ~8 ~7 minecraft:glass replace minecraft:air"),
            *self.summon_many("chicken", 25, 6, "~9"),
            self.stage(0.20, self.summon_many("egg", 20, 5, "~14", "{Motion:[0.0,-1.8,0.0]}")[0]),
            self.stage(0.40, self.at_target("fill ~-6 ~ ~-6 ~6 ~2 ~6 minecraft:cobweb replace minecraft:air")),
            self.stage(0.60, self.summon_many("egg", 20, 5, "~14", "{Motion:[0.0,-2.0,0.0]}")[0]),
            self.stage(0.80, self.at_target("summon minecraft:creeper ~ ~ ~ {Fuse:60,CustomName:'\"Egg Inspector\"'}")),
        ]

    def wacky_lava_moat(self) -> CommandPlan:
        return [
            self.at_target("fill ~-12 ~-1 ~-12 ~12 ~1 ~12 minecraft:lava replace minecraft:air"),
            self.at_target("fill ~-5 ~-1 ~-5 ~5 ~1 ~5 minecraft:air replace minecraft:lava"),
            self.at_target("fill ~-3 ~-1 ~-3 ~3 ~-1 ~3 minecraft:soul_sand"),
            f"effect give {self.target} minecraft:jump_boost 120 128 true",
            *self.summon_many("strider", 6, 8),
            self.stage(0.25, self.at_target("fill ~-7 ~-1 ~-7 ~7 ~1 ~7 minecraft:lava replace minecraft:air")),
            self.stage(0.50, self.at_target("fill ~-4 ~ ~-4 ~4 ~3 ~4 minecraft:cobweb replace minecraft:air")),
            self.stage(0.70, self.as_target("tp @s ~ ~1 ~")),
            self.stage(0.88, self.at_target("summon minecraft:blaze ~ ~2 ~")),
        ]

    def wacky_phantom_airport(self) -> CommandPlan:
        return [
            self.as_target("tp @s ~ ~75 ~"),
            f"effect give {self.target} minecraft:slow_falling 18 0 true",
            f"effect give {self.target} minecraft:glowing 180 0 true",
            *self.summon_many("phantom", 9, 12, "~8"),
            self.stage(0.28, f"effect clear {self.target} minecraft:slow_falling"),
            self.stage(0.44, self.at_target("summon minecraft:phantom ~ ~10 ~ {Size:4}")),
            self.stage(0.58, self.as_target("tp @s ~18 ~ ~-18")),
            self.stage(0.74, self.at_target("fill ~-4 ~-3 ~-4 ~4 ~-3 ~4 minecraft:slime_block replace minecraft:air")),
            self.stage(0.90, self.at_target("summon minecraft:tnt ~ ~10 ~ {Fuse:40}")),
        ]

    def wacky_bee_lawsuit(self) -> CommandPlan:
        return [
            self.at_target("fill ~-8 ~-1 ~-8 ~8 ~4 ~8 minecraft:honey_block replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:slowness 180 5 true",
            *self.summon_many("bee", 18, 7, "~", "{AngerTime:6000}"),
            self.stage(0.25, self.at_target("fill ~-6 ~ ~-6 ~6 ~3 ~6 minecraft:cobweb replace minecraft:air")),
            self.stage(0.50, self.at_target("summon minecraft:bee ~ ~ ~ {AngerTime:6000,CustomName:'\"Lead Counsel\"'}")),
            self.stage(0.72, f"effect give {self.target} minecraft:poison 12 0 true"),
            self.stage(0.92, self.at_target("fill ~-8 ~-1 ~-8 ~8 ~4 ~8 minecraft:air replace minecraft:honey_block")),
        ]

    def wacky_slime_trampoline(self) -> CommandPlan:
        return [
            self.at_target("fill ~-10 ~-1 ~-10 ~10 ~-1 ~10 minecraft:slime_block"),
            f"effect give {self.target} minecraft:levitation 10 12 true",
            f"effect give {self.target} minecraft:slow_falling 25 0 true",
            *self.summon_many("slime", 10, 8, "~", "{Size:8}"),
            self.stage(0.25, self.as_target("tp @s ~ ~25 ~")),
            self.stage(0.42, self.at_target("fill ~-4 ~15 ~-4 ~4 ~15 ~4 minecraft:anvil replace minecraft:air")),
            self.stage(0.62, f"effect clear {self.target} minecraft:slow_falling"),
            self.stage(0.82, self.at_target("summon minecraft:magma_cube ~ ~ ~ {Size:8}")),
        ]

    def wacky_magma_pit(self) -> CommandPlan:
        return [
            self.at_target("fill ~-9 ~-3 ~-9 ~9 ~-1 ~9 minecraft:magma_block"),
            self.at_target("fill ~-5 ~ ~-5 ~5 ~4 ~5 minecraft:cobweb replace minecraft:air"),
            f"effect give {self.target} minecraft:fire_resistance 12 0 true",
            *self.summon_many("magma_cube", 7, 7, "~", "{Size:7}"),
            self.stage(0.25, self.at_target("fill ~-6 ~ ~-6 ~6 ~1 ~6 minecraft:lava replace minecraft:air")),
            self.stage(0.45, f"effect clear {self.target} minecraft:fire_resistance"),
            self.stage(0.66, self.as_target("tp @s ~ ~2 ~")),
            self.stage(0.88, self.at_target("summon minecraft:blaze ~ ~2 ~")),
        ]

    def wacky_cactus_gallery(self) -> CommandPlan:
        return [
            self.at_target("fill ~-12 ~-1 ~-12 ~12 ~-1 ~12 minecraft:sand"),
            *[self.at_target(f"setblock ~{random.randint(-12, 12)} ~ ~{random.randint(-12, 12)} minecraft:cactus") for _ in range(55)],
            f"effect give {self.target} minecraft:speed 80 5 true",
            self.stage(0.24, self.at_target("fill ~-8 ~ ~-8 ~8 ~2 ~8 minecraft:sweet_berry_bush replace minecraft:air")),
            self.stage(0.48, self.as_target("tp @s ~10 ~ ~10")),
            self.stage(0.68, self.as_target("tp @s ~-20 ~ ~-20")),
            self.stage(0.90, self.at_target("summon minecraft:ravager ~ ~ ~")),
        ]

    def wacky_pumpkin_hr(self) -> CommandPlan:
        return [
            f"item replace entity {self.target} armor.head with minecraft:carved_pumpkin",
            f"effect give {self.target} minecraft:darkness 160 0 true",
            f"effect give {self.target} minecraft:nausea 120 1 true",
            *self.summon_many("armor_stand", 10, 6, "~", "{CustomName:'\"HR Representative\"',NoGravity:1b}"),
            self.stage(0.25, self.at_target("fill ~-5 ~ ~-5 ~5 ~3 ~5 minecraft:glass_pane replace minecraft:air")),
            self.stage(0.50, self.as_target("tp @s ~ ~1 ~")),
            self.stage(0.52, self.at_target("summon minecraft:vex ~ ~2 ~")),
            self.stage(0.75, self.at_target("summon minecraft:vex ~ ~2 ~")),
            self.stage(0.94, f"item replace entity {self.target} armor.head with minecraft:air"),
        ]

    def wacky_sampler_platter(self) -> CommandPlan:
        return [
            self.at_target("fill ~-6 ~-1 ~-6 ~6 ~4 ~6 minecraft:cobweb replace minecraft:air"),
            self.as_target("tp @s ~ ~12 ~"),
            f"effect give {self.target} minecraft:blindness 45 0 true",
            f"effect give {self.target} minecraft:hunger 180 4 true",
            *self.summon_many("creeper", 3, 5, "~", "{powered:1b,Fuse:80}"),
            self.stage(0.20, self.summon_many("witch", 3, 5)[0]),
            self.stage(0.38, self.summon_many("phantom", 3, 8, "~8")[0]),
            self.stage(0.56, self.summon_many("tnt", 3, 4, "~2", "{Fuse:50}")[0]),
            self.stage(0.74, self.at_target("fill ~-8 ~-1 ~-8 ~8 ~-1 ~8 minecraft:lava replace minecraft:air")),
            self.stage(0.90, self.at_target("summon minecraft:warden ~ ~ ~")),
        ]

    def wacky_shrinking_quiz_dome(self) -> CommandPlan:
        return [
            self.at_target("fill ~-12 ~-1 ~-12 ~12 ~8 ~12 minecraft:tinted_glass replace minecraft:air"),
            self.at_target("fill ~-10 ~ ~-10 ~10 ~6 ~10 minecraft:air"),
            f"effect give {self.target} minecraft:glowing 220 0 true",
            *self.summon_many("skeleton", 5, 10),
            self.stage(0.20, self.at_target("fill ~-10 ~ ~-10 ~10 ~5 ~10 minecraft:cobweb replace minecraft:air")),
            self.stage(0.36, self.at_target("fill ~-8 ~-1 ~-8 ~8 ~7 ~8 minecraft:obsidian replace minecraft:tinted_glass")),
            self.stage(0.52, self.at_target("fill ~-6 ~-1 ~-6 ~6 ~7 ~6 minecraft:tinted_glass replace minecraft:air")),
            self.stage(0.68, self.at_target("fill ~-4 ~-1 ~-4 ~4 ~7 ~4 minecraft:lava replace minecraft:air")),
            self.stage(0.84, self.at_target("summon minecraft:warden ~ ~ ~")),
            self.stage(0.97, self.at_target("fill ~-2 ~ ~-2 ~2 ~3 ~2 minecraft:powder_snow replace minecraft:air")),
        ]

    def wacky_teleport_debt_collector(self) -> CommandPlan:
        return [
            self.at_target("fill ~-9 ~-1 ~-9 ~9 ~-1 ~9 minecraft:amethyst_block"),
            f"effect give {self.target} minecraft:darkness 140 0 true",
            self.stage(0.12, self.as_target("tp @s ~18 ~3 ~18")),
            self.stage(0.18, self.at_target("summon minecraft:creeper ~ ~ ~ {powered:1b,Fuse:80}")),
            self.stage(0.32, self.as_target("tp @s ~-36 ~3 ~")),
            self.stage(0.38, self.at_target("summon minecraft:vex ~ ~2 ~")),
            self.stage(0.52, self.as_target("tp @s ~18 ~3 ~-18")),
            self.stage(0.58, self.at_target("summon minecraft:tnt ~ ~2 ~ {Fuse:45}")),
            self.stage(0.74, self.as_target("tp @s ~ ~6 ~")),
            self.stage(0.88, self.at_target("summon minecraft:warden ~ ~ ~")),
        ]

    def wacky_nether_customs_checkpoint(self) -> CommandPlan:
        return [
            self.at_target("fill ~-10 ~-1 ~-10 ~10 ~-1 ~10 minecraft:netherrack"),
            self.at_target("fill ~-10 ~ ~-10 ~10 ~4 ~10 minecraft:nether_brick_fence replace minecraft:air"),
            self.at_target("fill ~-1 ~ ~-1 ~1 ~2 ~1 minecraft:air"),
            f"effect give {self.target} minecraft:fire_resistance 20 0 true",
            *self.summon_many("hoglin", 4, 7),
            self.stage(0.22, self.at_target("fill ~-8 ~ ~-8 ~8 ~1 ~8 minecraft:lava replace minecraft:air")),
            self.stage(0.40, self.summon_many("blaze", 4, 8, "~3")[0]),
            self.stage(0.58, f"effect clear {self.target} minecraft:fire_resistance"),
            self.stage(0.70, self.as_target("tp @s ~ ~2 ~")),
            self.stage(0.86, self.at_target("summon minecraft:zoglin ~ ~ ~")),
        ]

    def wacky_sky_island_repossession(self) -> CommandPlan:
        return [
            self.as_target("tp @s ~ ~90 ~"),
            self.at_target("fill ~-5 ~-1 ~-5 ~5 ~-1 ~5 minecraft:slime_block replace minecraft:air"),
            f"effect give {self.target} minecraft:slow_falling 18 0 true",
            *self.summon_many("phantom", 5, 10, "~6"),
            self.stage(0.24, self.at_target("fill ~1 ~-1 ~-5 ~5 ~-1 ~5 minecraft:air")),
            self.stage(0.42, self.at_target("fill ~-5 ~-1 ~1 ~0 ~-1 ~5 minecraft:air")),
            self.stage(0.58, f"effect clear {self.target} minecraft:slow_falling"),
            self.stage(0.70, self.at_target("fill ~-2 ~20 ~-2 ~2 ~20 ~2 minecraft:anvil replace minecraft:air")),
            self.stage(0.86, self.at_target("summon minecraft:tnt ~ ~8 ~ {Fuse:60}")),
            self.stage(0.96, f"effect give {self.target} minecraft:slow_falling 8 0 true"),
        ]

    def wacky_raid_boss_paperwork_stack(self) -> CommandPlan:
        return [
            self.at_target("fill ~-10 ~-1 ~-10 ~10 ~-1 ~10 minecraft:dark_oak_planks"),
            self.at_target("fill ~-10 ~ ~-10 ~10 ~5 ~10 minecraft:dark_oak_fence replace minecraft:air"),
            f"effect give {self.target} minecraft:weakness 180 3 true",
            *self.summon_many("pillager", 5, 8),
            self.stage(0.20, self.at_target("summon minecraft:ravager ~ ~ ~")),
            self.stage(0.38, self.summon_many("vex", 4, 5, "~2")[0]),
            self.stage(0.56, self.at_target("summon minecraft:evoker ~ ~ ~")),
            self.stage(0.72, self.at_target("fill ~-7 ~ ~-7 ~7 ~2 ~7 minecraft:cobweb replace minecraft:air")),
            self.stage(0.90, self.at_target("summon minecraft:ravager ~ ~ ~ {CustomName:'\"Department Head\"'}")),
        ]


    def wacky2_incorrect_answers_department(self) -> CommandPlan:
        return [
            *self.wacky2_opening("DEPARTMENT OF INCORRECT ANSWERS", "Please take a number. There are 9,004 numbers."),
            *self.wacky2_temp_mobs("villager", 9, 8, "~", "{NoAI:1b,CustomName:'\"Case Worker\"'}"),
            *self.wacky2_temp_mobs("armor_stand", 6, 7, "~", "{NoGravity:1b,CustomNameVisible:1b,CustomName:'\"FORM 27-B\"'}"),
            self.stage(0.08, f"give {self.target} minecraft:paper 16"),
            self.stage(0.12, self.wacky2_sound("block.bell.use", 0.7)),
            self.stage(0.16, self.wacky2_tell("Window 3 is closed. Window 4 insists it is a chicken.", "yellow")),
            self.stage(0.20, self.wacky2_particles("composter", 160, 3.0, 0.15)),
            self.stage(0.25, f"effect give {self.target} minecraft:nausea 8 0 true"),
            self.stage(0.30, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.34, self.wacky2_sound("entity.villager.no", 0.6)),
            self.stage(0.38, f"give {self.target} minecraft:book 3"),
            self.stage(0.42, self.wacky2_tell("Your appeal has been forwarded to the Department of Appeals Appeals.", "aqua")),
            self.stage(0.47, self.as_target("tp @s ~ ~ ~ ~-90 ~")),
            self.stage(0.51, self.wacky2_particles("note", 120, 2.5, 0.1)),
            self.stage(0.56, self.wacky2_sound("entity.villager.yes", 1.8)),
            self.stage(0.61, f"experience add {self.target} 1 points"),
            self.stage(0.66, self.wacky2_tell("Congratulations: you have been promoted to Applicant.", "green")),
            self.stage(0.71, f"give {self.target} minecraft:cookie 4"),
            self.stage(0.76, self.wacky2_particles("enchant", 180, 4.0, 0.2)),
            self.stage(0.82, self.as_target("tp @s ~ ~ ~ ~180 ~")),
            self.stage(0.87, self.wacky2_sound("block.bell.use", 1.9)),
            *self.wacky2_finale("Case closed for reasons nobody can explain."),
        ]

    def wacky2_chicken_stock_exchange(self) -> CommandPlan:
        return [
            *self.wacky2_opening("CHICKEN STOCK EXCHANGE", "The market is up. The chickens are also up."),
            *self.wacky2_temp_mobs("chicken", 18, 10, "~", "{CustomName:'\"Financial Analyst\"'}"),
            *self.wacky2_temp_mobs("villager", 4, 8, "~", "{NoAI:1b,CustomName:'\"Broker\"'}"),
            self.stage(0.07, f"give {self.target} minecraft:wheat_seeds 32"),
            self.stage(0.11, self.wacky2_sound("entity.chicken.ambient", 1.9)),
            self.stage(0.15, self.wacky2_particles("crit", 180, 4.0, 0.25)),
            self.stage(0.19, self.wacky2_tell("BREAKING: EGG futures have become egg presents.", "yellow")),
            self.stage(0.24, f"effect give {self.target} minecraft:speed 12 2 true"),
            self.stage(0.29, self.as_target("tp @s ~ ~ ~ ~35 ~")),
            self.stage(0.33, self.wacky2_sound("entity.experience_orb.pickup", 1.6)),
            self.stage(0.37, f"give {self.target} minecraft:egg 8"),
            self.stage(0.42, self.wacky2_tell("Market correction: every chicken is now a consultant.", "aqua")),
            self.stage(0.47, self.wacky2_particles("cloud", 120, 3.5, 0.15)),
            self.stage(0.52, self.as_target("tp @s ~ ~ ~ ~-70 ~")),
            self.stage(0.57, f"effect give {self.target} minecraft:nausea 6 0 true"),
            self.stage(0.62, self.wacky2_sound("entity.chicken.egg", 0.7)),
            self.stage(0.67, f"give {self.target} minecraft:feather 12"),
            self.stage(0.72, self.wacky2_tell("Trading halted after a chicken attempted insider clucking.", "red")),
            self.stage(0.78, self.wacky2_particles("happy_villager", 180, 4.0, 0.2)),
            self.stage(0.84, self.wacky2_sound("block.note_block.pling", 0.5)),
            *self.wacky2_finale("The exchange has closed. The chickens deny everything."),
        ]

    def wacky2_sheep_color_singularity(self) -> CommandPlan:
        sheep = []
        colors = [1, 2, 3, 4, 5, 6, 9, 10, 11, 13, 14]
        for index, color in enumerate(colors):
            sheep.extend(self.wacky2_temp_mobs("sheep", 1, 8, "~", f"{{Color:{color}b,CustomName:'\"Chromatic Witness {index + 1}\"'}}"))
        return [
            *self.wacky2_opening("SHEEP COLOR SINGULARITY", "Physics has been replaced by a wool catalog."),
            *sheep,
            self.stage(0.08, f"give {self.target} minecraft:white_wool 8"),
            self.stage(0.12, self.wacky2_particles("note", 140, 3.0, 0.08)),
            self.stage(0.17, self.wacky2_sound("entity.sheep.ambient", 0.6)),
            self.stage(0.22, f"effect give {self.target} minecraft:glowing 30 0 true"),
            self.stage(0.27, self.as_target("tp @s ~ ~ ~ ~60 ~")),
            self.stage(0.32, self.wacky2_tell("Magenta has filed a complaint against cyan.", "light_purple")),
            self.stage(0.37, self.wacky2_particles("note", 220, 4.0, 0.12)),
            self.stage(0.42, f"give {self.target} minecraft:lime_dye 3"),
            self.stage(0.47, self.wacky2_sound("block.wool.place", 1.7)),
            self.stage(0.52, self.as_target("tp @s ~ ~ ~ ~60 ~")),
            self.stage(0.57, f"give {self.target} minecraft:magenta_dye 3"),
            self.stage(0.62, self.wacky2_tell("All colors have merged into administrative beige.", "gray")),
            self.stage(0.67, f"effect give {self.target} minecraft:night_vision 12 0 true"),
            self.stage(0.72, self.wacky2_particles("end_rod", 150, 3.0, 0.08)),
            self.stage(0.78, self.as_target("tp @s ~ ~ ~ ~60 ~")),
            self.stage(0.84, self.wacky2_sound("entity.sheep.shear", 1.4)),
            *self.wacky2_finale("Chromatic incident resolved. Beige remains under investigation."),
        ]

    def wacky2_quantum_rabbit_census(self) -> CommandPlan:
        return [
            *self.wacky2_opening("QUANTUM RABBIT CENSUS", "Every rabbit has been counted twice and also not at all."),
            *self.wacky2_temp_mobs("rabbit", 20, 11, "~", "{CustomName:'\"Maybe Rabbit\"'}"),
            *self.wacky2_temp_mobs("armor_stand", 5, 8, "~", "{NoGravity:1b,CustomNameVisible:1b,CustomName:'\"CENSUS DEVICE\"'}"),
            self.stage(0.07, f"give {self.target} minecraft:carrot 12"),
            self.stage(0.12, self.wacky2_particles("portal", 240, 4.0, 0.3)),
            self.stage(0.17, self.wacky2_sound("entity.rabbit.jump", 1.9)),
            self.stage(0.22, self.wacky2_tell("Rabbit count: 14. Rabbit confidence interval: yes.", "aqua")),
            self.stage(0.27, f"effect give {self.target} minecraft:jump_boost 10 2 true"),
            self.stage(0.32, self.as_target("tp @s ~ ~ ~ ~90 ~")),
            self.stage(0.37, self.wacky2_particles("reverse_portal", 180, 3.5, 0.2)),
            self.stage(0.42, self.wacky2_tell("Recount complete: the rabbits have counted YOU.", "yellow")),
            self.stage(0.47, f"give {self.target} minecraft:rabbit_hide 2"),
            self.stage(0.52, self.wacky2_sound("block.note_block.hat", 1.8)),
            self.stage(0.57, f"effect give {self.target} minecraft:nausea 5 0 true"),
            self.stage(0.62, self.as_target("tp @s ~ ~ ~ ~-135 ~")),
            self.stage(0.67, self.wacky2_particles("enchant", 220, 4.0, 0.25)),
            self.stage(0.72, self.wacky2_tell("One rabbit exists only for tax purposes.", "light_purple")),
            self.stage(0.78, f"experience add {self.target} 2 points"),
            self.stage(0.84, self.wacky2_sound("entity.rabbit.ambient", 0.5)),
            *self.wacky2_finale("Census archived in a dimension made entirely of carrots."),
        ]

    def wacky2_parrot_disco_emergency(self) -> CommandPlan:
        return [
            *self.wacky2_opening("PARROT DISCO EMERGENCY", "The dance floor has achieved sentience."),
            *self.wacky2_temp_mobs("parrot", 14, 9, "~1", "{CustomName:'\"DJ Squawk\"'}"),
            *self.wacky2_temp_mobs("armor_stand", 6, 8, "~", "{NoGravity:1b,CustomNameVisible:1b,CustomName:'\"DISCO INSPECTOR\"'}"),
            self.stage(0.06, self.wacky2_particles("note", 260, 4.5, 0.15)),
            self.stage(0.11, self.wacky2_sound("block.note_block.bass", 0.7)),
            self.stage(0.16, f"effect give {self.target} minecraft:speed 16 1 true"),
            self.stage(0.21, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.26, self.wacky2_sound("block.note_block.pling", 1.9)),
            self.stage(0.31, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.36, self.wacky2_particles("end_rod", 180, 4.0, 0.15)),
            self.stage(0.41, f"give {self.target} minecraft:cookie 6"),
            self.stage(0.46, self.wacky2_tell("Emergency update: dancing is now mandatory but unenforceable.", "light_purple")),
            self.stage(0.51, self.as_target("tp @s ~ ~ ~ ~90 ~")),
            self.stage(0.56, f"effect give {self.target} minecraft:nausea 5 0 true"),
            self.stage(0.61, self.wacky2_sound("entity.parrot.ambient", 1.8)),
            self.stage(0.66, self.wacky2_particles("firework", 220, 5.0, 0.18)),
            self.stage(0.72, self.as_target("tp @s ~ ~ ~ ~180 ~")),
            self.stage(0.78, self.wacky2_tell("The DJ has been replaced by three increasingly nervous parrots.", "yellow")),
            self.stage(0.84, self.wacky2_sound("block.note_block.chime", 1.5)),
            *self.wacky2_finale("Disco emergency downgraded to disco inconvenience."),
        ]

    def wacky2_cow_bell_orchestra(self) -> CommandPlan:
        return [
            *self.wacky2_opening("COW BELL ORCHESTRA AUDIT", "The symphony has one instrument and 14 opinions."),
            *self.wacky2_temp_mobs("cow", 14, 10, "~", "{CustomName:'\"Second Trombone\"'}"),
            *self.wacky2_temp_mobs("villager", 4, 7, "~", "{NoAI:1b,CustomName:'\"Music Critic\"'}"),
            self.stage(0.07, self.wacky2_sound("block.bell.use", 0.5)),
            self.stage(0.11, self.wacky2_sound("entity.cow.ambient", 1.8)),
            self.stage(0.15, self.wacky2_particles("note", 180, 4.0, 0.1)),
            self.stage(0.20, f"give {self.target} minecraft:wheat 8"),
            self.stage(0.25, self.wacky2_tell("Movement I: Allegro Moo Non Troppo.", "aqua")),
            self.stage(0.30, self.as_target("tp @s ~ ~ ~ ~30 ~")),
            self.stage(0.35, self.wacky2_sound("block.note_block.bass", 0.6)),
            self.stage(0.40, self.wacky2_particles("composter", 150, 3.0, 0.12)),
            self.stage(0.45, f"give {self.target} minecraft:bucket 1"),
            self.stage(0.50, self.wacky2_sound("block.bell.use", 1.9)),
            self.stage(0.55, self.as_target("tp @s ~ ~ ~ ~-75 ~")),
            self.stage(0.60, self.wacky2_tell("The conductor has resigned after being outvoted by a cow.", "yellow")),
            self.stage(0.65, f"effect give {self.target} minecraft:haste 12 2 true"),
            self.stage(0.70, self.wacky2_particles("happy_villager", 220, 4.0, 0.15)),
            self.stage(0.76, self.wacky2_sound("entity.cow.ambient", 0.5)),
            self.stage(0.82, self.as_target("tp @s ~ ~ ~ ~120 ~")),
            *self.wacky2_finale("Orchestra audit passed because nobody could find the rubric."),
        ]

    def wacky2_frog_opera(self) -> CommandPlan:
        return [
            *self.wacky2_opening("FROG OPERA LICENSING DISPUTE", "Act I begins in the key of ribbit minor."),
            *self.wacky2_temp_mobs("frog", 16, 9, "~", "{CustomName:'\"Tenor\"'}"),
            *self.wacky2_temp_mobs("villager", 3, 7, "~", "{NoAI:1b,CustomName:'\"Opera Reviewer\"'}"),
            self.stage(0.07, f"give {self.target} minecraft:slime_ball 8"),
            self.stage(0.12, self.wacky2_particles("note", 220, 4.0, 0.14)),
            self.stage(0.17, self.wacky2_sound("entity.frog.ambient", 0.7)),
            self.stage(0.22, self.wacky2_tell("Act II has been canceled because the pond union walked out.", "aqua")),
            self.stage(0.27, f"effect give {self.target} minecraft:jump_boost 12 1 true"),
            self.stage(0.32, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.37, self.wacky2_particles("splash", 170, 3.5, 0.2)),
            self.stage(0.42, self.wacky2_sound("block.note_block.flute", 1.6)),
            self.stage(0.47, f"give {self.target} minecraft:lily_pad 4"),
            self.stage(0.52, self.wacky2_tell("Intermission: please do not feed the soprano.", "yellow")),
            self.stage(0.57, self.as_target("tp @s ~ ~ ~ ~-90 ~")),
            self.stage(0.62, self.wacky2_particles("bubble", 180, 3.0, 0.15)),
            self.stage(0.67, self.wacky2_sound("entity.frog.ambient", 1.9)),
            self.stage(0.72, f"experience add {self.target} 3 points"),
            self.stage(0.78, self.wacky2_tell("Standing ovation detected. Source: frogs standing normally.", "green")),
            self.stage(0.84, self.wacky2_sound("block.note_block.pling", 0.8)),
            *self.wacky2_finale("Opera concluded with 11 curtain calls and no curtains."),
        ]

    def wacky2_cat_tribunal(self) -> CommandPlan:
        return [
            *self.wacky2_opening("CAT TRIBUNAL APPEALS COURT", "You may approach the scratching post."),
            *self.wacky2_temp_mobs("cat", 15, 9, "~", "{CustomName:'\"Associate Justice\"'}"),
            *self.wacky2_temp_mobs("armor_stand", 5, 7, "~", "{NoGravity:1b,CustomNameVisible:1b,CustomName:'\"EXHIBIT A: STRING\"'}"),
            self.stage(0.07, f"give {self.target} minecraft:cod 8"),
            self.stage(0.12, self.wacky2_sound("entity.cat.ambient", 1.7)),
            self.stage(0.17, self.wacky2_particles("happy_villager", 170, 3.0, 0.15)),
            self.stage(0.22, self.wacky2_tell("The court finds you guilty of insufficient cardboard boxes.", "yellow")),
            self.stage(0.27, self.as_target("tp @s ~ ~ ~ ~30 ~")),
            self.stage(0.32, f"give {self.target} minecraft:string 12"),
            self.stage(0.37, self.wacky2_sound("entity.cat.purr", 0.8)),
            self.stage(0.42, f"effect give {self.target} minecraft:night_vision 12 0 true"),
            self.stage(0.47, self.wacky2_tell("Appeal accepted. Appeal immediately rejected by a different cat.", "aqua")),
            self.stage(0.52, self.as_target("tp @s ~ ~ ~ ~-65 ~")),
            self.stage(0.57, self.wacky2_particles("note", 180, 3.5, 0.12)),
            self.stage(0.62, self.wacky2_sound("entity.cat.hiss", 0.6)),
            self.stage(0.67, f"give {self.target} minecraft:paper 5"),
            self.stage(0.72, self.wacky2_tell("Final ruling: sit somewhere inconvenient.", "light_purple")),
            self.stage(0.78, self.wacky2_particles("enchant", 180, 3.5, 0.2)),
            self.stage(0.84, self.wacky2_sound("entity.cat.purr", 1.8)),
            *self.wacky2_finale("Court adjourned for a 19-hour nap."),
        ]

    def wacky2_villager_customer_support(self) -> CommandPlan:
        return [
            *self.wacky2_opening("VILLAGER CUSTOMER SUPPORT", "Your estimated hold time is approximately hrmmmm."),
            *self.wacky2_temp_mobs("villager", 18, 11, "~", "{NoAI:1b,CustomName:'\"Tier 1 Support\"'}"),
            self.stage(0.06, self.wacky2_sound("entity.villager.ambient", 0.6)),
            self.stage(0.10, f"give {self.target} minecraft:paper 12"),
            self.stage(0.14, self.wacky2_tell("Press 1 for trading. Press 2 for more humming.", "yellow")),
            self.stage(0.18, self.wacky2_particles("composter", 200, 4.0, 0.15)),
            self.stage(0.22, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.27, self.wacky2_sound("entity.villager.no", 1.7)),
            self.stage(0.32, self.wacky2_tell("Your issue has been escalated to Tier 1.1 Support.", "aqua")),
            self.stage(0.37, f"give {self.target} minecraft:emerald 1"),
            self.stage(0.42, self.wacky2_particles("happy_villager", 260, 4.0, 0.2)),
            self.stage(0.47, self.wacky2_sound("entity.villager.yes", 0.5)),
            self.stage(0.52, self.as_target("tp @s ~ ~ ~ ~90 ~")),
            self.stage(0.57, f"effect give {self.target} minecraft:nausea 6 0 true"),
            self.stage(0.62, self.wacky2_tell("Technician note: user appears to be made of blocks.", "gray")),
            self.stage(0.67, f"give {self.target} minecraft:book 2"),
            self.stage(0.72, self.wacky2_sound("block.bell.use", 1.8)),
            self.stage(0.78, self.wacky2_particles("note", 180, 3.0, 0.1)),
            self.stage(0.84, self.wacky2_tell("Ticket marked RESOLVED despite absolutely nothing changing.", "green")),
            *self.wacky2_finale("Support session ended. Please rate your villager from hrm to hrrrm."),
        ]

    def wacky2_weather_forecast(self) -> CommandPlan:
        return [
            *self.wacky2_opening("POSSESSED WEATHER FORECAST", "Chance of weather: disturbingly high."),
            *self.wacky2_temp_mobs("bat", 12, 10, "~3", "{CustomName:'\"Meteorologist\"'}"),
            self.stage(0.06, "weather clear 20"),
            self.stage(0.11, self.wacky2_particles("cloud", 220, 5.0, 0.18)),
            self.stage(0.16, self.wacky2_tell("Forecast: clear skies, except for the indoor clouds.", "aqua")),
            self.stage(0.21, "time set noon"),
            self.stage(0.26, self.wacky2_sound("ambient.weather.rain", 0.8)),
            self.stage(0.31, "weather rain 20"),
            self.stage(0.36, f"effect give {self.target} minecraft:night_vision 15 0 true"),
            self.stage(0.41, "time set midnight"),
            self.stage(0.46, self.wacky2_particles("end_rod", 180, 4.0, 0.15)),
            self.stage(0.51, self.wacky2_tell("Local moon has been rescheduled to immediately.", "light_purple")),
            self.stage(0.56, "weather thunder 12"),
            self.stage(0.61, self.wacky2_sound("entity.lightning_bolt.thunder", 0.5)),
            self.stage(0.66, self.as_target("tp @s ~ ~ ~ ~120 ~")),
            self.stage(0.71, self.wacky2_particles("splash", 220, 5.0, 0.2)),
            self.stage(0.76, self.wacky2_tell("Forecast revised: partly confused with scattered bureaucracy.", "yellow")),
            self.stage(0.82, "weather clear 600"),
            self.stage(0.86, "time set day"),
            *self.wacky2_finale("Weather department denies that any of this was weather."),
        ]

    def wacky2_inventory_misfile(self) -> CommandPlan:
        return [
            *self.wacky2_opening("INVENTORY MISFILING CATASTROPHE", "Several objects have been assigned the wrong careers."),
            self.stage(0.06, f"give {self.target} minecraft:stick 7"),
            self.stage(0.10, f"give {self.target} minecraft:bowl 5"),
            self.stage(0.14, f"give {self.target} minecraft:feather 9"),
            self.stage(0.18, f"give {self.target} minecraft:paper 13"),
            self.stage(0.22, f"give {self.target} minecraft:cookie 3"),
            self.stage(0.26, self.wacky2_sound("entity.item.pickup", 1.8)),
            self.stage(0.30, self.wacky2_tell("Inventory audit: the bowl is now middle management.", "yellow")),
            self.stage(0.34, f"give {self.target} minecraft:wooden_button 11"),
            self.stage(0.38, f"give {self.target} minecraft:torch 4"),
            self.stage(0.42, self.wacky2_particles("item minecraft:snowball", 140, 3.0, 0.12)),
            self.stage(0.46, f"effect give {self.target} minecraft:nausea 7 0 true"),
            self.stage(0.50, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.54, f"give {self.target} minecraft:kelp 6"),
            self.stage(0.58, f"give {self.target} minecraft:brick 2"),
            self.stage(0.62, self.wacky2_tell("A stick has requested annual leave.", "aqua")),
            self.stage(0.66, self.wacky2_sound("block.note_block.pling", 0.6)),
            self.stage(0.70, f"give {self.target} minecraft:flower_pot 1"),
            self.stage(0.74, f"give {self.target} minecraft:name_tag 1"),
            self.stage(0.78, self.wacky2_particles("happy_villager", 180, 3.5, 0.2)),
            self.stage(0.84, self.wacky2_tell("Audit complete: everything is technically somewhere.", "green")),
            *self.wacky2_finale("Inventory catastrophe downgraded to inventory paperwork."),
        ]

    def wacky2_fake_boss_fight(self) -> CommandPlan:
        return [
            *self.wacky2_opening("BOSS FIGHT: ???", "Threat level: theatrically enormous, practically zero."),
            *self.wacky2_temp_mobs("armor_stand", 10, 9, "~", "{NoGravity:1b,CustomNameVisible:1b,CustomName:'\"Definitely The Final Boss\"'}"),
            *self.wacky2_temp_mobs("chicken", 8, 7, "~", "{CustomName:'\"Boss Phase\"'}"),
            self.stage(0.06, self.wacky2_sound("entity.ender_dragon.growl", 0.5, 0.7)),
            self.stage(0.11, self.wacky2_particles("dragon_breath", 220, 5.0, 0.1)),
            self.stage(0.16, self.wacky2_tell("BOSS PHASE 1: intimidating typography.", "red")),
            self.stage(0.21, self.as_target("tp @s ~ ~ ~ ~60 ~")),
            self.stage(0.26, f"effect give {self.target} minecraft:speed 8 1 true"),
            self.stage(0.31, self.wacky2_sound("entity.wither.spawn", 1.8, 0.5)),
            self.stage(0.36, self.wacky2_tell("BOSS PHASE 2: the boss has misplaced itself.", "yellow")),
            self.stage(0.41, self.wacky2_particles("explosion", 25, 4.0, 0.0)),
            self.stage(0.46, f"give {self.target} minecraft:wooden_sword 1"),
            self.stage(0.51, self.as_target("tp @s ~ ~ ~ ~-120 ~")),
            self.stage(0.56, self.wacky2_sound("block.anvil.land", 0.6)),
            self.stage(0.61, self.wacky2_tell("BOSS PHASE 3: mandatory cutscene with no cutscene.", "light_purple")),
            self.stage(0.66, f"effect give {self.target} minecraft:jump_boost 8 2 true"),
            self.stage(0.71, self.wacky2_particles("totem_of_undying", 260, 5.0, 0.25)),
            self.stage(0.76, self.wacky2_sound("ui.toast.challenge_complete", 1.2)),
            self.stage(0.82, self.wacky2_tell("YOU DEFEATED NOTHING. Nothing drops 3 XP.", "green")),
            self.stage(0.86, f"experience add {self.target} 3 points"),
            *self.wacky2_finale("Fake boss defeated. The real boss was formatting all along."),
        ]

    def wacky2_moon_gravity_onboarding(self) -> CommandPlan:
        return [
            *self.wacky2_opening("MOON-GRAVITY ONBOARDING", "Please sign the waiver while gently refusing gravity."),
            *self.wacky2_temp_mobs("bat", 14, 10, "~4", "{CustomName:'\"Gravity Technician\"'}"),
            self.stage(0.07, f"effect give {self.target} minecraft:jump_boost 24 4 true"),
            self.stage(0.12, f"effect give {self.target} minecraft:slow_falling 30 0 true"),
            self.stage(0.17, f"effect give {self.target} minecraft:levitation 2 1 true"),
            self.stage(0.22, self.wacky2_particles("cloud", 180, 4.0, 0.12)),
            self.stage(0.27, self.wacky2_sound("entity.bat.takeoff", 1.8)),
            self.stage(0.32, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.37, self.wacky2_tell("Orientation module 2: up is now a suggestion.", "aqua")),
            self.stage(0.42, f"effect give {self.target} minecraft:levitation 1 2 true"),
            self.stage(0.47, self.wacky2_particles("end_rod", 220, 4.5, 0.12)),
            self.stage(0.52, self.as_target("tp @s ~ ~ ~ ~90 ~")),
            self.stage(0.57, self.wacky2_sound("block.note_block.chime", 0.7)),
            self.stage(0.62, self.wacky2_tell("Gravity technician says this is within tolerance.", "yellow")),
            self.stage(0.67, f"give {self.target} minecraft:feather 12"),
            self.stage(0.72, f"effect give {self.target} minecraft:levitation 2 0 true"),
            self.stage(0.78, self.wacky2_particles("portal", 200, 4.0, 0.25)),
            self.stage(0.84, self.as_target("tp @s ~ ~ ~ ~180 ~")),
            *self.wacky2_finale("Gravity restored pending another paperwork error."),
        ]

    def wacky2_museum_exhibit(self) -> CommandPlan:
        return [
            *self.wacky2_opening("MUSEUM EXHIBIT: YOU", "Please do not tap the glass. There is no glass."),
            *self.wacky2_temp_mobs("armor_stand", 14, 10, "~", "{NoGravity:1b,CustomNameVisible:1b,CustomName:'\"Museum Guest\"'}"),
            *self.wacky2_temp_mobs("villager", 5, 8, "~", "{NoAI:1b,CustomName:'\"Curator\"'}"),
            self.stage(0.06, self.wacky2_particles("enchant", 180, 4.0, 0.18)),
            self.stage(0.11, self.wacky2_sound("block.amethyst_block.chime", 1.5)),
            self.stage(0.16, self.wacky2_tell("Plaque: 'Player, confused period, mixed media.'", "yellow")),
            self.stage(0.21, f"effect give {self.target} minecraft:glowing 24 0 true"),
            self.stage(0.26, self.as_target("tp @s ~ ~ ~ ~30 ~")),
            self.stage(0.31, self.wacky2_particles("happy_villager", 160, 3.5, 0.15)),
            self.stage(0.36, self.wacky2_tell("A critic called the exhibit 'surprisingly interactive.'", "aqua")),
            self.stage(0.41, self.as_target("tp @s ~ ~ ~ ~30 ~")),
            self.stage(0.46, self.wacky2_sound("entity.villager.yes", 1.8)),
            self.stage(0.51, f"give {self.target} minecraft:painting 1"),
            self.stage(0.56, self.wacky2_particles("note", 200, 3.5, 0.12)),
            self.stage(0.61, self.as_target("tp @s ~ ~ ~ ~120 ~")),
            self.stage(0.66, self.wacky2_tell("Gift shop now sells tiny replicas of your wrong answer.", "light_purple")),
            self.stage(0.71, f"give {self.target} minecraft:paper 4"),
            self.stage(0.76, self.wacky2_sound("ui.toast.in", 1.4)),
            self.stage(0.82, self.wacky2_particles("totem_of_undying", 170, 4.0, 0.2)),
            *self.wacky2_finale("Museum closed after the exhibit attempted to leave."),
        ]

    def wacky2_minecart_parking(self) -> CommandPlan:
        return [
            *self.wacky2_opening("MINECART PARKING ENFORCEMENT", "Your vehicle has been ticketed despite not existing."),
            *self.wacky2_temp_mobs("minecart", 16, 10, "~", "{CustomName:'\"Illegally Parked\"'}"),
            *self.wacky2_temp_mobs("villager", 5, 8, "~", "{NoAI:1b,CustomName:'\"Parking Officer\"'}"),
            self.stage(0.07, f"give {self.target} minecraft:paper 9"),
            self.stage(0.12, self.wacky2_sound("entity.minecart.riding", 1.8)),
            self.stage(0.17, self.wacky2_particles("smoke", 160, 4.0, 0.12)),
            self.stage(0.22, self.wacky2_tell("Citation: parking outside a parking dimension.", "yellow")),
            self.stage(0.27, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.32, self.wacky2_sound("block.bell.use", 0.8)),
            self.stage(0.37, f"give {self.target} minecraft:rail 8"),
            self.stage(0.42, self.wacky2_tell("Appeal denied: the minecart has already testified.", "aqua")),
            self.stage(0.47, self.wacky2_particles("crit", 180, 4.0, 0.15)),
            self.stage(0.52, self.as_target("tp @s ~ ~ ~ ~-90 ~")),
            self.stage(0.57, f"effect give {self.target} minecraft:speed 8 1 true"),
            self.stage(0.62, self.wacky2_sound("entity.minecart.inside", 1.5)),
            self.stage(0.67, f"give {self.target} minecraft:iron_nugget 5"),
            self.stage(0.72, self.wacky2_tell("Tow truck unavailable because Minecraft has no tow truck.", "gray")),
            self.stage(0.78, self.wacky2_particles("happy_villager", 180, 4.0, 0.15)),
            self.stage(0.84, self.wacky2_sound("entity.villager.no", 0.6)),
            *self.wacky2_finale("All tickets voided due to catastrophic absence of roads."),
        ]

    def wacky2_dry_boat_dealership(self) -> CommandPlan:
        return [
            *self.wacky2_opening("BOAT DEALERSHIP ON DRY LAND", "Zero water. Maximum financing options."),
            *self.wacky2_temp_mobs("boat", 12, 10, "~", "{CustomName:'\"Certified Pre-Owned\"'}"),
            *self.wacky2_temp_mobs("villager", 5, 8, "~", "{NoAI:1b,CustomName:'\"Sales Associate\"'}"),
            self.stage(0.07, self.wacky2_sound("entity.boat.paddle_land", 1.6)),
            self.stage(0.12, f"give {self.target} minecraft:oak_planks 6"),
            self.stage(0.17, self.wacky2_tell("This model gets 0 miles per gallon and 0 miles per anything.", "yellow")),
            self.stage(0.22, self.wacky2_particles("splash", 160, 4.0, 0.18)),
            self.stage(0.27, self.as_target("tp @s ~ ~ ~ ~60 ~")),
            self.stage(0.32, self.wacky2_sound("entity.villager.yes", 1.8)),
            self.stage(0.37, f"give {self.target} minecraft:map 1"),
            self.stage(0.42, self.wacky2_tell("Salesperson added the premium 'imaginary ocean' package.", "aqua")),
            self.stage(0.47, self.wacky2_particles("bubble", 180, 3.5, 0.15)),
            self.stage(0.52, self.as_target("tp @s ~ ~ ~ ~-120 ~")),
            self.stage(0.57, f"effect give {self.target} minecraft:water_breathing 12 0 true"),
            self.stage(0.62, self.wacky2_sound("entity.boat.paddle_water", 0.7)),
            self.stage(0.67, f"give {self.target} minecraft:kelp 4"),
            self.stage(0.72, self.wacky2_tell("Test drive complete without the boat moving at all.", "green")),
            self.stage(0.78, self.wacky2_particles("happy_villager", 200, 4.0, 0.15)),
            self.stage(0.84, self.wacky2_sound("block.note_block.pling", 1.9)),
            *self.wacky2_finale("Dealership repossessed by the concept of water."),
        ]

    def wacky2_honey_inspection(self) -> CommandPlan:
        return [
            *self.wacky2_opening("BEE-FREE HONEY INSPECTION", "The bees are present but legally off duty."),
            *self.wacky2_temp_mobs("bee", 16, 9, "~1", "{AngerTime:0,CustomName:'\"Union Inspector\"'}"),
            *self.wacky2_temp_mobs("armor_stand", 5, 7, "~", "{NoGravity:1b,CustomNameVisible:1b,CustomName:'\"HONEY QUALITY CONTROL\"'}"),
            self.stage(0.07, f"give {self.target} minecraft:honey_bottle 3"),
            self.stage(0.12, self.wacky2_particles("falling_honey", 180, 4.0, 0.15)),
            self.stage(0.17, self.wacky2_sound("entity.bee.loop", 0.6)),
            self.stage(0.22, self.wacky2_tell("Inspection result: sticky in all measurable dimensions.", "yellow")),
            self.stage(0.27, self.as_target("tp @s ~ ~ ~ ~30 ~")),
            self.stage(0.32, f"give {self.target} minecraft:honeycomb 6"),
            self.stage(0.37, self.wacky2_particles("landing_honey", 160, 3.0, 0.12)),
            self.stage(0.42, self.wacky2_sound("block.honey_block.slide", 1.8)),
            self.stage(0.47, self.wacky2_tell("Bee union requires a 15-minute pollen break.", "aqua")),
            self.stage(0.52, self.as_target("tp @s ~ ~ ~ ~-75 ~")),
            self.stage(0.57, f"effect give {self.target} minecraft:speed 7 1 true"),
            self.stage(0.62, self.wacky2_particles("wax_on", 180, 3.5, 0.15)),
            self.stage(0.67, self.wacky2_sound("entity.bee.pollinate", 1.7)),
            self.stage(0.72, f"give {self.target} minecraft:glass_bottle 2"),
            self.stage(0.78, self.wacky2_tell("Final sample classified as aggressively honey-shaped.", "green")),
            self.stage(0.84, self.wacky2_particles("happy_villager", 180, 4.0, 0.15)),
            *self.wacky2_finale("Honey inspection complete. No bees were promoted."),
        ]

    def wacky2_snowman_retreat(self) -> CommandPlan:
        return [
            *self.wacky2_opening("SNOWMAN CORPORATE RETREAT", "Team-building exercise: remain vaguely frozen."),
            *self.wacky2_temp_mobs("snow_golem", 12, 9, "~", "{CustomName:'\"Synergy Coach\"'}"),
            *self.wacky2_temp_mobs("armor_stand", 5, 7, "~", "{NoGravity:1b,CustomNameVisible:1b,CustomName:'\"BREAKOUT GROUP\"'}"),
            self.stage(0.07, f"give {self.target} minecraft:snowball 16"),
            self.stage(0.12, self.wacky2_particles("snowflake", 240, 4.5, 0.18)),
            self.stage(0.17, self.wacky2_sound("block.snow.place", 0.7)),
            self.stage(0.22, self.wacky2_tell("Icebreaker question: are you literally an icebreaker?", "aqua")),
            self.stage(0.27, f"effect give {self.target} minecraft:speed 8 1 true"),
            self.stage(0.32, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.37, f"give {self.target} minecraft:pumpkin 1"),
            self.stage(0.42, self.wacky2_particles("snowflake", 180, 4.0, 0.15)),
            self.stage(0.47, self.wacky2_tell("Breakout group C has melted conceptually.", "yellow")),
            self.stage(0.52, self.wacky2_sound("entity.snow_golem.shoot", 1.8)),
            self.stage(0.57, self.as_target("tp @s ~ ~ ~ ~-90 ~")),
            self.stage(0.62, f"effect give {self.target} minecraft:night_vision 8 0 true"),
            self.stage(0.67, self.wacky2_particles("cloud", 160, 3.5, 0.12)),
            self.stage(0.72, f"give {self.target} minecraft:blue_ice 1"),
            self.stage(0.78, self.wacky2_tell("Retreat goal achieved: everyone is colder and no wiser.", "green")),
            self.stage(0.84, self.wacky2_sound("block.note_block.chime", 1.5)),
            *self.wacky2_finale("Corporate retreat ended after synergy reached freezing point."),
        ]

    def wacky2_horse_committee(self) -> CommandPlan:
        return [
            *self.wacky2_opening("HORSE COMMITTEE CAROUSEL", "The committee has 12 members and zero minutes."),
            *self.wacky2_temp_mobs("horse", 12, 11, "~", "{Tame:1b,CustomName:'\"Committee Member\"'}"),
            *self.wacky2_temp_mobs("villager", 4, 8, "~", "{NoAI:1b,CustomName:'\"Secretary\"'}"),
            self.stage(0.07, f"give {self.target} minecraft:apple 6"),
            self.stage(0.12, self.wacky2_sound("entity.horse.ambient", 0.6)),
            self.stage(0.17, self.wacky2_particles("happy_villager", 180, 4.0, 0.15)),
            self.stage(0.22, self.wacky2_tell("Motion to neigh has passed unanimously.", "yellow")),
            self.stage(0.27, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.32, f"give {self.target} minecraft:hay_block 2"),
            self.stage(0.37, self.wacky2_sound("entity.horse.gallop", 1.8)),
            self.stage(0.42, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.47, self.wacky2_tell("Agenda item 7: why is the table not a horse?", "aqua")),
            self.stage(0.52, f"effect give {self.target} minecraft:speed 8 2 true"),
            self.stage(0.57, self.wacky2_particles("crit", 180, 4.0, 0.15)),
            self.stage(0.62, self.wacky2_sound("block.bell.use", 1.6)),
            self.stage(0.67, self.as_target("tp @s ~ ~ ~ ~90 ~")),
            self.stage(0.72, f"give {self.target} minecraft:paper 5"),
            self.stage(0.78, self.wacky2_tell("Meeting minutes lost after being eaten by an attendee.", "gray")),
            self.stage(0.84, self.wacky2_sound("entity.horse.ambient", 1.7)),
            *self.wacky2_finale("Committee dissolved into several unrelated horses."),
        ]

    def wacky2_llama_telemarketing(self) -> CommandPlan:
        return [
            *self.wacky2_opening("LLAMA TELEMARKETING CONVENTION", "We have been trying to reach you about your extended hay warranty."),
            *self.wacky2_temp_mobs("llama", 14, 10, "~", "{Tame:1b,CustomName:'\"Sales Representative\"'}"),
            *self.wacky2_temp_mobs("wandering_trader", 4, 8, "~", "{NoAI:1b,CustomName:'\"Regional Manager\"'}"),
            self.stage(0.07, self.wacky2_sound("entity.llama.ambient", 1.7)),
            self.stage(0.12, f"give {self.target} minecraft:wheat 8"),
            self.stage(0.17, self.wacky2_tell("Offer expires in 7 seconds and also last Tuesday.", "yellow")),
            self.stage(0.22, self.wacky2_particles("happy_villager", 200, 4.0, 0.15)),
            self.stage(0.27, self.as_target("tp @s ~ ~ ~ ~60 ~")),
            self.stage(0.32, self.wacky2_sound("entity.wandering_trader.ambient", 0.6)),
            self.stage(0.37, f"give {self.target} minecraft:paper 7"),
            self.stage(0.42, self.wacky2_tell("Please hold while your call is transferred to another llama.", "aqua")),
            self.stage(0.47, self.as_target("tp @s ~ ~ ~ ~-120 ~")),
            self.stage(0.52, f"effect give {self.target} minecraft:nausea 5 0 true"),
            self.stage(0.57, self.wacky2_particles("note", 180, 3.5, 0.1)),
            self.stage(0.62, self.wacky2_sound("entity.llama.ambient", 0.5)),
            self.stage(0.67, f"give {self.target} minecraft:white_carpet 2"),
            self.stage(0.72, self.wacky2_tell("Congratulations, you declined successfully. Sales call continues anyway.", "green")),
            self.stage(0.78, self.wacky2_particles("enchant", 180, 4.0, 0.18)),
            self.stage(0.84, self.wacky2_sound("block.note_block.pling", 1.8)),
            *self.wacky2_finale("Telemarketing convention disconnected by a mysterious clicking noise."),
        ]

    def wacky2_pig_executive_summit(self) -> CommandPlan:
        return [
            *self.wacky2_opening("PIG EXECUTIVE STRATEGY SUMMIT", "Quarterly objective: locate more carrots."),
            *self.wacky2_temp_mobs("pig", 16, 10, "~", "{CustomName:'\"Senior Vice Pig\"'}"),
            *self.wacky2_temp_mobs("villager", 4, 8, "~", "{NoAI:1b,CustomName:'\"Consultant\"'}"),
            self.stage(0.07, f"give {self.target} minecraft:carrot 10"),
            self.stage(0.12, self.wacky2_sound("entity.pig.ambient", 0.7)),
            self.stage(0.17, self.wacky2_particles("composter", 180, 4.0, 0.15)),
            self.stage(0.22, self.wacky2_tell("Q3 revenue is measured exclusively in carrots now.", "yellow")),
            self.stage(0.27, f"give {self.target} minecraft:saddle 1"),
            self.stage(0.32, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.37, self.wacky2_sound("block.bell.use", 1.8)),
            self.stage(0.42, self.wacky2_tell("Board approves strategic mud expansion.", "aqua")),
            self.stage(0.47, f"effect give {self.target} minecraft:speed 8 1 true"),
            self.stage(0.52, self.wacky2_particles("happy_villager", 200, 4.0, 0.15)),
            self.stage(0.57, self.as_target("tp @s ~ ~ ~ ~-90 ~")),
            self.stage(0.62, f"give {self.target} minecraft:potato 5"),
            self.stage(0.67, self.wacky2_sound("entity.pig.ambient", 1.9)),
            self.stage(0.72, self.wacky2_tell("Consultants recommend becoming 14% more pig-shaped.", "light_purple")),
            self.stage(0.78, f"experience add {self.target} 2 points"),
            self.stage(0.84, self.wacky2_particles("note", 180, 3.5, 0.12)),
            *self.wacky2_finale("Strategy summit adjourned to a more synergistic mud puddle."),
        ]

    def wacky2_bat_radar_outage(self) -> CommandPlan:
        return [
            *self.wacky2_opening("BAT RADAR OUTAGE DRILL", "Echolocation has been outsourced to subtitles."),
            *self.wacky2_temp_mobs("bat", 24, 12, "~3", "{CustomName:'\"Radar Technician\"'}"),
            self.stage(0.06, f"effect give {self.target} minecraft:darkness 5 0 true"),
            self.stage(0.11, self.wacky2_sound("entity.bat.ambient", 0.6)),
            self.stage(0.16, self.wacky2_particles("sonic_boom", 18, 4.0, 0.0)),
            self.stage(0.21, self.wacky2_tell("PING. PING. That was text, not radar.", "aqua")),
            self.stage(0.26, f"effect give {self.target} minecraft:night_vision 10 0 true"),
            self.stage(0.31, self.as_target("tp @s ~ ~ ~ ~90 ~")),
            self.stage(0.36, self.wacky2_sound("entity.bat.takeoff", 1.8)),
            self.stage(0.41, self.wacky2_particles("end_rod", 180, 4.0, 0.15)),
            self.stage(0.46, f"effect give {self.target} minecraft:darkness 4 0 true"),
            self.stage(0.51, self.wacky2_tell("Radar contact acquired: object identified as probably you.", "yellow")),
            self.stage(0.56, self.as_target("tp @s ~ ~ ~ ~-135 ~")),
            self.stage(0.61, self.wacky2_sound("block.note_block.hat", 1.9)),
            self.stage(0.66, f"give {self.target} minecraft:torch 4"),
            self.stage(0.71, self.wacky2_particles("portal", 200, 4.0, 0.25)),
            self.stage(0.76, self.wacky2_tell("Backup echolocation restored by yelling at the ceiling.", "green")),
            self.stage(0.82, self.wacky2_sound("entity.bat.ambient", 1.7)),
            self.stage(0.86, self.as_target("tp @s ~ ~ ~ ~180 ~")),
            *self.wacky2_finale("Radar outage resolved. Bats remain deeply unhelpful."),
        ]

    def wacky2_armor_stand_press_conference(self) -> CommandPlan:
        return [
            *self.wacky2_opening("ARMOR-STAND PRESS CONFERENCE", "No questions will be answered because nobody here can talk."),
            *self.wacky2_temp_mobs("armor_stand", 20, 12, "~", "{NoGravity:1b,CustomNameVisible:1b,CustomName:'\"Journalist\"'}"),
            *self.wacky2_temp_mobs("villager", 3, 8, "~", "{NoAI:1b,CustomName:'\"Press Secretary\"'}"),
            self.stage(0.06, f"give {self.target} minecraft:paper 10"),
            self.stage(0.11, self.wacky2_sound("block.note_block.hat", 1.7)),
            self.stage(0.16, self.wacky2_particles("flash", 12, 4.0, 0.0)),
            self.stage(0.21, self.wacky2_tell("Question 1: can you explain the answer situation?", "yellow")),
            self.stage(0.26, self.as_target("tp @s ~ ~ ~ ~30 ~")),
            self.stage(0.31, self.wacky2_tell("Follow-up: why did you rotate instead of answering?", "aqua")),
            self.stage(0.36, self.wacky2_particles("crit", 180, 4.0, 0.15)),
            self.stage(0.41, self.wacky2_sound("entity.villager.no", 0.6)),
            self.stage(0.46, self.as_target("tp @s ~ ~ ~ ~60 ~")),
            self.stage(0.51, f"effect give {self.target} minecraft:glowing 12 0 true"),
            self.stage(0.56, self.wacky2_tell("Press pool reports that glowing counts as a statement.", "light_purple")),
            self.stage(0.61, f"give {self.target} minecraft:book 1"),
            self.stage(0.66, self.wacky2_sound("block.note_block.pling", 1.8)),
            self.stage(0.71, self.as_target("tp @s ~ ~ ~ ~90 ~")),
            self.stage(0.76, self.wacky2_particles("happy_villager", 180, 4.0, 0.15)),
            self.stage(0.82, self.wacky2_tell("Final question denied by an armor stand with no authority.", "gray")),
            *self.wacky2_finale("Press conference concluded without producing a single fact."),
        ]

    def wacky2_village_festival(self) -> CommandPlan:
        return [
            *self.wacky2_opening("VILLAGE FESTIVAL NOBODY APPROVED", "Permits are optional when everyone is already here."),
            *self.wacky2_temp_mobs("villager", 14, 11, "~", "{CustomName:'\"Festival Attendee\"'}"),
            *self.wacky2_temp_mobs("chicken", 8, 9, "~", "{CustomName:'\"Parade Marshal\"'}"),
            *self.wacky2_temp_mobs("cat", 6, 8, "~", "{CustomName:'\"Security\"'}"),
            self.stage(0.06, self.wacky2_sound("block.bell.use", 1.6)),
            self.stage(0.10, self.wacky2_particles("happy_villager", 260, 5.0, 0.2)),
            self.stage(0.14, f"give {self.target} minecraft:bread 6"),
            self.stage(0.18, self.wacky2_tell("Parade route changed because the parade forgot where it was.", "yellow")),
            self.stage(0.22, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.27, self.wacky2_sound("entity.villager.celebrate", 1.8)),
            self.stage(0.32, self.wacky2_particles("note", 220, 4.0, 0.15)),
            self.stage(0.37, f"give {self.target} minecraft:cookie 5"),
            self.stage(0.42, self.wacky2_tell("Main stage replaced by an aggressively average chicken.", "aqua")),
            self.stage(0.47, self.as_target("tp @s ~ ~ ~ ~90 ~")),
            self.stage(0.52, f"effect give {self.target} minecraft:speed 10 1 true"),
            self.stage(0.57, self.wacky2_sound("entity.cat.purr", 1.6)),
            self.stage(0.62, self.wacky2_particles("firework", 220, 5.0, 0.18)),
            self.stage(0.67, f"give {self.target} minecraft:emerald 1"),
            self.stage(0.72, self.wacky2_tell("Festival currency has collapsed after one emerald entered circulation.", "light_purple")),
            self.stage(0.78, self.wacky2_sound("ui.toast.challenge_complete", 1.4)),
            self.stage(0.84, self.wacky2_particles("totem_of_undying", 180, 4.0, 0.2)),
            *self.wacky2_finale("Festival canceled successfully after already happening."),
        ]

    def wacky2_reality_compiler_error(self) -> CommandPlan:
        return [
            *self.wacky2_opening("REALITY COMPILER ERROR", "Unexpected token: chicken at line 404."),
            *self.wacky2_temp_mobs("chicken", 8, 8, "~", "{CustomName:'\"Syntax Error\"'}"),
            *self.wacky2_temp_mobs("sheep", 6, 9, "~", "{Color:10b,CustomName:'\"Deprecated Feature\"'}"),
            *self.wacky2_temp_mobs("rabbit", 8, 10, "~", "{CustomName:'\"Null Pointer\"'}"),
            *self.wacky2_temp_mobs("villager", 5, 8, "~", "{NoAI:1b,CustomName:'\"Debugger\"'}"),
            *self.wacky2_temp_mobs("parrot", 6, 9, "~2", "{CustomName:'\"Warning Message\"'}"),
            self.stage(0.05, self.wacky2_sound("block.note_block.bass", 0.5)),
            self.stage(0.09, self.wacky2_particles("portal", 260, 5.0, 0.3)),
            self.stage(0.13, self.wacky2_tell("ERROR 404: correct answer not found.", "red")),
            self.stage(0.17, f"effect give {self.target} minecraft:nausea 7 0 true"),
            self.stage(0.21, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.25, self.wacky2_sound("entity.experience_orb.pickup", 1.9)),
            self.stage(0.29, f"give {self.target} minecraft:paper 7"),
            self.stage(0.33, self.wacky2_particles("reverse_portal", 220, 5.0, 0.25)),
            self.stage(0.37, self.wacky2_tell("Attempting hotfix: replacing logic with sheep.", "yellow")),
            self.stage(0.41, self.as_target("tp @s ~ ~ ~ ~45 ~")),
            self.stage(0.45, f"effect give {self.target} minecraft:jump_boost 9 2 true"),
            self.stage(0.49, self.wacky2_sound("block.amethyst_block.chime", 1.8)),
            self.stage(0.53, f"give {self.target} minecraft:cookie 3"),
            self.stage(0.57, self.wacky2_particles("enchant", 240, 5.0, 0.22)),
            self.stage(0.61, self.wacky2_tell("Compiler warning: player contains excessive player.", "aqua")),
            self.stage(0.65, self.as_target("tp @s ~ ~ ~ ~90 ~")),
            self.stage(0.69, self.wacky2_sound("block.bell.use", 0.6)),
            self.stage(0.73, f"effect give {self.target} minecraft:levitation 1 1 true"),
            self.stage(0.77, self.wacky2_particles("totem_of_undying", 260, 5.0, 0.25)),
            self.stage(0.81, self.wacky2_tell("Build succeeded with 37 warnings and one parrot.", "green")),
            self.stage(0.85, f"experience add {self.target} 4 points"),
            self.stage(0.88, self.wacky2_sound("ui.toast.challenge_complete", 1.8)),
            *self.wacky2_finale("Reality restarted in safe mode. Nobody knows what that means."),
        ]


    def wacky3_cathedral_organ(self) -> CommandPlan:
        plan: CommandPlan = [
            *self.wacky3_opening("REDSTONE CATHEDRAL ORGAN", "Four sequencers. Forty notes. Absolutely no restraint."),
            self.wacky2_tell("Building a repeater-fed note-block organ above your head.", "yellow"),
        ]
        row_data = [(-12, -9, "gold_block", 3), (-12, -3, "clay", 8), (-12, 3, "packed_ice", 13), (-12, 9, "bone_block", 18)]
        for row, (start_x, z, support, base_note) in enumerate(row_data):
            for i in range(10):
                x = start_x + i * 2
                plan.extend([
                    self.wacky3_set(x, 10, z, support),
                    self.wacky3_set(x, 11, z, f"repeater[facing=east,delay={(i % 4) + 1}]"),
                    self.wacky3_set(x + 1, 10, z, "smooth_quartz"),
                    self.wacky3_set(x + 1, 11, z, "redstone_wire"),
                    self.wacky3_set(x + 1, 10, z + 1, support),
                    self.wacky3_set(x + 1, 11, z + 1, f"note_block[note={(base_note + i * 2) % 25}]"),
                    self.wacky3_set(x + 1, 11, z - 1, "redstone_lamp"),
                ])
            plan.extend(self.wacky3_pulse(start_x - 1, 11, z, 0.12 + row * 0.12, 0.04))
        for t, pitch in [(0.16, 0.7), (0.31, 1.0), (0.46, 1.3), (0.61, 1.7)]:
            plan.append(self.stage(t, self.wacky2_sound("block.note_block.bell", pitch, 1.2)))
        plan.extend(self.wacky3_finale("The organ has rendered your wrong answer in four-part harmony."))
        return plan

    def wacky3_piston_wave_parliament(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("PISTON WAVE PARLIAMENT", "Sixty-four pistons will now vote on your answer.")]
        colors = ["red_concrete", "orange_concrete", "yellow_concrete", "lime_concrete"]
        for row, z in enumerate((-9, -3, 3, 9)):
            for i, x in enumerate(range(-15, 16, 2)):
                plan.extend([
                    self.wacky3_set(x, 9, z, "sticky_piston[facing=up]"),
                    self.wacky3_set(x, 10, z, colors[row]),
                    self.wacky3_set(x, 9, z + 1, "redstone_wire"),
                    self.wacky3_set(x, 8, z + 1, "smooth_quartz"),
                    self.stage(0.10 + row * 0.10 + i * 0.012, self.wacky3_set(x, 8, z, "redstone_block")),
                    self.stage(0.15 + row * 0.10 + i * 0.012, self.wacky3_set(x, 8, z, "air")),
                ])
        plan.extend([
            self.stage(0.34, self.wacky2_particles("electric_spark", 260, 8.0, 0.18)),
            self.stage(0.55, self.wacky2_tell("Motion carried: your answer has been mechanically overruled.", "aqua")),
        ])
        plan.extend(self.wacky3_finale("Parliament adjourned after 64 extremely physical votes."))
        return plan

    def wacky3_hopper_clock_observatory(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("HOPPER CLOCK OBSERVATORY", "Four silent clocks orbit one extremely loud mistake.")]
        origins = [(-10, -10), (8, -10), (-10, 8), (8, 8)]
        for index, (ox, oz) in enumerate(origins):
            y = 11
            plan.extend([
                self.wacky3_set(ox, y, oz, "hopper[facing=east]"),
                self.wacky3_set(ox + 1, y, oz, "hopper[facing=south]"),
                self.wacky3_set(ox + 1, y, oz + 1, "hopper[facing=west]"),
                self.wacky3_set(ox, y, oz + 1, "hopper[facing=north]"),
                self.wacky3_item_replace(ox, y, oz, 0, "redstone_torch", 1),
                self.wacky3_set(ox - 1, y, oz, "comparator[facing=west]"),
                self.wacky3_set(ox + 2, y, oz, "comparator[facing=east]"),
                self.wacky3_set(ox + 1, y, oz + 2, "comparator[facing=south]"),
                self.wacky3_set(ox, y, oz - 1, "comparator[facing=north]"),
                self.wacky3_set(ox - 2, y, oz, "redstone_lamp"),
                self.wacky3_set(ox + 3, y, oz, "redstone_lamp"),
                self.wacky3_set(ox + 1, y, oz + 3, "redstone_lamp"),
                self.wacky3_set(ox, y, oz - 2, "redstone_lamp"),
            ])
            plan.append(self.stage(0.18 + index * 0.11, self.wacky2_sound("block.note_block.hat", 0.8 + index * 0.25, 0.9)))
        plan.extend([
            self.stage(0.38, self.wacky2_tell("The clocks are transferring one item around four loops because one clock was apparently insufficient.", "yellow")),
            self.stage(0.68, self.wacky2_particles("enchant", 240, 7.0, 0.15)),
        ])
        plan.extend(self.wacky3_finale("Time itself has filed a redstone incident report."))
        return plan

    def wacky3_minecart_signal_roundabout(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("MINECART SIGNAL ROUNDABOUT", "Detector rails now control an unnecessarily ceremonial traffic system.")]
        y = 11
        plan.append(self.wacky3_fill(-9, 10, -9, 9, 10, 9, "smooth_quartz", "keep"))
        for x in range(-7, 8):
            block = "detector_rail[shape=east_west]" if x in (-4, 0, 4) else "powered_rail[shape=east_west,powered=true]"
            plan.extend([self.wacky3_set(x, y, -8, block), self.wacky3_set(x, y, 8, block)])
        for z in range(-7, 8):
            block = "detector_rail[shape=north_south]" if z in (-4, 0, 4) else "powered_rail[shape=north_south,powered=true]"
            plan.extend([self.wacky3_set(-8, y, z, block), self.wacky3_set(8, y, z, block)])
        corners = [(-8, -8, "south_east"), (8, -8, "south_west"), (8, 8, "north_west"), (-8, 8, "north_east")]
        for x, z, shape in corners:
            plan.extend([self.wacky3_set(x, y, z, f"rail[shape={shape}]"), self.wacky3_set(x, 9, z, "redstone_block")])
        for x, z in [(-4, -8), (0, -8), (4, -8), (8, -4), (8, 0), (8, 4), (4, 8), (0, 8), (-4, 8), (-8, 4), (-8, 0), (-8, -4)]:
            ox = 0 if x else 2
            oz = 2 if z == 0 else (1 if z < 0 else -1)
            plan.extend([
                self.wacky3_set(x + (1 if x <= 0 else -1), y, z + (1 if z <= 0 else -1), "redstone_lamp"),
                self.wacky3_set(x + (2 if x <= 0 else -2), y, z + (2 if z <= 0 else -2), "bell"),
            ])
        plan.extend([
            self.wacky3_temp_entity("minecart", -7, y, -8, "{Motion:[0.55d,0.0d,0.0d]}"),
            self.stage(0.30, self.wacky3_temp_entity("minecart", 7, y, 8, "{Motion:[-0.55d,0.0d,0.0d]}")),
            self.stage(0.47, self.wacky2_tell("Each cart is now voting on junction policy by physically occupying detector rails.", "aqua")),
        ])
        plan.extend(self.wacky3_finale("Traffic engineering has concluded that the wrong answer caused congestion."))
        return plan

    def wacky3_flying_machine_inspection(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("FLYING MACHINE INSPECTION GANTRY", "Observers, slime, honey, pistons, docks, and far too much paperwork.")]
        # Two compact observer/piston test engines, kept on a bounded gantry rather than carrying the player.
        for side in (-1, 1):
            z = 6 * side
            plan.extend([
                self.wacky3_fill(-14, 13, z - 2, 14, 13, z + 2, "tinted_glass", "keep"),
                self.wacky3_set(-10, 14, z, "sticky_piston[facing=east]"),
                self.wacky3_set(-9, 14, z, "slime_block"),
                self.wacky3_set(-8, 14, z, "observer[facing=west]"),
                self.wacky3_set(-7, 14, z, "slime_block"),
                self.wacky3_set(-6, 14, z, "piston[facing=east]"),
                self.wacky3_set(-9, 15, z, "honey_block"),
                self.wacky3_set(-8, 15, z, "observer[facing=east]"),
                self.wacky3_set(12, 14, z, "iron_block"),
                self.wacky3_set(13, 14, z, "obsidian"),
                self.wacky3_set(-12, 14, z, "note_block[note=12]"),
            ])
            plan.extend(self.wacky3_pulse(-11, 14, z, 0.18 if side < 0 else 0.42, 0.035))
            plan.append(self.stage(0.28 if side < 0 else 0.52, self.wacky2_particles("slime", 140, 4.0, 0.12)))
        plan.extend([
            self.stage(0.62, self.wacky2_tell("Inspection note: piston push limits remain a thing, so the bureaucracy has installed a dock.", "yellow")),
            self.stage(0.74, self.wacky2_sound("block.piston.contract", 0.7, 1.2)),
            self.stage(0.90, self.wacky3_set(13, 14, -6, "air")),
            self.stage(0.90, self.wacky3_set(13, 14, 6, "air")),
        ])
        plan.extend(self.wacky3_finale("Both flying machines have been grounded for excessive observer feedback."))
        return plan

    def wacky3_seven_segment_404(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("SEVEN-SEGMENT 404 TRIBUNAL", "Your answer has been encoded into a wall of lamps.")]
        plan.extend(self.wacky3_lamp_digit(-13, 11, 11, 4))
        plan.extend(self.wacky3_lamp_digit(-4, 11, 11, 0))
        plan.extend(self.wacky3_lamp_digit(5, 11, 11, 4))
        # Decorative decoder backplane: repeaters and bus lines behind the display.
        for z in (13, 15, 17):
            for x in range(-14, 14, 2):
                plan.extend([
                    self.wacky3_set(x, 10, z, "smooth_quartz"),
                    self.wacky3_set(x, 11, z, f"repeater[facing=east,delay={(abs(x) % 4) + 1}]"),
                    self.wacky3_set(x + 1, 11, z, "redstone_wire"),
                ])
        plan.extend([
            self.stage(0.18, self.wacky2_tell("Decoder bus online: 4 - 0 - 4.", "red")),
            self.stage(0.32, self.wacky2_sound("block.note_block.bit", 0.55, 1.0)),
            self.stage(0.48, self.wacky2_sound("block.note_block.bit", 1.1, 1.0)),
            self.stage(0.64, self.wacky2_sound("block.note_block.bit", 1.75, 1.0)),
            self.stage(0.72, self.wacky2_particles("electric_spark", 300, 8.0, 0.16)),
        ])
        plan.extend(self.wacky3_finale("ERROR 404: CORRECT ANSWER NOT FOUND IN INPUT REGISTER."))
        return plan

    def wacky3_observer_domino_serpent(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("OBSERVER DOMINO SERPENT", "A 56-node signal snake is watching itself watch itself.")]
        nodes: list[tuple[int, int]] = []
        for row, z in enumerate(range(-12, 13, 4)):
            xs = list(range(-14, 15, 2))
            if row % 2:
                xs.reverse()
            nodes.extend((x, z) for x in xs)
        for i, (x, z) in enumerate(nodes[:56]):
            facing = "east" if (i // 15) % 2 == 0 else "west"
            plan.extend([
                self.wacky3_set(x, 11, z, f"observer[facing={facing}]"),
                self.wacky3_set(x, 10, z, "smooth_quartz"),
                self.wacky3_set(x, 12, z, "redstone_lamp" if i % 2 == 0 else f"note_block[note={(i * 3) % 25}]"),
            ])
            if i < 40:
                plan.append(self.stage(0.12 + i * 0.014, self.wacky3_set(x, 11, z + 1, "redstone_block")))
                plan.append(self.stage(0.13 + i * 0.014, self.wacky3_set(x, 11, z + 1, "air")))
        plan.append(self.stage(0.70, self.wacky2_tell("The serpent has reached the part of the circuit where nobody remembers what the original input was.", "aqua")))
        plan.extend(self.wacky3_finale("Observer chain complete. Causality has been asked to leave the server."))
        return plan

    def wacky3_dropper_rube_goldberg(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("DROPPER RUBE GOLDBERG MAILROOM", "One button. Twelve departments. Zero justification.")]
        for i in range(8):
            x = -14 + i * 4
            z = -6 if i % 2 == 0 else 6
            facing = "east" if i < 7 else "west"
            plan.extend([
                self.wacky3_set(x, 11, z, f"dropper[facing={facing}]"),
                self.wacky3_item_replace(x, 11, z, 0, "paper", 8),
                self.wacky3_set(x, 10, z, "smooth_quartz"),
                self.wacky3_set(x, 11, z + (1 if z < 0 else -1), "repeater[facing=east,delay=4]"),
                self.wacky3_set(x + 1, 11, z + (1 if z < 0 else -1), "redstone_wire"),
                self.wacky3_set(x + 2, 11, z, "target"),
                self.wacky3_set(x + 2, 12, z, f"note_block[note={(i * 4) % 25}]"),
            ])
            plan.extend(self.wacky3_pulse(x - 1, 11, z, 0.12 + i * 0.065, 0.022))
        for i, x in enumerate(range(-12, 13, 4)):
            plan.extend([
                self.wacky3_set(x, 14, 0, "sticky_piston[facing=up]"),
                self.wacky3_set(x, 15, 0, "lime_wool" if i % 2 else "magenta_wool"),
            ])
            plan.extend(self.wacky3_pulse(x, 13, 0, 0.20 + i * 0.055, 0.03))
        plan.extend([
            self.stage(0.66, self.wacky2_sound("block.bell.use", 1.2, 1.2)),
            self.stage(0.72, self.wacky2_tell("The paper has been forwarded, re-forwarded, mechanically stamped, and emotionally lost.", "yellow")),
        ])
        plan.extend(self.wacky3_finale("Rube Goldberg mail delivery completed one task using approximately every component available."))
        return plan

    def wacky3_item_sorter_appeals(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("ITEM SORTER APPEALS OFFICE", "Six comparator filters are now categorizing your mistake.")]
        items = ["cobblestone", "dirt", "paper", "egg", "redstone", "cookie"]
        for i, item in enumerate(items):
            x = -15 + i * 6
            plan.extend([
                self.wacky3_set(x, 14, -3, "hopper[facing=east]"),
                self.wacky3_set(x, 13, -3, "hopper[facing=down]"),
                self.wacky3_item_replace(x, 13, -3, 0, item, 41),
                self.wacky3_item_replace(x, 13, -3, 1, "redstone_torch", 1),
                self.wacky3_item_replace(x, 13, -3, 2, "redstone_torch", 1),
                self.wacky3_item_replace(x, 13, -3, 3, "redstone_torch", 1),
                self.wacky3_item_replace(x, 13, -3, 4, "redstone_torch", 1),
                self.wacky3_set(x, 13, -2, "comparator[facing=south]"),
                self.wacky3_set(x, 12, -1, "repeater[facing=south,delay=1]"),
                self.wacky3_set(x, 12, -2, "redstone_wire"),
                self.wacky3_set(x, 12, -3, "redstone_torch"),
                self.wacky3_set(x, 11, -3, "barrel"),
                self.wacky3_set(x, 13, 1, "redstone_lamp"),
                self.wacky3_set(x, 12, 1, "smooth_quartz"),
                self.wacky3_set(x, 12, 0, "redstone_wire"),
            ])
        for i, item in enumerate(reversed(items)):
            plan.append(self.stage(0.16 + i * 0.08, self.wacky3_item_replace(-15 + (5 - i) * 6, 14, -3, 0, item, 8)))
        plan.append(self.stage(0.70, self.wacky2_tell("Sorter result: your answer has been filed under MISCELLANEOUS / UNRECOVERABLE.", "red")))
        plan.extend(self.wacky3_finale("Appeal denied by six tileable modules acting in parallel."))
        return plan

    def wacky3_piston_iris_portal(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("PISTON IRIS BUREAUCRACY PORTAL", "A twelve-piston aperture will open, close, reconsider, and open sideways.")]
        # Vertical display plane at z=10, with piston rings aimed toward a 5x5 aperture.
        ring = [(-4, 0, "east"), (4, 0, "west"), (0, -4, "south"), (0, 4, "north")]
        for level in range(11, 18, 2):
            for dx, dz, facing in ring:
                plan.extend([
                    self.wacky3_set(dx, level, 10 + dz, f"sticky_piston[facing={facing}]"),
                    self.wacky3_set(dx + (1 if facing == "east" else -1 if facing == "west" else 0), level, 10 + dz + (1 if facing == "south" else -1 if facing == "north" else 0), "purple_concrete"),
                ])
        pulse_points = [(-5, 11, 10), (5, 13, 10), (0, 15, 5), (0, 17, 15), (-5, 17, 10), (5, 15, 10), (0, 13, 5), (0, 11, 15)]
        for i, (x, y, z) in enumerate(pulse_points):
            plan.extend(self.wacky3_pulse(x, y, z, 0.14 + i * 0.07, 0.04))
        plan.extend([
            self.stage(0.48, self.wacky2_particles("portal", 260, 4.0, 0.28)),
            self.stage(0.67, self.wacky2_tell("The portal has opened to the Department of More Doors.", "light_purple")),
        ])
        plan.extend(self.wacky3_finale("Iris mechanism complete: access denied anyway."))
        return plan

    def wacky3_elevator_to_nowhere(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("REDSTONE ELEVATOR TO NOWHERE", "A vertical piston stack will perform several floors of administrative motion.")]
        for y in range(9, 22, 2):
            plan.extend([
                self.wacky3_set(0, y, 0, "sticky_piston[facing=up]"),
                self.wacky3_set(0, y + 1, 0, "slime_block" if (y // 2) % 2 else "honey_block"),
                self.wacky3_set(2, y, 0, "observer[facing=down]"),
                self.wacky3_set(3, y, 0, "redstone_lamp"),
                self.wacky3_set(-2, y, 0, f"note_block[note={(y * 2) % 25}]"),
            ])
            plan.extend(self.wacky3_pulse(0, y - 1, 0, 0.10 + (y - 9) * 0.035, 0.035))
        plan.extend([
            self.stage(0.35, self.wacky2_tell("Floor 3: Accounting. Floor 4: More Accounting. Floor 5 has been removed for maintenance.", "yellow")),
            self.stage(0.62, self.wacky2_particles("cloud", 180, 3.0, 0.12)),
        ])
        plan.extend(self.wacky3_finale("Elevator arrived exactly where it started, but with substantially more circuitry."))
        return plan

    def wacky3_comparator_mood_meter(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("COMPARATOR ANALOG MOOD LAB", "Eight signal strengths are measuring how incorrect that was.")]
        for i in range(8):
            x = -14 + i * 4
            level = i + 1
            plan.extend([
                self.wacky3_set(x, 11, -6, f"composter[level={level}]"),
                self.wacky3_set(x, 11, -5, "comparator[facing=south]"),
                self.wacky3_set(x, 10, -4, "smooth_quartz"),
                self.wacky3_set(x, 11, -4, "redstone_wire"),
            ])
            for j in range(1, 9):
                plan.extend([
                    self.wacky3_set(x, 10, -4 + j, "smooth_quartz"),
                    self.wacky3_set(x, 11, -4 + j, "redstone_wire" if j < 8 else "redstone_lamp"),
                ])
            plan.append(self.stage(0.14 + i * 0.065, self.wacky2_sound("block.note_block.xylophone", 0.6 + i * 0.14, 0.8)))
        plan.extend([
            self.stage(0.64, self.wacky2_tell("Analog result: signal strength approximately 'why did you answer that'.", "aqua")),
            self.stage(0.73, self.wacky2_particles("happy_villager", 200, 6.0, 0.14)),
        ])
        plan.extend(self.wacky3_finale("Comparator laboratory has converted embarrassment into a measurable voltage-like quantity."))
        return plan

    def wacky3_rs_latch_argument(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("RS LATCH ARGUMENT CHAMBER", "SET says yes. RESET says no. The lamps are taking sides.")]
        for offset in (-8, 0, 8):
            plan.extend([
                self.wacky3_set(offset - 2, 11, 0, "smooth_quartz"),
                self.wacky3_set(offset + 2, 11, 0, "smooth_quartz"),
                self.wacky3_set(offset - 1, 11, 0, "redstone_torch"),
                self.wacky3_set(offset + 1, 11, 0, "redstone_torch"),
                self.wacky3_set(offset - 2, 12, 0, "redstone_wire"),
                self.wacky3_set(offset + 2, 12, 0, "redstone_wire"),
                self.wacky3_set(offset, 12, -1, "redstone_wire"),
                self.wacky3_set(offset, 12, 1, "redstone_wire"),
                self.wacky3_set(offset - 4, 11, 0, "redstone_lamp"),
                self.wacky3_set(offset + 4, 11, 0, "redstone_lamp"),
            ])
        for i, (x, z) in enumerate([(-11, 0), (-5, 0), (-3, 0), (3, 0), (5, 0), (11, 0), (-11, 0), (11, 0)]):
            plan.extend(self.wacky3_pulse(x, 11, z, 0.14 + i * 0.07, 0.025))
        plan.extend([
            self.stage(0.48, self.wacky2_tell("SET and RESET have entered a stable disagreement.", "yellow")),
            self.stage(0.70, self.wacky2_sound("block.lever.click", 1.7, 1.0)),
        ])
        plan.extend(self.wacky3_finale("Latch state preserved indefinitely, unlike confidence in the previous answer."))
        return plan

    def wacky3_t_flip_flop_hall(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("T-FLIP-FLOP INDECISION HALL", "Six droppers will repeatedly change their minds.")]
        for i in range(6):
            x = -15 + i * 6
            plan.extend([
                self.wacky3_set(x, 12, -2, "dropper[facing=east]"),
                self.wacky3_set(x + 1, 12, -2, "dropper[facing=west]"),
                self.wacky3_item_replace(x, 12, -2, 0, "redstone_torch", 1),
                self.wacky3_set(x - 1, 12, -2, "comparator[facing=west]"),
                self.wacky3_set(x - 2, 12, -2, "redstone_lamp"),
                self.wacky3_set(x + 2, 12, -2, "comparator[facing=east]"),
                self.wacky3_set(x + 3, 12, -2, "redstone_lamp"),
                self.wacky3_set(x, 11, 1, "stone_button[face=floor]"),
                self.wacky3_set(x, 11, 0, "repeater[facing=north,delay=1]"),
                self.wacky3_set(x, 11, -1, "redstone_wire"),
            ])
            for j in range(3):
                plan.extend(self.wacky3_pulse(x, 12, -3, 0.12 + i * 0.035 + j * 0.18, 0.02))
        plan.append(self.stage(0.72, self.wacky2_tell("Every pulse toggles a state. None of those states are 'correct answer'.", "aqua")))
        plan.extend(self.wacky3_finale("Indecision hall has toggled itself into a committee meeting."))
        return plan

    def wacky3_binary_shame_counter(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("FOUR-BIT BINARY SHAME COUNTER", "Counting from 0000 to 1111 because one punishment state was too simple.")]
        bit_x = [-9, -3, 3, 9]
        for bit, x in enumerate(bit_x):
            plan.extend([
                self.wacky3_set(x, 13, 6, "redstone_lamp"),
                self.wacky3_set(x, 12, 6, "smooth_quartz"),
                self.wacky3_set(x, 12, 4, "repeater[facing=south,delay=2]"),
                self.wacky3_set(x, 12, 5, "redstone_wire"),
                self.wacky3_set(x, 13, 3, f"note_block[note={5 + bit * 5}]"),
            ])
        for value in range(16):
            t = 0.10 + value * 0.045
            for bit, x in enumerate(bit_x):
                on = bool(value & (1 << (3 - bit)))
                plan.append(self.stage(t, self.wacky3_set(x, 13, 7, "redstone_block" if on else "air")))
            plan.append(self.stage(t, self.wacky2_sound("block.note_block.bit", 0.55 + value * 0.055, 0.45)))
        plan.append(self.stage(0.78, self.wacky2_tell("Counter overflow achieved. The mistake has wrapped around to zero and is still wrong.", "red")))
        plan.extend(self.wacky3_finale("Four bits were insufficient to encode the administrative consequences."))
        return plan

    def wacky3_pulse_extender_tunnel(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("COMPARATOR PULSE-EXTENDER TIME TUNNEL", "A short input is about to become an offensively long output.")]
        for lane, z in enumerate((-9, -3, 3, 9)):
            for x in range(-12, 13):
                plan.extend([self.wacky3_set(x, 10, z, "smooth_quartz"), self.wacky3_set(x, 11, z, "redstone_wire")])
            plan.extend([
                self.wacky3_set(-11, 11, z + 1, "comparator[facing=east,mode=subtract]"),
                self.wacky3_set(-9, 11, z + 1, "comparator[facing=west,mode=subtract]"),
                self.wacky3_set(12, 11, z, "redstone_lamp"),
                self.wacky3_set(13, 11, z, "note_block[note=18]"),
            ])
            plan.extend(self.wacky3_pulse(-13, 11, z, 0.12 + lane * 0.12, 0.02))
        plan.extend([
            self.stage(0.58, self.wacky2_tell("Input pulse duration: tiny. Output bureaucracy duration: effectively geological.", "yellow")),
            self.stage(0.74, self.wacky2_particles("cloud", 180, 5.0, 0.08)),
        ])
        plan.extend(self.wacky3_finale("Pulse extender has finished stretching one mistake across several fiscal quarters."))
        return plan

    def wacky3_randomizer_casino(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("REDSTONE RANDOMIZER CASINO AUDIT", "Droppers, comparators, lamps, bells, and absolutely no gambling economy.")]
        for i in range(5):
            x = -12 + i * 6
            plan.extend([
                self.wacky3_set(x, 12, 0, "dropper[facing=down]"),
                self.wacky3_item_replace(x, 12, 0, 0, "stick", 1),
                self.wacky3_item_replace(x, 12, 0, 1, "snowball", 16),
                self.wacky3_item_replace(x, 12, 0, 2, "egg", 16),
                self.wacky3_item_replace(x, 12, 0, 3, "book", 1),
                self.wacky3_set(x, 11, 0, "hopper[facing=down]"),
                self.wacky3_set(x, 10, 0, "barrel"),
                self.wacky3_set(x - 1, 10, 0, "comparator[facing=west]"),
                self.wacky3_set(x - 2, 10, 0, "redstone_lamp"),
                self.wacky3_set(x + 1, 10, 0, "bell"),
            ])
            for j in range(4):
                plan.extend(self.wacky3_pulse(x, 12, 1, 0.10 + i * 0.04 + j * 0.12, 0.018))
        plan.extend([
            self.stage(0.66, self.wacky2_tell("Audit finding: randomness is functioning, accounting is not.", "aqua")),
            self.stage(0.76, self.wacky2_sound("block.bell.use", 1.6, 1.2)),
        ])
        plan.extend(self.wacky3_finale("Casino closed after the redstone department discovered probability."))
        return plan

    def wacky3_piston_tape_billboard(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("PISTON TAPE BILLBOARD", "A mechanical display will now scroll colors past a wall of observers.")]
        colors = ["red_wool", "orange_wool", "yellow_wool", "lime_wool", "cyan_wool", "blue_wool", "purple_wool", "magenta_wool"]
        for row in range(5):
            y = 11 + row * 2
            for i, x in enumerate(range(-14, 15, 4)):
                color = colors[(i + row) % len(colors)]
                plan.extend([
                    self.wacky3_set(x, y, 6, "sticky_piston[facing=east]"),
                    self.wacky3_set(x + 1, y, 6, color),
                    self.wacky3_set(x + 2, y, 6, "observer[facing=west]"),
                    self.wacky3_set(x + 2, y + 1, 6, "redstone_lamp"),
                ])
                plan.extend(self.wacky3_pulse(x - 1, y, 6, 0.10 + row * 0.08 + i * 0.025, 0.03))
        plan.append(self.stage(0.68, self.wacky2_tell("Billboard message decoding: PLEASE STOP FEEDING THE PISTON TAPE.", "yellow")))
        plan.extend(self.wacky3_finale("Mechanical billboard jammed successfully at maximum visual complexity."))
        return plan

    def wacky3_door_factory(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("PISTON DOOR FACTORY", "2x2, 3x3-ish, flush-ish, iris-ish: every door must now be tested.")]
        door_centers = [(-10, 11, 8), (0, 11, 8), (10, 11, 8)]
        sizes = [2, 3, 4]
        for door_index, ((cx, cy, cz), size) in enumerate(zip(door_centers, sizes)):
            for y in range(cy, cy + size):
                plan.extend([
                    self.wacky3_set(cx - size, y, cz, "sticky_piston[facing=east]"),
                    self.wacky3_set(cx + size, y, cz, "sticky_piston[facing=west]"),
                    self.wacky3_set(cx - size + 1, y, cz, "blue_concrete"),
                    self.wacky3_set(cx + size - 1, y, cz, "red_concrete"),
                ])
            for x in range(cx - size, cx + size + 1):
                plan.extend([
                    self.wacky3_set(x, cy - 2, cz, "smooth_quartz"),
                    self.wacky3_set(x, cy - 1, cz, "redstone_wire"),
                ])
            plan.extend(self.wacky3_pulse(cx - size - 1, cy, cz, 0.14 + door_index * 0.18, 0.08))
            plan.extend(self.wacky3_pulse(cx + size + 1, cy, cz, 0.23 + door_index * 0.18, 0.08))
        plan.extend([
            self.stage(0.65, self.wacky2_tell("Acceptance test failed: all doors opened, which is apparently suspicious.", "aqua")),
            self.stage(0.73, self.wacky2_sound("block.piston.extend", 0.5, 1.5)),
        ])
        plan.extend(self.wacky3_finale("Door factory certified itself, then immediately revoked the certificate."))
        return plan

    def wacky3_lamp_matrix_scanner(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("LAMP MATRIX SCANNER", "An 8x8 redstone display is scanning for signs of a correct answer.")]
        for row in range(8):
            y = 10 + row
            for col in range(8):
                x = -14 + col * 4
                plan.extend([
                    self.wacky3_set(x, y, 10, "redstone_lamp"),
                    self.wacky3_set(x, y, 11, "smooth_quartz"),
                    self.wacky3_set(x, y, 12, "redstone_wire"),
                ])
        for scan in range(8):
            t = 0.12 + scan * 0.075
            for row in range(8):
                x = -14 + scan * 4
                y = 10 + row
                plan.append(self.stage(t, self.wacky3_set(x, y, 11, "redstone_block")))
                plan.append(self.stage(t + 0.045, self.wacky3_set(x, y, 11, "smooth_quartz")))
            plan.append(self.stage(t, self.wacky2_sound("block.note_block.hat", 0.7 + scan * 0.12, 0.5)))
        plan.append(self.stage(0.74, self.wacky2_tell("SCAN COMPLETE: correct answer signature absent from all 64 pixels.", "red")))
        plan.extend(self.wacky3_finale("Matrix found only redstone, lamps, and escalating concern."))
        return plan

    def wacky3_minecart_logic_junction(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("MINECART LOGIC JUNCTION", "Three rail branches, detector inputs, powered outputs, one indecisive cart.")]
        y = 11
        # Main line and three branch indicators.
        for x in range(-14, 15):
            rail = "detector_rail[shape=east_west]" if x in (-8, 0, 8) else "powered_rail[shape=east_west,powered=true]"
            plan.extend([self.wacky3_set(x, 10, 0, "smooth_quartz"), self.wacky3_set(x, y, 0, rail)])
        for x in (-8, 0, 8):
            plan.extend([
                self.wacky3_set(x, 10, 2, "smooth_quartz"),
                self.wacky3_set(x, 11, 2, "redstone_lamp"),
                self.wacky3_set(x, 11, 1, "redstone_wire"),
                self.wacky3_set(x, 10, -2, "smooth_quartz"),
                self.wacky3_set(x, 11, -2, "note_block[note=12]"),
                self.wacky3_set(x, 11, -1, "redstone_wire"),
            ])
        plan.extend([
            self.wacky3_temp_entity("minecart", -13, y, 0, "{Motion:[0.65d,0.0d,0.0d]}"),
            self.stage(0.34, self.wacky3_temp_entity("minecart", 13, y, 0, "{Motion:[-0.65d,0.0d,0.0d]}")),
            self.stage(0.55, self.wacky2_tell("Junction logic has detected two mutually exclusive directions and selected both.", "yellow")),
        ])
        plan.extend(self.wacky3_finale("Rail committee recommends another committee to decide where the cart went."))
        return plan

    def wacky3_bell_relay_tower(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("BELL + NOTE-BLOCK RELAY TOWER", "A vertical repeater ladder will announce this mistake to several imaginary departments.")]
        for level in range(7):
            y = 10 + level * 2
            side = -1 if level % 2 == 0 else 1
            plan.extend([
                self.wacky3_set(0, y, 0, "smooth_quartz"),
                self.wacky3_set(0, y + 1, 0, "redstone_wire"),
                self.wacky3_set(2 * side, y + 1, 0, f"repeater[facing={'west' if side < 0 else 'east'},delay={(level % 4)+1}]"),
                self.wacky3_set(3 * side, y + 1, 0, "bell" if level % 2 == 0 else f"note_block[note={(level * 4) % 25}]"),
                self.wacky3_set(-2 * side, y + 1, 0, "redstone_lamp"),
            ])
            plan.extend(self.wacky3_pulse(0, y + 1, 1, 0.12 + level * 0.08, 0.025))
        plan.extend([
            self.stage(0.68, self.wacky2_particles("note", 220, 5.0, 0.15)),
            self.stage(0.74, self.wacky2_tell("Relay tower confirms receipt. Nobody knows who sent the original pulse.", "aqua")),
        ])
        plan.extend(self.wacky3_finale("Signal reached the top and discovered another repeater."))
        return plan

    def wacky3_slime_mechanical_heart(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("SLIME-BLOCK MECHANICAL HEART", "Twenty-four pistons are about to simulate cardiovascular engineering very badly.")]
        # Heart-shaped-ish slime/honey core with radial pistons.
        core = [(-2, 14, 0), (2, 14, 0), (-4, 15, 0), (4, 15, 0), (-3, 16, 0), (3, 16, 0), (0, 12, 0), (0, 13, 0), (0, 14, 0), (0, 15, 0)]
        for i, (x, y, z) in enumerate(core):
            plan.append(self.wacky3_set(x, y, z, "slime_block" if i % 2 else "honey_block"))
        piston_positions = []
        for y in (12, 14, 16, 18):
            piston_positions.extend([(-7, y, 0, "east"), (7, y, 0, "west"), (0, y, -7, "south"), (0, y, 7, "north")])
        for i, (x, y, z, facing) in enumerate(piston_positions):
            plan.extend([
                self.wacky3_set(x, y, z, f"sticky_piston[facing={facing}]"),
                self.wacky3_set(x, y + 1, z, "redstone_lamp"),
            ])
            for beat in range(3):
                plan.extend(self.wacky3_pulse(x + (-1 if facing == "east" else 1 if facing == "west" else 0), y, z + (-1 if facing == "south" else 1 if facing == "north" else 0), 0.12 + beat * 0.20 + (i % 4) * 0.012, 0.045))
        plan.extend([
            self.stage(0.33, self.wacky2_sound("block.note_block.basedrum", 0.7, 1.4)),
            self.stage(0.53, self.wacky2_sound("block.note_block.basedrum", 0.7, 1.4)),
            self.stage(0.73, self.wacky2_sound("block.note_block.basedrum", 0.7, 1.4)),
        ])
        plan.extend(self.wacky3_finale("Mechanical heart survived. The answer remains clinically incorrect."))
        return plan

    def wacky3_logic_gate_calculator(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("REDSTONE LOGIC-GATE CALCULATOR COSPLAY", "AND, OR, NOT, XOR-ish: enough logic to prove one input was wrong.")]
        gates = [(-12, "AND"), (-4, "OR"), (4, "NOT"), (12, "XOR")]
        for idx, (x, name) in enumerate(gates):
            plan.extend([
                self.wacky3_set(x, 10, -4, "smooth_quartz"),
                self.wacky3_set(x - 2, 11, -4, "redstone_wire"),
                self.wacky3_set(x + 2, 11, -4, "redstone_wire"),
                self.wacky3_set(x, 11, -4, "redstone_torch" if name in ("NOT", "XOR") else "repeater[facing=south]"),
                self.wacky3_set(x, 11, -1, "redstone_lamp"),
                self.wacky3_set(x, 11, -2, "redstone_wire"),
                self.wacky3_set(x, 10, -1, "smooth_quartz"),
                self.wacky3_set(x, 13, -1, f"note_block[note={4 + idx * 6}]"),
            ])
        input_points = [(-14, 11, -4), (-10, 11, -4), (-6, 11, -4), (-2, 11, -4), (2, 11, -4), (6, 11, -4), (10, 11, -4), (14, 11, -4)]
        patterns = [(1,0,1,0,1,0,1,0), (1,1,0,0,1,1,0,0), (0,1,0,1,0,1,0,1), (1,1,1,1,1,1,1,1)]
        for pidx, pattern in enumerate(patterns):
            t = 0.14 + pidx * 0.17
            for point, state in zip(input_points, pattern):
                x, y, z = point
                plan.append(self.stage(t, self.wacky3_set(x, y, z, "redstone_block" if state else "smooth_quartz")))
            plan.append(self.stage(t + 0.05, self.wacky2_sound("block.note_block.bit", 0.8 + pidx * 0.3, 0.8)))
        plan.append(self.stage(0.78, self.wacky2_tell("Logic result: TRUE AND FALSE OR PANIC XOR PAPERWORK = still wrong.", "red")))
        plan.extend(self.wacky3_finale("Calculator produced a proof consisting mostly of redstone dust."))
        return plan

    def wacky3_grand_rube_goldberg(self) -> CommandPlan:
        plan: CommandPlan = [*self.wacky3_opening("GRAND UNIFIED RUBE GOLDBERG CATHEDRAL", "Every subsystem gets one job: trigger another subsystem.")]
        # Zone A: minecart starter / detector rail.
        for x in range(-16, -5):
            plan.extend([
                self.wacky3_set(x, 10, -10, "smooth_quartz"),
                self.wacky3_set(x, 11, -10, "detector_rail[shape=east_west]" if x == -10 else "powered_rail[shape=east_west,powered=true]"),
            ])
        plan.append(self.wacky3_temp_entity("minecart", -15, 11, -10, "{Motion:[0.7d,0.0d,0.0d]}"))
        # Zone B: piston accordion.
        for i, x in enumerate(range(-12, 13, 3)):
            plan.extend([
                self.wacky3_set(x, 11, -3, "sticky_piston[facing=up]"),
                self.wacky3_set(x, 12, -3, "slime_block" if i % 2 else "honey_block"),
                self.wacky3_set(x, 13, -3, "redstone_lamp"),
            ])
            plan.extend(self.wacky3_pulse(x, 10, -3, 0.18 + i * 0.035, 0.035))
        # Zone C: note-block observer chain.
        for i, x in enumerate(range(-14, 15, 2)):
            plan.extend([
                self.wacky3_set(x, 10, 4, "smooth_quartz"),
                self.wacky3_set(x, 11, 4, f"repeater[facing=east,delay={(i % 4) + 1}]"),
                self.wacky3_set(x, 11, 5, f"note_block[note={(i * 2 + 5) % 25}]"),
                self.wacky3_set(x, 11, 3, "redstone_lamp"),
            ])
        plan.extend(self.wacky3_pulse(-15, 11, 4, 0.46, 0.04))
        # Zone D: dropper/hopper mail transfer.
        for i, x in enumerate((-9, -3, 3, 9)):
            plan.extend([
                self.wacky3_set(x, 15, 10, "dropper[facing=down]"),
                self.wacky3_item_replace(x, 15, 10, 0, "paper", 16),
                self.wacky3_set(x, 14, 10, "hopper[facing=down]"),
                self.wacky3_set(x, 13, 10, "barrel"),
                self.wacky3_set(x - 1, 13, 10, "comparator[facing=west]"),
                self.wacky3_set(x - 2, 13, 10, "bell"),
            ])
            plan.extend(self.wacky3_pulse(x, 15, 11, 0.58 + i * 0.045, 0.02))
        # Zone E: absurd lamp finale / pseudo-binary display.
        for row in range(4):
            for col in range(8):
                x = -14 + col * 4
                y = 18 + row
                plan.extend([self.wacky3_set(x, y, 0, "redstone_lamp"), self.wacky3_set(x, y, 1, "smooth_quartz")])
                if (row + col) % 2 == 0:
                    plan.append(self.stage(0.72 + row * 0.025, self.wacky3_set(x, y, 1, "redstone_block")))
        plan.extend([
            self.stage(0.22, self.wacky2_tell("STAGE A: minecart authorization token accepted.", "yellow")),
            self.stage(0.40, self.wacky2_tell("STAGE B: piston accordion has converted motion into more motion.", "aqua")),
            self.stage(0.56, self.wacky2_tell("STAGE C: repeater cathedral is now singing the paperwork onward.", "light_purple")),
            self.stage(0.70, self.wacky2_tell("STAGE D: droppers have mailed the signal to a barrel four blocks away.", "green")),
            self.stage(0.82, self.wacky2_particles("electric_spark", 420, 10.0, 0.28)),
            self.stage(0.84, self.wacky2_sound("block.bell.use", 0.6, 1.6)),
            self.stage(0.86, self.wacky2_sound("block.note_block.pling", 1.8, 1.6)),
        ])
        plan.extend(self.wacky3_finale("Grand machine complete: approximately 150 mechanisms collaborated to say 'wrong'."))
        return plan


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
You are the host of a trivia punishment game.
Create exactly one general trivia question in the requested difficulty.

Difficulty scale:
1 = extremely easy for almost anyone.
3 = easy school/common knowledge.
5 = medium pub trivia.
7 = hard.
10 = ridiculously hard but still objectively answerable.

Requirements:
- Category preference: Idk man just make up stuff. Make me laugh.
- Current difficulty: {self.difficulty}/10
- Avoid repeating these recent questions: {self.history[-20:]}
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

Return only JSON with keys:
- correct: boolean
- message: a response for the player that clearly says whether they were correct
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
You are the host of a Minecraft trivia punishment game.

The player got this question wrong:
Question: {question.prompt}
Expected answer: {expected_answer}
Player answer: {user_answer}

The random punishment selected by the game is: {punishment_name}

Write a punishment announcement.
Requirements:
- Be super cool and nonchalant. Says one sentence zingers that make you seem too cool to even comment.
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
    parser.add_argument("--punishment-mode", choices=("brutal", "wacky", "wacky2", "wacky3"), default="brutal", help="Punishment pool to roll from.")
    parser.add_argument("--wacky-punishments", action="store_true", help="Shortcut for --punishment-mode wacky.")
    parser.add_argument("--wacky-punishments2", "--wacky-punishments-2", action="store_true", help="Shortcut for --punishment-mode wacky2: very complex, bizarre, low-lethality punishment sequences.")
    parser.add_argument("--wacky-punishments3", "--wacky-punishments-3", action="store_true", help="Shortcut for --punishment-mode wacky3: giant redstone contraptions, signal chains, clocks, pistons, rails, observers, and logic machines.")
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
    if args.wacky_punishments2:
        args.punishment_mode = "wacky2"
    if args.wacky_punishments3:
        args.punishment_mode = "wacky3"
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
        elif args.punishment_mode == "wacky2":
            chaos.announce("Wacky punishments 2 are enabled. Complexity is king: maximum nonsense, minimum dying in a box.")
        elif args.punishment_mode == "wacky3":
            chaos.announce("Wacky punishments 3 are enabled. Complex redstone is king: clocks, pistons, rails, observers, logic, and Rube Goldberg machinery.")
        if args.answer_player:
            chaos.announce(f"Only answers from {args.answer_player} will count.")
        else:
            chaos.announce("The next player chat message after each question counts as the answer.")
        for index in range(1, args.questions + 1):
            delay_consumed = 0.0
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
                delay_consumed = chaos.run_punishment(
                    punishment_commands,
                    delay_budget_seconds=args.delay_seconds,
                )
            if index < args.questions and args.delay_seconds > 0:
                remaining_delay = max(0.0, args.delay_seconds - delay_consumed)
                if remaining_delay > 0:
                    chaos.announce(f"Next question in {remaining_delay:g} seconds.")
                    time.sleep(remaining_delay)
        chaos.announce("Trivia chaos complete.")
    finally:
        if client is not None:
            client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
