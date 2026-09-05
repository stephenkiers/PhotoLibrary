#!/usr/bin/env python3
"""Generate issues.json for the photo vault project. Validates dependency DAG and prints a topological build order."""
import json, sys, datetime
from collections import defaultdict, deque

ISSUES = []
def I(id, title, milestone, deps=(), labels=(), est="M", body="", ac=(), notes=""):
    ISSUES.append(dict(id=id, title=title, milestone=milestone, depends_on=list(deps), labels=list(labels),
                       estimate=est, description=body.strip(), acceptance_criteria=list(ac), notes=notes.strip()))

# ---------------- M0 Foundations ----------------
I("M0-01","Blocking questions Q1-Q7 answered 2026-09-04 (Shared Library scope, edited-render handling, NAS volume1 assumption, Mar-2025 backup treated as full source, dedup definition, proxy targets, staging/compute host)","M0",[],["decision","answered"],"S",
  "Q1 Shared Library: tooling supports both Personal and Shared Library assets, but every batch "
  "-- especially deletions -- is manually triggered and reviewed; no unattended runs against "
  "Photos, ever. Q2 Edited renders: proxy the edited version, not the un-edited original; edit "
  "history/Memories still don't survive osxphotos/Photos, accepted. Q3 NAS volume1 (9.7 TiB "
  "used, Immich empty): assumed to be prior photo backups, not yet verified -- process "
  "NAS-resident material before the live Photos library (see M1-00). Q4 March 2025 backup "
  "library: treated as a full-originals bulk source without further verification. Q5 Duplicate "
  "definition: auto-drop only exact + strictly-worse copies; bursts/near-dupes stay in the "
  "archive for manual review. Q6 Proxy targets: 1920px HEIC / 1080p HEVC, aiming for the 200GB "
  "iCloud tier. Q7 Staging/compute: the Intel i9 Mac (Radeon Pro 550M) does all compute with a "
  "4TB local staging disk; the NAS is storage-only (source read + Immich archive write); the "
  "M3 Max is reserved for day-to-day work.",
  ["Closed on creation -- answers captured here for reference now that PLAN.md is retired"])
I("M0-02","Rotate leaked Immich API key and DB password; scrub old repos","M0",[],["security"],"S",
  "API key and DB password are committed in the Immich, ImmichImportManager and NasPhotoOptimizationProject repos.",
  ["New key issued in Immich, old key revoked","No secret strings remain in any tracked file (gitleaks passes)"])
I("M0-03","Procure/attach staging storage on the Intel i9 Mac and second/third backup drives","M0",["M0-01"],["hardware"],"S",
  "Compute and staging move to the Intel i9 Mac, not the M3 Max (busy with day-to-day work) or "
  "the NAS (too slow). Need 4 TB attached/local to the Intel Mac for staging/working set, plus "
  "at least two backup destinations (USB drive kept offline, and either a second NAS or cloud "
  "bucket).",
  ["4TB staging disk mounted on the Intel Mac and benchmarked (>500 MB/s)","Two backup targets identified and reachable"])
I("M0-04","Bootstrap repo: uv project, typer CLI skeleton, ruff, mypy, pytest, pre-commit","M0",[],["infra"],"S","",
  ["`uv run vault --help` lists all planned subcommands as stubs","CI runs lint, type check, tests on push"])
I("M0-05","Config schema and loader (single vault.toml + env overrides)","M0",["M0-04"],["core"],"S",
  "Paths (archive, journal, catalog, proxies, staging), sources list, thresholds, proxy params, publish policy (grace days, shared-library policy), backup targets. No secrets in file; secrets via env or keychain.",
  ["Invalid config fails fast with a clear message","Example config committed as vault.example.toml"])
I("M0-06","Hashing module: BLAKE3 full hash, xxh3 prehash, chunked verify","M0",["M0-04"],["core"],"S","",
  ["Hash 1 GB file in <2 s on the Intel i9 Mac","Property test: hash(bytes) stable, verify() detects single-bit flip"])
I("M0-07","Content-addressed store: put (temp+rename), get path, exists, verify, iterate","M0",["M0-06","M0-05","M0-14"],["core","data-safety"],"M",
  "Layout archive/objects/aa/bb/<hash>.<ext>. put() rehashes after copy and refuses to overwrite a differing object. Preserve mtime in sidecar metadata, not on the object.",
  ["put is idempotent and atomic (kill -9 mid-copy leaves no partial object)","verify(hash) rehashes and reports mismatch","Works on SMB and local APFS/ext4"])
