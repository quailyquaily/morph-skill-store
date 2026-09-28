# Submitting a skill

1. Fork this repository and add a folder `skills/<id>/`. `<id>` is lowercase letters, digits, `.`, `_` or `-`.
2. Add `SKILL.md`:

   ```markdown
   ---
   name: <id>
   description: What the skill does and when the agent should use it.
   requirements:        # tools or programs it needs (optional)
     - url_fetch
   auth_profiles: []    # credential profiles it expects (optional)
   ---

   # Title

   Steps, exact endpoints or commands, what to do on failure, and what to tell the user.
   ```

3. Add `skill.yaml`:

   ```yaml
   version: 1.0.0
   description: One or two sentences for the store card.
   author: your-github-name
   license: MIT
   homepage: https://example.com   # optional
   tags: [example]                 # optional, up to 5
   ```

4. Run `python3 scripts/build_index.py --check` and fix any errors.
5. Open a pull request. Do not edit `index.json`; CI rebuilds it after the merge.

## What reviewers look at

- The skill does what its description says and nothing else.
- Every command and URL it uses is visible in the files. Nothing is downloaded and run at install time.
- It needs no more access than the job requires. Warnings from CI (`sudo`, `rm -rf`, credential files, scripts) need a reason in the pull request.
- It works: say in the pull request which model and tools you tried it with.

## Updating a skill

Change the files, bump `version` in `skill.yaml`, and open a pull request. Agents that installed an earlier version see **Update** on the Skills page.
