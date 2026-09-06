# Minecraft Trivia Chaos

`trivia_minecraft_chaos.py` runs a terminal trivia game and talks to a local Minecraft Java server through RCON. Correct answers get a short in-game message. Wrong answers roll one of 20 random punishments.

## Minecraft Setup

In `server.properties`, enable RCON:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=change-this-password
```

Restart the server after editing that file.

## Run It

Test without connecting to Minecraft:

```bash
python3 trivia_minecraft_chaos.py --dry-run --questions 5
```

Run against a local server:

```bash
python3 trivia_minecraft_chaos.py --password change-this-password --target @a
```

Useful options:

- `--target @p` punishes only the nearest player.
- `--target PlayerName` punishes one player by name.
- `--questions 50` changes the session length.
- `--host` and `--port` point at a non-default RCON server.

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

I intentionally made the chunk punishment limited. Deleting an actual chunk is better done with a server plugin or world editor and is too easy to make permanently destructive by accident.

## Other Ideas That Would Fit Well

- Timed rounds where taking too long counts as wrong.
- Team mode where one player answers and everyone suffers.
- Minecraft-only answers through chat, using a small server plugin to listen for player chat.
- Difficulty categories like Minecraft, science, history, and math.
- A mercy meter that gives rewards after surviving several punishments.
- Boss rounds every 10 questions with harder questions and bigger consequences.
