# Minecraft Trivia Chaos

`trivia_minecraft_chaos.py` runs a Minecraft chat trivia game through RCON and the server log. An LLM creates each question in real time and judges whether the answer is correct. Correct answers get a short in-game message. Wrong answers roll one of 60 random punishments.

## Gemini Setup

Put your Gemini API key in `.env`:

```properties
GEMINI_KEY=your-api-key
```

The script also accepts `GEMINI_API_KEY` or `GOOGLE_API_KEY`.

## Ollama Setup

For Ollama Cloud, put your API key in `.env`:

```properties
OLLAMA_API_KEY=your-api-key
```

Ollama Cloud uses `https://ollama.com/api/chat`. Local Ollama can also be used with `--ollama-host http://localhost:11434`.

## Minecraft Setup

In `server.properties`, enable RCON:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=change-this-password
```

Restart the server after editing that file.

The script reads player answers from the Minecraft server log. Run it from the server directory, or pass the log path explicitly:

```bash
--chat-log /path/to/server/logs/latest.log
```

## Run It

Test without connecting to Minecraft commands while still reading answers from a log file:

```bash
python3 trivia_minecraft_chaos.py --dry-run --questions 5 --chat-log logs/latest.log
```

That still uses Gemini. To test completely offline with the old built-in question bank:

```bash
python3 trivia_minecraft_chaos.py --dry-run --offline-questions --questions 5 --delay-seconds 0 --chat-log logs/latest.log
```

Run against a local server with Gemini:

```bash
python3 trivia_minecraft_chaos.py --password change-this-password --target @a
```

Run against a local server with Ollama Cloud:

```bash
python3 trivia_minecraft_chaos.py --llm-provider ollama --ollama-model gpt-oss:120b --password change-this-password --target @a
```

Check Ollama Cloud auth before starting the game:

```bash
python3 trivia_minecraft_chaos.py --llm-provider ollama --check-llm-auth --llm-insecure-skip-verify
```

Run with local Ollama:

```bash
python3 trivia_minecraft_chaos.py --llm-provider ollama --ollama-host http://localhost:11434 --ollama-model llama3.1 --password change-this-password --target @a
```

Useful options:

- `--target @p` punishes only the nearest player.
- `--target PlayerName` punishes one player by name.
- `--answer-player PlayerName` only accepts answers from one Minecraft username.
- `--chat-log logs/latest.log` chooses the server log to read chat answers from.
- `--questions 50` changes the session length. The default is `100`.
- `--delay-seconds 30` waits 30 seconds between questions. The default is `180`, or 3 minutes.
- `--category "Minecraft and science"` nudges the LLM toward a category.
- `--llm-provider ollama` uses Ollama instead of Gemini.
- `--gemini-model gemini-3.7-flash` changes the model.
- `--ollama-model gpt-oss:120b` changes the Ollama model.
- `--ollama-host https://ollama.com` changes the Ollama API host.
- `--llm-ca-file /path/to/cacert.pem` points Python at a CA bundle if HTTPS certificate verification fails.
- `--llm-insecure-skip-verify` disables LLM HTTPS certificate verification for local testing.
- `--host` and `--port` point at a non-default RCON server.

If you see `CERTIFICATE_VERIFY_FAILED` on macOS, your Python install probably does not have its certificate store set up. The best fix is to run Python's `Install Certificates.command` for your Python install. For a quick local test, run:

```bash
python3 trivia_minecraft_chaos.py --dry-run --questions 5 --delay-seconds 0 --llm-insecure-skip-verify --chat-log logs/latest.log
```

## Punishments Included

The script rolls randomly from these:

1. Duplicate nearby hostile mobs, plus an escalating backup wave
2. Twenty creepers
3. Lightning ring
4. Anvil rain
5. Silverfish confetti
6. Slowness and mining fatigue
7. Temporary lava or magma floor
8. Carved pumpkin helmet
9. Vertical launch with slow falling
10. Angry bees
11. Cave spiders
12. Witches
13. Blindness and darkness
14. Phantoms
15. Ghast spawn
16. Primed TNT cough
17. Chicken jockeys
18. Snowball storm
19. Suspicious stew
20. Chunk bite, which clears a small local block pocket instead of deleting a whole chunk
21. Charged creepers
22. Zombie office party
23. Skeleton firing squad
24. Pillager pop quiz
25. Vex paperwork
26. Ravager surprise
27. Blaze drill
28. Magma cube bounce house
29. Slime audit
30. Endermite ankle biters
31. Hoglin hallway
32. Zoglin chaos
33. Guardian laser pointer
34. Elder guardian mining fatigue
35. Arrow rain
36. Trident rain
37. Egg storm
38. Chicken flood
39. Bat cave mode
40. Rabbit distraction
41. Cod flop
42. Goat convention
43. Cobweb trap
44. Ice cube prison
45. Glass timeout box
46. Dirt timeout box
47. Waterlogged boots
48. Lava moat
49. Powder snow pocket
50. Soul sand stumble field
51. Cactus circle
52. Sweet berry bush inconvenience
53. Hunger
54. Poison
55. Wither warning
56. Levitation
57. Glow of shame
58. Thunderstorm
59. Night shift
60. Rotten flesh consolation prize

I intentionally made the chunk punishment limited. Deleting an actual chunk is better done with a server plugin or world editor and is too easy to make permanently destructive by accident.

## Other Ideas That Would Fit Well

- Timed rounds where taking too long counts as wrong.
- Team mode where one player answers and everyone suffers.
- Minecraft-only answers through chat, using a small server plugin to listen for player chat.
- Difficulty categories like Minecraft, science, history, and math.
- A mercy meter that gives rewards after surviving several punishments.
- Boss rounds every 10 questions with harder questions and bigger consequences.
