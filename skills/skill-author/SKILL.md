---
name: skill-author
description: Draft or improve a Mister Morph skill (a folder with SKILL.md). Use when the user wants to create a skill, turn a routine into a skill, or prepare one for the Morph Skill Store.
requirements:
  - file_io
---

# Skill author

A skill is a folder whose `SKILL.md` teaches the agent one job. The agent reads the frontmatter to decide when the skill applies and the body when it runs.

## 1. Pin down the job

Ask only what you cannot infer:

- What should the agent do, and what does a good result look like?
- When should the skill apply? Collect two or three phrases a user would actually say.
- Which tools does it need (`url_fetch`, `bash`, `read_file`, ...)? Which credentials, if any?

## 2. Write the frontmatter

```yaml
---
name: short-kebab-name          # becomes the folder name
description: One or two sentences: what it does and when to use it.
requirements:                   # tools or programs it relies on
  - url_fetch
auth_profiles: ["service-name"] # only if it calls an API with a credential profile
---
```

The description is how the agent chooses the skill, so name the trigger situations in it.

## 3. Write the body

- Start with the steps, in order. Short imperative sentences.
- Give exact endpoints, commands and fields. Show one example request and the parts of the reply that matter.
- Say what to do when something fails, and when to stop.
- Say what the final answer to the user should look like.
- Keep it under about 300 lines. Put long reference material in a second file and link to it.

Never put secrets in a skill. Credentials come from auth profiles set up by the user.

## 4. Save and try it

Write the folder to the agent's skills directory (for example `~/.morph/skills/<name>/SKILL.md`), switch it on in the console's Skills page, and run a task that should trigger it.

## 5. Submit to the store (optional)

For the Morph Skill Store (https://github.com/quailyquaily/morph-skill-store), add `skills/<name>/skill.yaml` next to `SKILL.md` with `version`, `description`, `author`, `license`, and optional `homepage` and `tags`, then open a pull request. Only text files are accepted; no binaries or install scripts that download code.
