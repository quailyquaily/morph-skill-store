# Morph Skill Store

Reviewed skills for [Mister Morph](https://github.com/quailyquaily/mistermorph). Browse and install them from the console's **Skills → Store** tab.

A skill is a folder with a `SKILL.md` that teaches the agent one job. Each skill here also has a `skill.yaml` with store details (version, author, license).

## How installing works

1. The console reads [`index.json`](index.json). CI builds it from `skills/` after every merge.
2. Every entry is pinned to a commit, and every file has a SHA-256 checksum.
3. When you press **Install**, the agent opens a new chat topic. It downloads the skill at that commit, checks every checksum, reviews the skill, and tells you what it does and what the risks are.
4. Nothing is installed until you approve the `skill_install` step. Installed skills are switched on straight away.

To remove a skill, delete its folder from the agent's skills directory (for example `~/.morph/skills/<id>`).

## Layout

```
skills/
  <id>/
    SKILL.md      # the skill: frontmatter (name, description, requirements, auth_profiles) + instructions
    skill.yaml    # store metadata; see schema/skill.schema.json
    ...           # optional extra text files (references, templates, scripts)
index.json        # generated; do not edit
scripts/build_index.py
```

## Rules

- Text files only: no binaries, archives, images or symlinks.
- At most 50 files, 512 KiB per file and 2 MiB per skill.
- The `name` in the `SKILL.md` frontmatter must match the folder name.
- The `version` in `skill.yaml` must be bumped whenever a skill changes.
- No secrets. Skills that call APIs use `auth_profiles`, so the user sets up the credential and the agent never sees it.
- A skill is rejected if it pipes downloads into a shell, runs hidden (base64) commands, tries to override the agent's instructions, or sends data to request-collector sites. Other risky patterns (`sudo`, `rm -rf`, credential files, `http://`) are flagged for reviewers.

See [CONTRIBUTING.md](CONTRIBUTING.md) to submit a skill.

## Checking locally

```sh
pip install pyyaml
python3 scripts/build_index.py --check
```