I("M0-08","Append-only journal (jsonl, hash-chained, typed events)","M0",["M0-05"],["core"],"M",
  "Event types: object_stored, source_seen, decision, publish, retire, backup_verified. Each line carries prev-line hash. Multiple writers (Mac + NAS) write to separate files merged by timestamp.",
  ["Corrupted or truncated line detected on read","Merge of two writer files is deterministic"])
I("M0-09","Catalog: SQLite schema, migrations, rebuild-from-journal","M0",["M0-08","M0-07"],["core"],"L",
  "Tables: objects, sources, source_files, fingerprints(object,algo,version,value), groups, group_members, decisions, publishes, backups. WAL mode. `vault rebuild` recreates it from archive + journal.",
  ["rebuild on a fixture vault equals the incrementally built catalog (byte-for-byte dump)","Migrations are forward-only and tested"])
I("M0-10","Test fixture vault: ~200 synthetic and real assets covering every edge case","M0",["M0-04"],["testing"],"M",
  "HEIC, JPEG, PNG, DNG+JPEG pair, Live Photo pair, burst of 12, resized/re-encoded copies, rotated copy, video MOV/MP4 with GPS, 0-byte file, non-media file, unicode filenames, same file twice.",
  ["Fixture generator is deterministic (seeded)","Documented expected groups and winners"])
I("M0-11","Docker image for NAS (linux/amd64) with exiftool, vips, ffmpeg","M0",["M0-04"],["infra"],"S","",
  ["`docker run vault status` works against a mounted archive on the ASUSTOR"])
I("M0-12","Decide: loose-folder triage (bips-go-yup 136GB, recovery/, Del, DelEA, DJI Bak) -- source vs junk","M0",[],["decision"],"S",
  "PLAN.md Q8. Which of these loose folders are real sources to ingest and which are junk/recovery-dump noise to skip.",
  ["Written decision per folder, referenced by M8-02"])
I("M0-13","Decide: RAW+JPEG pair handling -- keep RAW as archive winner, proxy the embedded JPEG?","M0",[],["decision"],"S",
  "PLAN.md Q9. Confirms the winner-rule tie-break (RAW > HEIC > JPEG) actually matches what should go back into Photos as the proxy.",
  ["Written decision, referenced by M3-01"])
I("M0-14","Decide: Immich managed-upload tree as the only archive, or also a flat originals tree outside Immich?","M0",[],["decision"],"S",
  "PLAN.md Q10. Affects the content-addressed store's relationship to Immich's own `library/<user>/yyyy/MM/` layout.",
  ["Written decision, referenced by M0-07"])
I("M0-15","Decide: second copy of the archive -- second NAS, Backblaze B2, or rotating USB?","M0",[],["decision"],"S",
  "PLAN.md Q11. RAID 1 on the NAS is not a backup; this must be settled before Phase 7/M8-06 deletes anything from Photos.",
  ["Written decision, referenced by M6-01"])
I("M0-16","Decide: future ingest path -- keep iPhone to iCloud to Photos loop, or move phone backup to the Immich app?","M0",[],["decision"],"S",
  "PLAN.md Q12. Determines whether M7-05's family/steady-state upload path needs the full Photos-delta loop or can shift to Immich mobile backup.",
  ["Written decision, referenced by M7-05"])
I("M0-17","Decide: export hidden, Recently Deleted, and syndicated (Messages) assets, or skip them?","M0",[],["decision"],"S",
  "PLAN.md Q13. Scopes what M1-04's Photos-library ingest actually pulls.",
  ["Written decision, referenced by M1-04"])
I("M0-18","Decide: timeline and downtime tolerance -- OK with Photos in a mixed proxy/original state for weeks?","M0",[],["decision"],"S",
  "PLAN.md Q14. Affects how M8-06's year-by-year publish/retire schedule is paced.",
  ["Written decision, referenced by M8-06"])
I("M0-19","Decide: where should Immich ML (faces, CLIP embeddings) run -- NAS only, or a temporary Mac container for the initial backlog?","M0",[],["decision"],"S",
  "PLAN.md Q15. Ops/config decision for the Immich deployment; doesn't gate any vault build issue.",
  ["Written decision, recorded in docs/decisions.md"])
