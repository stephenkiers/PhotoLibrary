#!/usr/bin/env python3
"""Push issues.json to GitHub Issues: Program epic -> 10 milestone epics -> individual issues,
wired with native sub-issue and blocked-by relationships. Idempotent: safe to re-run after an
interruption -- everything already created is looked up from the local map file (falling back
to a title search) and skipped.

Usage:
  python3 scripts/push_issues_to_github.py [--dry-run] [issues.json path]

Never starts any project work itself -- it only creates tracking issues on GitHub.
"""

import json
import os
import subprocess
import sys

MAP_PATH = os.path.join(os.path.dirname(__file__), "..", ".github-issue-map.json")
LABEL_COLOR = "6f42c1"  # any custom label not already on the repo gets this color


def run(*args, input_text=None):
    r = subprocess.run(args, capture_output=True, text=True, input=input_text)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(args)}\n{r.stderr}")
    return r.stdout.strip()


def run_json(*args):
    return json.loads(run(*args))


def load_map():
    if os.path.exists(MAP_PATH):
        return json.load(open(MAP_PATH))
    return {}


def save_map(m):
    json.dump(m, open(MAP_PATH, "w"), indent=2)


def node_id(repo, number):
    q = """
    query($o:String!,$r:String!,$n:Int!){
      repository(owner:$o,name:$r){ issue(number:$n){ id } }
    }"""
    owner, name = repo.split("/")
    out = run_json(
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={q}",
        "-f",
        f"o={owner}",
        "-f",
        f"r={name}",
        "-F",
        f"n={number}",
    )
    return out["data"]["repository"]["issue"]["id"]


def add_sub_issue(dry_run, parent_id, child_id):
    if dry_run:
        return
    m = "mutation($p:ID!,$c:ID!){ addSubIssue(input:{issueId:$p,subIssueId:$c}){ issue{ id } } }"
    run("gh", "api", "graphql", "-f", f"query={m}", "-f", f"p={parent_id}", "-f", f"c={child_id}")


def add_blocked_by(dry_run, blocked_id, blocking_id):
    if dry_run:
        return
    m = "mutation($i:ID!,$b:ID!){ addBlockedBy(input:{issueId:$i,blockingIssueId:$b}){ issue{ id } } }"
    run(
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={m}",
        "-f",
        f"i={blocked_id}",
        "-f",
        f"b={blocking_id}",
    )


def find_existing_by_title(repo, title):
    out = run(
        "gh",
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "all",
        "--search",
        f'in:title "{title}"',
        "--json",
        "number,title",
    )
    for row in json.loads(out):
        if row["title"] == title:
            return row["number"]
    return None


def ensure_labels(repo, labels, dry_run):
    existing = {
        row["name"] for row in run_json("gh", "label", "list", "--repo", repo, "--json", "name")
    }
    for label in sorted(labels - existing):
        print(f"  + label {label}")
        if not dry_run:
            run("gh", "label", "create", label, "--repo", repo, "--color", LABEL_COLOR, "--force")


def ensure_milestones(repo, milestone_map, dry_run):
    existing = {
        row["title"]
        for row in run_json(
            "gh", "api", f"repos/{repo}/milestones", "--paginate", "-X", "GET", "-f", "state=all"
        )
    }
    titles = {}
    for key, name in milestone_map.items():
        title = f"{key}: {name}"
        titles[key] = title
        if title in existing:
            continue
        print(f"  + milestone {title}")
        if dry_run:
            continue
        run("gh", "api", f"repos/{repo}/milestones", "-f", f"title={title}", "-f", "state=open")
    return titles


def create_issue(repo, title, body, labels, milestone_title, dry_run, gmap, map_key):
    if map_key in gmap:
        return gmap[map_key], False
    existing = find_existing_by_title(repo, title)
    if existing:
        gmap[map_key] = existing
        save_map(gmap)
        return existing, False
    print(f"  + issue {map_key}: {title}", flush=True)
    if dry_run:
        return None, True
    args = ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body]
    for label in labels:
        args += ["--label", label]
    if milestone_title is not None:
        args += ["--milestone", milestone_title]
    url = run(*args)
    number = int(url.rstrip("/").rsplit("/", 1)[-1])
    gmap[map_key] = number
    save_map(gmap)
    return number, True


