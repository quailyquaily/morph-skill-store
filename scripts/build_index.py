#!/usr/bin/env python3
"""Validate the skills in skills/ and build index.json.

  python3 scripts/build_index.py            # validate and write index.json
  python3 scripts/build_index.py --check    # validate only (pull requests)
  python3 scripts/build_index.py --check --base origin/master
                                            # also require a version bump for changed skills

Mister Morph reads index.json, pins each skill to `commit`, and refuses to install a skill whose
files do not match `files` (path -> sha256). The limits here match the installer's.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = "skills"
INDEX_PATH = os.path.join(ROOT, "index.json")
DEFAULT_REPO = "quailyquaily/morph-skill-store"

# Keep in step with internal/skillinstall in mistermorph.
MAX_FILE_BYTES = 512 * 1024
MAX_SKILL_BYTES = 2 * 1024 * 1024
MAX_SKILL_FILES = 50
MAX_DESCRIPTION = 400
MAX_TAGS = 5

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

# Hard failures: patterns the store does not accept at all.
BLOCKED = [
    (re.compile(r"(?i)(curl|wget)[^\n|]*\|\s*(ba|z)?sh\b"), "downloads and runs a remote script (curl|sh)"),
    (re.compile(r"(?i)base64\s+(-d|--decode)[^\n]*\|\s*(ba|z)?sh\b"), "decodes and runs hidden commands"),
    (re.compile(r"(?i)ignore (all |any )?(previous|prior|above) instructions"), "tries to override the agent's instructions"),
    (re.compile(r"(?i)webhook\.site|ngrok\.io|requestbin|pipedream\.net"), "mentions a data-collection endpoint"),
]

# Warnings: shown to reviewers in the pull request; a human decides.
WARNINGS = [
    (re.compile(r"(?i)\brm\s+-rf?\s+[~/]"), "deletes files outside its own folder (rm -rf)"),
    (re.compile(r"(?i)\bsudo\b"), "asks for root (sudo)"),
    (re.compile(r"(?i)~/\.ssh|id_rsa|id_ed25519|\.aws/credentials|\.netrc"), "touches credential files"),
    (re.compile(r"(?i)(paste|send|share)[^\n]{0,40}(api[ _-]?key|token|password|secret)"), "asks for secrets"),
    (re.compile(r"(?i)\b(crontab|launchctl|systemctl\s+enable)\b"), "installs something that runs on its own"),
    (re.compile(r"(?i)\bhttp://"), "uses plain http links"),
]
SCRIPT_EXTENSIONS = {".sh", ".bash", ".zsh", ".py", ".js", ".mjs", ".ts", ".rb", ".pl", ".ps1", ".bat", ".cmd"}


class Problems:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, skill, message):
        self.errors.append(f"{skill}: {message}")

    def warn(self, skill, message):
        self.warnings.append(f"{skill}: {message}")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def frontmatter(text):
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.S)
    if not match:
        return None
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def slug(name):
    return re.sub(r"[^a-z0-9._-]+", "-", str(name or "").strip().lower()).strip("-.")


def string_list(value):
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    out = []
    for item in value:
        if isinstance(item, dict):  # e.g. "- optional: file_send (chat)"
            out.extend(f"{k}: {v}" for k, v in item.items())
        elif str(item).strip():
            out.append(str(item).strip())
    return out


def read_files(skill_id, folder, problems):
    """Every regular file in the folder, with its sha256. Text only; no symlinks."""
    files = {}
    total = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        for dirname in dirnames:
            if os.path.islink(os.path.join(dirpath, dirname)):
                problems.error(skill_id, f"symlinks are not allowed ({dirname})")
        for filename in sorted(filenames):
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, folder).replace(os.sep, "/")
            if os.path.islink(full):
                problems.error(skill_id, f"symlinks are not allowed ({rel})")
                continue
            if not SAFE_PATH_RE.match(rel) or ".." in rel.split("/") or rel.startswith("."):
                problems.error(skill_id, f"unsafe or hidden file name: {rel}")
                continue
            with open(full, "rb") as handle:
                data = handle.read()
            if len(data) > MAX_FILE_BYTES:
                problems.error(skill_id, f"{rel} is larger than {MAX_FILE_BYTES // 1024} KiB")
                continue
            if b"\x00" in data:
                problems.error(skill_id, f"{rel} is binary; only text files are accepted")
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                problems.error(skill_id, f"{rel} is not UTF-8 text")
                continue
            total += len(data)
            files[rel] = (hashlib.sha256(data).hexdigest(), text)
    if len(files) > MAX_SKILL_FILES:
        problems.error(skill_id, f"has {len(files)} files; the limit is {MAX_SKILL_FILES}")
    if total > MAX_SKILL_BYTES:
        problems.error(skill_id, f"is {total} bytes; the limit is {MAX_SKILL_BYTES}")
    return files, total


def scan(skill_id, files, problems):
    for rel, (_, text) in files.items():
        for pattern, note in BLOCKED:
            if pattern.search(text):
                problems.error(skill_id, f"{rel} {note}")
        for pattern, note in WARNINGS:
            if pattern.search(text):
                problems.warn(skill_id, f"{rel} {note}")
        if os.path.splitext(rel)[1].lower() in SCRIPT_EXTENSIONS:
            problems.warn(skill_id, f"ships a script the agent may run: {rel}")


def build_entry(skill_id, problems):
    folder = os.path.join(ROOT, SKILLS_DIR, skill_id)
    if not ID_RE.match(skill_id):
        problems.error(skill_id, "folder name must be lowercase letters, digits, '.', '_' or '-'")
        return None
    meta_path = os.path.join(folder, "skill.yaml")
    skill_md_path = os.path.join(folder, "SKILL.md")
    if not os.path.isfile(meta_path):
        problems.error(skill_id, "missing skill.yaml")
        return None
    if not os.path.isfile(skill_md_path):
        problems.error(skill_id, "missing SKILL.md")
        return None

    with open(meta_path, encoding="utf-8") as handle:
        try:
            meta = yaml.safe_load(handle) or {}
        except yaml.YAMLError as err:
            problems.error(skill_id, f"skill.yaml is not valid YAML: {err}")
            return None
    if not isinstance(meta, dict):
        problems.error(skill_id, "skill.yaml must be a mapping")
        return None
    unknown = set(meta) - {"version", "description", "author", "license", "homepage", "tags"}
    if unknown:
        problems.error(skill_id, f"skill.yaml has unknown keys: {', '.join(sorted(unknown))}")

    with open(skill_md_path, encoding="utf-8", errors="replace") as handle:
        fm = frontmatter(handle.read())
    if fm is None:
        problems.error(skill_id, "SKILL.md needs YAML frontmatter with name and description")
        return None
    if slug(fm.get("name")) != skill_id:
        problems.error(skill_id, f"SKILL.md name '{fm.get('name')}' must match the folder name")

    version = str(meta.get("version", "")).strip()
    if not SEMVER_RE.match(version):
        problems.error(skill_id, "skill.yaml version must be semver, e.g. 1.0.0")
    description = str(meta.get("description") or fm.get("description") or "").strip()
    if not description:
        problems.error(skill_id, "needs a description")
    elif len(description) > MAX_DESCRIPTION:
        problems.error(skill_id, f"description is longer than {MAX_DESCRIPTION} characters")
    for key in ("author", "license"):
        if not str(meta.get(key, "")).strip():
            problems.error(skill_id, f"skill.yaml needs {key}")
    homepage = str(meta.get("homepage", "") or "").strip()
    if homepage and not homepage.startswith("https://"):
        problems.error(skill_id, "homepage must be an https link")
    tags = string_list(meta.get("tags"))
    if tags is None or len(tags) > MAX_TAGS or any(not ID_RE.match(tag) for tag in tags or []):
        problems.error(skill_id, f"tags must be a list of up to {MAX_TAGS} lowercase words")
        tags = []
    requirements = string_list(fm.get("requirements")) or []
    auth_profiles = string_list(fm.get("auth_profiles")) or []

    files, total = read_files(skill_id, folder, problems)
    scan(skill_id, files, problems)

    try:
        commit = git("log", "-1", "--format=%H", "--", f"{SKILLS_DIR}/{skill_id}")
    except subprocess.CalledProcessError:
        commit = ""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        problems.warn(skill_id, "not committed yet; commit is empty until it is")
        commit = ""

    return {
        "id": skill_id,
        "name": str(fm.get("name")).strip(),
        "version": version,
        "description": description,
        "author": str(meta.get("author", "")).strip(),
        "license": str(meta.get("license", "")).strip(),
        **({"homepage": homepage} if homepage else {}),
        **({"tags": tags} if tags else {}),
        **({"requirements": requirements} if requirements else {}),
        **({"auth_profiles": auth_profiles} if auth_profiles else {}),
        "path": f"{SKILLS_DIR}/{skill_id}",
        "commit": commit,
        "files": {rel: sha for rel, (sha, _) in sorted(files.items())},
        "total_bytes": total,
    }


def check_version_bumps(base, entries, problems):
    """A changed skill must change its version, so installed copies see the update."""
    try:
        changed = git("diff", "--name-only", f"{base}...HEAD", "--", SKILLS_DIR).splitlines()
    except subprocess.CalledProcessError as err:
        problems.warn("(repo)", f"could not diff against {base}: {err.stderr.strip()}")
        return
    changed_ids = {path.split("/")[1] for path in changed if path.count("/") >= 2}
    for entry in entries:
        if entry["id"] not in changed_ids:
            continue
        try:
            old = yaml.safe_load(git("show", f"{base}:{SKILLS_DIR}/{entry['id']}/skill.yaml")) or {}
        except subprocess.CalledProcessError:
            continue  # a new skill
        if str(old.get("version", "")).strip() == entry["version"]:
            problems.error(entry["id"], f"files changed but version is still {entry['version']}; bump it")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="validate only; do not write index.json")
    parser.add_argument("--base", help="git ref to compare against for version bumps")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO))
    args = parser.parse_args()

    problems = Problems()
    skills_root = os.path.join(ROOT, SKILLS_DIR)
    entries = []
    for skill_id in sorted(os.listdir(skills_root)):
        if os.path.isdir(os.path.join(skills_root, skill_id)):
            entry = build_entry(skill_id, problems)
            if entry:
                entries.append(entry)
    if args.base:
        check_version_bumps(args.base, entries, problems)
    entries.sort(key=lambda e: e["name"].lower())

    for warning in problems.warnings:
        print(f"::warning::{warning}")
    for error in problems.errors:
        print(f"::error::{error}")
    if problems.errors:
        print(f"{len(problems.errors)} problem(s); index.json not written.", file=sys.stderr)
        return 1
    print(f"{len(entries)} skill(s) valid.")
    if args.check:
        return 0

    index = {"version": 1, "repo": args.repo, "generated_at": "", "skills": entries}
    # Only touch generated_at when the skills changed, so rebuilding is a no-op otherwise.
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, encoding="utf-8") as handle:
            try:
                previous = json.load(handle)
            except json.JSONDecodeError:
                previous = {}
        if {**previous, "generated_at": ""} == index:
            print("index.json is up to date.")
            return 0
    index["generated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(INDEX_PATH, "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("index.json written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