I("M0-20","Decide: fuzzy-match risk tolerance -- auto-drop losers in clean clusters, or review every near-duplicate cluster by eye?","M0",[],["decision"],"S",
  "PLAN.md Q16. At 200k+ assets, full manual review of every cluster is not realistic; sets the calibration target for M2-10.",
  ["Written decision, referenced by M2-10"])

# ---------------- M1 Ingest ----------------
I("M1-00","Ingest and dedupe NAS-resident material not in any Photos library, before the live Photos library export starts","M1",["M1-06","M0-01"],["ingest","nas","data-safety"],"M",
  "Q3/Q7 (2026-09-04): NAS volume1 has 9.7 TiB used with Immich holding 0 assets, assumed to be "
  "prior photo/video backups (e.g. FastTransfer/PhotoBackupProject). Run ingest -> fingerprint "
  "-> group -> select -> publish-to-Immich for this NAS-resident content on its own, while the "
  "live Photos app stays running and untouched, before M1-04 begins. Confirms the volume1 "
  "assumption with real numbers before committing to the rest of the plan's storage estimates.",
  ["NAS volume1 content inventoried and classified as source vs. reclaimable space",
   "Immich holds the deduped NAS-resident content before M1-04 (live Photos export) starts",
   "No changes made to the live Photos app or library during this phase"])
I("M1-01","Source plugin interface: enumerate(), fetch(item)->local path, metadata(item)","M1",["M0-09"],["ingest"],"S","",
  ["Interface documented; folder source implements it"])
I("M1-02","Folder source (recursive, extension allowlist, sidecar discovery XMP/AAE/JSON)","M1",["M1-01"],["ingest"],"M","",
  ["Sidecars linked to their media by stem","Ignores junk (.DS_Store, thumbs, AppleDouble ._ files)"])
I("M1-03","Ingest command: enumerate -> prehash -> full hash -> store -> journal, resumable","M1",["M1-02","M0-07","M0-08"],["ingest"],"L",
  "Skip already-seen (source,path,size,mtime). Parallel hashing bounded by IO. Progress bar and summary. --dry-run.",
  ["Re-running ingest on unchanged source reports 0 new objects","Kill and resume loses no work","1 TB from USB ingests without manual intervention"])
I("M1-04","Apple Photos source via osxphotos (originals + edited + AAE + XMP + JSON metadata)","M1",["M1-01","M1-00","M0-17"],["ingest","mac"],"L",
  "Wrap `osxphotos export --update --sidecar xmp --sidecar json --export-aae` into a staging dir. Exports only assets already present on disk by default; `--fetch-icloud` opt-in adds `--download-missing` in small date-range batches. Capture Photos UUID, albums, keywords, favorite, hidden, persons, shared-library flag, burst UUID, live photo pair.",
  ["Photos UUID -> object hash mapping stored in journal","Not-downloaded assets are listed in a report, never treated as errors","Optional iCloud fetch batches by date range and respects a free-disk floor"])
I("M1-05","Optional iCloud fetch mode: batch download of not-yet-local originals (low priority)","M1",["M1-04"],["ingest","mac","optional"],"M",
  "Only needed for assets that exist nowhere locally after all other sources are ingested. Investigate whether downloaded originals stay in the library and fill the disk; choose batch size and eviction approach accordingly.",
  ["Runs unattended in small batches without exhausting the boot disk","Can be paused and resumed; no other stage depends on it"])
I("M1-06","Drop-folder source for the NAS (SMB share, quarantine until stable size, then ingest)","M1",["M1-02"],["ingest","nas","data-safety"],"M","",
  ["File still being written is not ingested","Ingested files moved to processed/ with date subfolders"])
I("M1-07","Immich source (optional): pull originals via API for assets not yet in the vault","M1",["M1-01"],["ingest","immich","optional"],"M","",
  ["Immich asset id -> object hash recorded"])
I("M1-08","Pilot ingest: 5k assets from the loose folders + 1k from the live Photos library","M1",["M1-03","M1-04"],["pilot"],"S","",
  ["Counts reconciled against source","Report of any unreadable files"])