def issue_body(issue):
    lines = []
    if issue["description"]:
        lines.append(issue["description"])
        lines.append("")
    if issue["acceptance_criteria"]:
        lines.append("**Acceptance criteria**")
        for ac in issue["acceptance_criteria"]:
            lines.append(f"- [ ] {ac}")
        lines.append("")
    if issue["notes"]:
        lines.append(f"**Notes:** {issue['notes']}")
        lines.append("")
    lines.append(f"Estimate: {issue['estimate']}")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    path = args[0] if args else "issues.json"
    data = json.load(open(path))
    repo = run("gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    print(f"repo: {repo}  dry_run={dry_run}")

    gmap = load_map()

    all_labels = {l for i in data["issues"] for l in i["labels"]} | {
        "epic",
        "decision",
        "data-safety",
    }
    print("Ensuring labels...")
    ensure_labels(repo, all_labels, dry_run)

    print("Ensuring milestones...")
    milestone_titles = ensure_milestones(repo, data["meta"]["milestones"], dry_run)

    print("Creating Program epic...")
    program_body = (
        "Photo library consolidation program epic. Sub-issues are the 10 milestone epics "
        "(M0 Foundations through M9 Open source); each milestone epic contains the individual, "
        "independently-shippable issues for that milestone. Dependencies between issues are "
        "wired as native GitHub blocked-by relationships -- an issue with no open blockers is "
        "safe to pick up in parallel with any other unblocked issue.\n\n"
        "Data safety is a hard constraint throughout: nothing that deletes or moves an original "
        "photo/video runs unattended. See issues labeled `data-safety`."
    )
    program_number, _ = create_issue(
        repo, "Photo Vault: Program", program_body, ["epic"], None, dry_run, gmap, "program"
    )
    program_id = node_id(repo, program_number) if (not dry_run and program_number) else None

    milestone_issue_ids = {}
    for key, name in data["meta"]["milestones"].items():
        title = f"{key}: {name} (epic)"
        body = f"Milestone epic for {key} ({name}). Sub-issues are the individual work items in this milestone."
        number, created = create_issue(
            repo, title, body, ["epic"], milestone_titles.get(key), dry_run, gmap, f"epic:{key}"
        )
        milestone_issue_ids[key] = number
        if program_id and number and not dry_run:
            add_sub_issue(dry_run, program_id, node_id(repo, number))

    print("Creating individual issues...")
    number_by_id = {}
    for issue in data["issues"]:
        title = issue["title"]
        body = issue_body(issue)
        number, created = create_issue(
            repo,
            title,
            body,
            issue["labels"],
            milestone_titles.get(issue["milestone"]),
            dry_run,
            gmap,
            issue["id"],
        )
        number_by_id[issue["id"]] = number
        parent_epic_number = milestone_issue_ids.get(issue["milestone"])
        if not dry_run and number and parent_epic_number:
            add_sub_issue(dry_run, node_id(repo, parent_epic_number), node_id(repo, number))

    print("Wiring blocked-by dependencies...")
    for issue in data["issues"]:
        blocked_number = number_by_id.get(issue["id"])
        if not blocked_number or dry_run:
            continue
        for dep in issue["depends_on"]:
            blocking_number = number_by_id.get(dep)
            if not blocking_number:
                continue
            add_blocked_by(dry_run, node_id(repo, blocked_number), node_id(repo, blocking_number))

    print("Closing already-answered decision issues (labeled 'answered')...")
    for issue in data["issues"]:
        if "answered" in issue["labels"]:
            number = number_by_id.get(issue["id"])
            if number and not dry_run:
                run(
                    "gh",
                    "issue",
                    "close",
                    str(number),
                    "--repo",
                    repo,
                    "-c",
                    "Answered; captured in this issue's body. PLAN.md retired.",
                )

    if not dry_run:
        save_map(gmap)
    print("Done.")


if __name__ == "__main__":
    main()
