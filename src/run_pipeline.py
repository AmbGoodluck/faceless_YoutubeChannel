"""
Orchestrator — runs one episode through the pipeline.

Flow (with two human checkpoints, per YouTube's authenticity rules):
  queued
    -> generate script        -> script_ready   [YOU APPROVE the script.txt]
    -> submit to Revid        -> submitted
    -> render finishes        -> rendered        [YOU APPROVE the final video]
    -> publish (manual/auto)  -> posted

By default this runs ONE step at a time and stops at each checkpoint, so nothing
ever publishes without you seeing it. Use --auto to skip the pauses (not advised
until you trust the output).

Usage:
  python src/run_pipeline.py            # advance the next-ready episode by one stage
  python src/run_pipeline.py --script   # only (re)generate the next queued script
  python src/run_pipeline.py --submit ID  # submit an approved script to Revid
"""
import os, sys, csv, argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src import generate_script, revid_client


def read_queue():
    with open(config.QUEUE_FILE, newline="") as f:
        return list(csv.DictReader(f))


def write_queue(rows):
    with open(config.QUEUE_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


def set_status(rows, rid, status):
    for r in rows:
        if r["id"] == rid:
            r["status"] = status
    write_queue(rows)


def next_with_status(rows, status):
    return next((r for r in rows if r["status"] == status), None)


def cmd_script(rows):
    row = next_with_status(rows, "queued")
    if not row:
        print("No queued episodes left. Refill content_queue.csv.")
        return
    generate_script.generate(row)
    set_status(rows, row["id"], "script_ready")
    print(f"\n>>> CHECKPOINT 1: review outputs/{row['id']}-*/script.txt, then run with --submit {row['id']}")


def cmd_submit(rows, rid):
    import json, glob
    path = glob.glob(os.path.join(config.OUTPUT_DIR, f"{rid}-*", "script.json"))
    if not path:
        print(f"No script.json for id {rid}. Run --script first."); return
    with open(path[0]) as f:
        script = json.load(f)
    webhook = os.environ.get("REVID_WEBHOOK_URL")  # optional
    resp = revid_client.create_video(script, webhook)
    set_status(rows, rid, "submitted")
    print(f"\n>>> Submitted. pid={resp.get('pid') or resp}. Webhook/poll will deliver the video.")
    print(f">>> CHECKPOINT 2: when rendered, watch it, then mark posted after publishing.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--script", action="store_true", help="generate next queued script")
    p.add_argument("--submit", metavar="ID", help="submit an approved script id to Revid")
    args = p.parse_args()

    rows = read_queue()
    if args.submit:
        cmd_submit(rows, args.submit)
    else:
        cmd_script(rows)  # default: produce the next script and stop at checkpoint 1


if __name__ == "__main__":
    main()