# ---------------- M2 Fingerprint & group ----------------
I("M2-01","EXIF/QuickTime extraction with exiftool batch mode","M2",["M0-09"],["fingerprint"],"M",
  "Dates (with timezone), GPS, dims, orientation, camera, BurstUUID, MediaGroupUUID, ContentIdentifier, ImageUniqueID, MakerNote fields, codec, duration, ICC. Store raw JSON plus normalized columns.",
  ["10k files/min throughput","Unparseable file recorded, not fatal"])
I("M2-02","Image perceptual fingerprints (pHash, dHash, blockhash) via vips downscale + sharpness score","M2",["M2-01"],["fingerprint"],"M",
  "Decode once at 1024 px, compute hashes, compute Laplacian variance for sharpness. Versioned algorithm id. HEIC and RAW via embedded preview.",
  ["Rotated copy is matched (compute hashes for 4 rotations or use rotation-invariant variant)","Resized copy within Hamming <=4 on 256-bit pHash"])
I("M2-03","Video fingerprints (frame pHashes at 10/50/90 percent, duration, resolution, bitrate)","M2",["M2-01"],["fingerprint"],"M","",
  ["1080p re-encode of same video matches original","Different videos do not match"])
I("M2-04","Fingerprint command: parallel, resumable, versioned, skips done work","M2",["M2-02","M2-03"],["fingerprint"],"M","",
  ["Second run with no new objects does zero work"])
I("M2-05","Exact groups (same hash seen from multiple sources)","M2",["M2-04"],["group"],"S","",
  ["Group lists all source paths for the object"])
I("M2-06","Near groups via BK-tree over pHash with date/dims sanity checks","M2",["M2-04"],["group"],"L",
  "Threshold configurable; default tight (<=2 bits on 64-bit dHash AND <=6 on 256-bit pHash). Reject if capture dates differ by more than a day when both known. Emit confidence score.",
  ["Fixture near-dupes grouped; fixture distinct images not grouped","230k images cluster in <30 min on the Intel i9 Mac"])
I("M2-07","Pair groups: RAW+JPEG, Live Photo still+video, edited+original from Photos","M2",["M2-04"],["group"],"M","",
  ["Live pair via ContentIdentifier; RAW+JPEG via stem+date; edited via Photos UUID"])
I("M2-08","Sequence groups: BurstUUID, plus time window (<=3 s) with high similarity","M2",["M2-06","M2-07"],["group"],"M","",
  ["Fixture burst of 12 becomes one sequence","Two different scenes 2 s apart are not merged"])
I("M2-09","Group command produces deterministic group ids (hash of sorted member hashes)","M2",["M2-05","M2-06","M2-07","M2-08"],["group"],"S","",
  ["Re-running group yields identical ids"])
I("M2-10","Similarity threshold calibration on a labelled sample of 500 clusters","M2",["M2-09","M1-08","M0-20"],["group","research"],"M","",
  ["Precision >=0.99 on near groups at chosen threshold","Thresholds written into config defaults with rationale"])

# ---------------- M3 Select & proxy ----------------
I("M3-01","Winner rule for near groups (pixels > RAW>HEIC>JPEG > size > metadata > earliest)","M3",["M2-09","M0-13"],["select"],"S","",
  ["Pure function with table-driven tests","Edited render never beats its original unless original missing"])
I("M3-02","Representative rule for sequences (winner of sharpest frame; faces-open heuristic optional)","M3",["M3-01"],["select"],"M","",
  ["Deterministic; ties broken by earliest capture time"])
I("M3-03","Decision model: human decisions override rules; effective_state view","M3",["M3-01","M0-08"],["select"],"M",
  "Decisions: keep, trim, set_representative, merge_groups, split_group, undo. Stored in journal; catalog view computes effective published set.",
  ["Undo restores prior effective state","Rebuild reproduces effective state"])
I("M3-04","Image proxy generator (vips): configurable long edge and HEIC/JPEG quality; two profiles: review (720px) and publish (1920px)","M3",["M2-01"],["proxy"],"M","",
  ["Derived cache keyed by (hash, profile version)","10k images/hour on the Intel i9 Mac","Orientation and ICC preserved"])
I("M3-05","Metadata copy into proxies (exiftool -tagsFromFile, all EXIF/GPS/XMP, ContentIdentifier)","M3",["M3-04"],["proxy"],"S","",
  ["Proxy imported into a scratch Photos library shows correct date, GPS, keywords"])
