# Support

**There is none.** String Theory is shared as-is, as a starting point for your own project.

- It works on the author's lights: NOMA Smart RGB C9 strings on a Raspberry Pi. That's the only setup it's known to work on.
- There's no help with setup, no troubleshooting, no fixes or features on request, and no promise it works with your lights or keeps working after an app or firmware update.
- Issues and pull requests may go unanswered or be closed without comment. The repository may change, or stop changing, at any time.

## Helping yourself

- [README.md](README.md): setup on a Raspberry Pi, in Docker or on a home computer.
- [docs/hardware.md](docs/hardware.md): which lights work, and what to look for when buying.
- [docs/adapting.md](docs/adapting.md): working out how your controller works with `tools/probe.py`, and what to change.
- [CLAUDE.md](CLAUDE.md): everything learned building it (protocol, timing, what looks good on the bulbs), written for an AI coding assistant. Open your copy in one, such as Claude Code, and ask it for help.
- [tinytuya](https://github.com/jasonacox/tinytuya): the library String Theory uses to talk to Tuya devices. Its documentation and community cover most connection and key problems.

## Making it yours

Fork it, rename it, change anything. It's MIT licensed (see [LICENSE](LICENSE)): keep the copyright notice, and you're free to do the rest. Never publish your `devices.json`, `tinytuya.json` or `data/` folder: they hold your lights' keys.