I("M3-06","Video proxy generator (ffmpeg): 1080p HEVC, VideoToolbox on Mac, libx265 fallback; .mov; metadata preserved","M3",["M2-01"],["proxy"],"M","",
  ["Creation date and GPS visible in Photos after import","Throughput measured and documented"])
I("M3-07","Live Photo proxy pairing (still + video share ContentIdentifier after proxying)","M3",["M3-05","M3-06"],["proxy"],"S","",
  ["Imported pair shows as Live Photo in Photos"])
I("M3-08","Proxy command: parallel, resumable, only for objects that need it (winners/reps)","M3",["M3-04","M3-06","M3-03"],["proxy"],"S","",
  ["No-op on second run"])
I("M3-09","Publish-set calculation and size report (estimate iCloud footprint)","M3",["M3-03","M3-08"],["select"],"S","",
  ["Reports total proxy bytes vs original bytes per year"])

# ---------------- M4 Review UI ----------------
I("M4-01","Review server (FastAPI + htmx) reading catalog and proxies, local only","M4",["M3-09"],["ui"],"M","",
  ["Starts with `vault review`, opens browser, no external network"])
I("M4-02","Timeline view: infinite scroll by day using review proxies, fast on 230k items","M4",["M4-01"],["ui"],"L","",
  ["Scroll stays under 100 ms/frame with virtualization"])
I("M4-03","Sequence strip view: burst/near members side by side, sharpness badges, choose representative","M4",["M4-02"],["ui"],"M","",
  ["One click sets representative and writes decision"])
I("M4-04","Keep/trim actions with keyboard shortcuts, batch select, undo","M4",["M4-03","M3-03"],["ui"],"M","",
  ["Every action is a journal line; undo works across restarts"])
I("M4-05","Filters: year, source, group type, undecided-only, sequences with >N members","M4",["M4-02"],["ui"],"S","",[])
I("M4-06","Compare view for near-group winners (side-by-side with zoom, dims, size, source)","M4",["M4-03"],["ui"],"S","",[])
I("M4-07","Contact-sheet HTML export as a no-server fallback for review","M4",["M3-09"],["ui","optional"],"S","",[])

# ---------------- M5 Publish to Photos ----------------
I("M5-01","Publish target interface and Photos target via osxphotos import (album, keywords, title, description, location, favorite)","M5",["M3-09"],["publish","mac"],"L","",
  ["Imported asset UUID captured and journaled","--skip-dups prevents double import"])
I("M5-02","Verify step: confirm proxy present in Photos by UUID and metadata matches","M5",["M5-01"],["publish","mac"],"M","",
  ["Mismatch blocks retire for that asset"])
I("M5-03","Retire step: delete original from Photos by UUID, manually triggered per batch, backup-verified precondition, --yes","M5",["M5-02","M6-04"],["publish","mac","destructive","data-safety"],"M",
  "Q1 (2026-09-04): no automated or scheduled deletion, ever. Every retire batch is triggered "
  "by an explicit human command and reviewed before running -- it is never invoked by `vault "
  "sync`, launchd, or any unattended job. Enforce this at runtime, not just by documentation.",
  ["Refuses if object not in >=1 verified backup",
   "Refuses for Shared Library assets unless policy allows",
   "Dry run lists exact UUIDs and a second explicit confirmation flag is required to actually delete",
   "Cannot be invoked from `vault sync` or any scheduled/launchd job -- enforced by a runtime check"])
I("M5-04","Shared Library policy and contributor detection (track osxphotos issue 860)","M5",["M0-01","M1-04"],["publish","risk"],"M","",
  ["Policy documented; assets of other contributors never retired without explicit config"])
I("M5-05","Album and favorites round-trip mapping (Photos albums -> proxies in same albums)","M5",["M5-01"],["publish"],"M","",[ "Albums recreated with same names; favorites set"])
I("M5-06","Pilot: 500 assets round trip into a scratch Photos library, then 500 into the real one","M5",["M5-02","M5-05","M3-07"],["pilot","mac"],"M","",
  ["Checklist: dates, GPS, albums, keywords, Live Photos, HEIC rendering, faces re-detected","Sign-off recorded in docs/decisions.md"])
I("M5-07","Immich publish target via immich-go (winners, albums, XMP) for viewing","M5",["M3-09"],["publish","immich","optional"],"M","",[ "Winners' checksums found via Immich API after upload"])
I("M5-08","Folder publish target (plain export of winners by yyyy/MM) for non-Immich users","M5",["M3-09"],["publish","optional"],"S","",[])

# ---------------- M6 Backup & verify ----------------
I("M6-01","Backup target interface: rsync-to-disk and restic (B2/second NAS)","M6",["M0-07","M0-08","M0-15"],["backup","data-safety"],"M","",[ "Targets configurable; archive and journal both included"])
I("M6-02","Backup command: incremental, then verify by rehashing a sample and all new objects","M6",["M6-01"],["backup","data-safety"],"M","",[ "Journal event backup_verified per object per target"])
I("M6-03","Scrub command: periodic full rehash of archive and backups, report drift","M6",["M6-02"],["backup","data-safety"],"S","",[ "Monthly scrub of 8 TB completes; report emailed/logged"])
I("M6-04","Restore drill: restore 1k random objects from each target and verify","M6",["M6-02"],["backup","data-safety"],"S","",[ "Documented runbook; drill passes"])
I("M6-05","Offline drive rotation procedure (two USB drives alternating, one off-site)","M6",["M6-02","M0-03"],["backup","ops","data-safety"],"S","",[ "Runbook in docs/backups.md"])

# ---------------- M7 Automation ----------------
I("M7-01","`vault sync` orchestrator: ingest -> fingerprint -> group -> select -> proxy -> publish(import) -> backup, with lock file","M7",["M1-04","M2-09","M3-08","M5-01","M6-02"],["automation"],"M",
  "Never invokes retire (M5-03). Retire is a separate, always-manual command -- vault sync's job "
  "ends at importing proxies into Photos.",
  ["Single command idempotent; concurrent run refused","Retire (M5-03) is unreachable from this command, enforced by a runtime check not just omission"])
I("M7-02","Intel Mac launchd job for nightly sync (ingest through publish/import only, never retire) with disk-space and power preconditions","M7",["M7-01"],["automation","mac"],"S","",[])
I("M7-03","NAS container schedule: hourly drop-folder ingest, nightly backup, monthly scrub","M7",["M0-11","M1-06","M6-03"],["automation","nas"],"S","",[])
I("M7-04","Status, health and notifications (CLI status, JSON report, ntfy/email on failure)","M7",["M7-01"],["automation"],"S","",[])
I("M7-05","Family upload path: drop folder via SMB/PhotoSync, or Immich mobile -> Immich source","M7",["M1-06","M1-07","M0-16"],["automation","family"],"S","",[ "Documented instructions for family members"])
I("M7-06","Catalog concurrency: Mac and NAS both writing (journal per writer, catalog rebuild on conflict)","M7",["M0-09","M7-03"],["automation","core"],"M","",[ "Simulated concurrent writes converge after rebuild"])

# ---------------- M8 Migration ----------------
I("M8-01","Ingest the March-2025 backup Photos library (bulk originals from USB)","M8",["M1-04","M1-08","M0-03"],["migration"],"L","",[ "All assets ingested or listed as unreadable"])
I("M8-02","Ingest loose folders (PhotosBackup, MP600, BergePhotos, NAS FastTransfer)","M8",["M1-03","M0-01","M0-12"],["migration"],"M","",[])
I("M8-03","Ingest the live Photos library: locally present originals only","M8",["M8-01"],["migration","mac"],"M","",[ "Everything downloaded on the Mac is archived; not-downloaded assets listed in a report"])
I("M8-09","Optional last step: fetch remaining iCloud-only originals in background batches","M8",["M8-05","M1-05"],["migration","mac","optional"],"XL",
  "Runs after the archive is backed up. Low priority; can span weeks. Retire in Photos only happens for assets whose original is archived, so this step only widens coverage.",
  [ "Report of assets that still exist only in iCloud trends to zero or is accepted as-is"])
I("M8-04","Full fingerprint + group + select on the whole vault; publish size report","M8",["M8-02","M8-03","M2-10","M3-09"],["migration"],"L","",[])
I("M8-05","First full backup to two targets and verify before any retire","M8",["M8-04","M6-04","M6-05"],["migration","backup","data-safety"],"L","",[])
I("M8-06","Publish proxies to Photos year by year, verify, retire originals, monitor iCloud usage","M8",["M8-05","M5-06","M5-04","M0-18"],["migration","destructive","data-safety"],"XL","",
  ["iCloud usage drops as expected per year","Zero assets in Photos without a matching archive object",
   "Each year's retire batch is manually triggered and reviewed -- never automated (M5-03)"])
I("M8-07","Sequence trimming passes in the review UI (bursts first, then near groups)","M8",["M8-04","M4-04"],["migration","ui"],"L","",[])
I("M8-08","Decommission old projects and staging; keep one archived copy of decisions","M8",["M8-06"],["migration","cleanup"],"S","",[])

# ---------------- M9 Open source ----------------
I("M9-01","Docs: README, quickstart, architecture, safety model, config reference","M9",["M7-01"],["docs"],"M","",[])
I("M9-02","Remove all personal paths/defaults; example configs for Mac-only, NAS-only, both","M9",["M9-01"],["docs"],"S","",[])
I("M9-03","License, contributing guide, issue templates, release workflow (uv build, Docker publish)","M9",["M9-02"],["docs","infra"],"S","",[])
I("M9-04","Immich integration documented as optional plugin; Google Takeout source","M9",["M5-07","M1-07"],["docs","optional"],"M","",[])

# ---------------- validate ----------------
ids = {i["id"] for i in ISSUES}
dups = [i for i in ids if sum(1 for x in ISSUES if x["id"]==i)>1]
assert not dups, dups
for i in ISSUES:
    for d in i["depends_on"]:
        assert d in ids, f"{i['id']} depends on unknown {d}"
indeg = {i["id"]:len(i["depends_on"]) for i in ISSUES}
children = defaultdict(list)
for i in ISSUES:
    for d in i["depends_on"]: children[d].append(i["id"])
q = deque(sorted(k for k,v in indeg.items() if v==0)); order=[]
while q:
    n=q.popleft(); order.append(n)
    for c in sorted(children[n]):
        indeg[c]-=1
        if indeg[c]==0: q.append(c)
assert len(order)==len(ISSUES), "cycle detected"
EST_DAYS={"S":1,"M":3,"L":6,"XL":12}
out = {
  "meta": {"project":"photo vault (working name)","generated":str(datetime.date.today()),
           "generator":"scripts/gen_issues.py","issue_count":len(ISSUES),
           "estimate_days_total": sum(EST_DAYS[i["estimate"]] for i in ISSUES),
           "estimate_scale":EST_DAYS,
           "milestones":{"M0":"Foundations","M1":"Ingest","M2":"Fingerprint and group","M3":"Select and proxy","M4":"Review UI","M5":"Publish to Photos","M6":"Backup and verify","M7":"Automation","M8":"Migration","M9":"Open source"},
           "critical_path_hint":"M0-07 -> M1-03 -> M1-04 -> M2-04 -> M2-09 -> M3-08 -> M3-09 -> M5-01 -> M5-02 -> M6-04 -> M5-03 -> M8-05 -> M8-06 (iCloud fetch M1-05/M8-09 is off the critical path)",
           "topological_order": order},
  "flow": [
    "ingest: local sources first (USB library, folders, NAS, on-disk Photos originals) -> staging -> blake3 -> archive/objects (verified copy) -> journal; iCloud fetch is an optional trailing step",
    "fingerprint: exif + phash/dhash + video frame hashes, versioned, cached per object",
    "group: exact -> near (BK-tree) -> pair (RAW+JPEG, Live) -> sequence (burst/time window)",
    "select: rule-based winner per near group, representative per sequence, overridden by journaled human decisions",
    "proxy: review (720px) and publish (1920px HEIC / 1080p HEVC) with metadata copied",
    "review: local web UI writes decisions to journal",
    "publish: import proxies into Apple Photos, verify by UUID, retire originals after grace + backup-verified",
    "backup: rsync/restic to >=2 targets, verify, scrub, restore drills",
    "sync: one orchestrator command run by launchd (Mac) and a container schedule (NAS)"],
  "issues": ISSUES}
json.dump(out, open(sys.argv[1] if len(sys.argv)>1 else "issues.json","w"), indent=2)
print(f"{len(ISSUES)} issues, {out['meta']['estimate_days_total']} est. days; DAG ok")
by_ms=defaultdict(int)
for i in ISSUES: by_ms[i["milestone"]]+=EST_DAYS[i["estimate"]]
print(dict(sorted(by_ms.items())))
