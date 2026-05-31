"""SAGE command-line interface.

Examples:
    python -m sage.cli run --docs demo/sample_company --goal "Rebuild our API"
    python -m sage.cli log --db sage_state.db --instance <id>
"""

from __future__ import annotations

import argparse
import sys

from .core.engine import SageEngine
from .core.events import ActivityLog
from .core.resume import reconstruct
from .providers import get_provider


# ANSI colours for a readable live feed.
C = {
    "SAGE-Core": "\033[95m", "Gardener": "\033[92m",
    "dim": "\033[90m", "bold": "\033[1m", "reset": "\033[0m", "agent": "\033[96m",
}


def _color_for(actor: str) -> str:
    if actor.startswith("agent:"):
        return C["agent"]
    return C.get(actor, "")


def _print_event(event) -> None:
    color = _color_for(event.actor)
    flag = "*" if event.checkpoint else "-"
    print(f"{C['dim']}{flag}{C['reset']} {color}{event.actor:<16}{C['reset']} "
          f"{event.summary}", flush=True)


def cmd_run(args: argparse.Namespace) -> int:
    provider = get_provider(args.provider)
    print(f"{C['bold']}SAGE{C['reset']} -- provider: {provider.name}\n")
    engine = SageEngine(provider=provider, db_path=args.db,
                        instance_id=args.instance, on_event=_print_event)
    if args.instance and engine.discovered_roles:
        print(f"{C['dim']}resumed instance {args.instance} "
              f"(remembers: {', '.join(engine.discovered_roles)}){C['reset']}\n")

    if args.docs:
        engine.ingest(args.docs)
    print()
    results = engine.run_cycles(args.goal, cycles=args.cycles)
    result = results[-1]

    print(f"\n{C['bold']}-- Summary --{C['reset']}")
    print(f"instance: {result.instance_id}")
    print(f"methodology: {result.methodology or 'none (from scratch)'}")
    print(f"agents: {len(result.agents)}")
    for a in result.agents:
        print(f"  {C['agent']}{a.role:<14}{C['reset']} "
              f"score={a.score} status={a.status.value}")
    if result.insights.get("insights"):
        print("insights:")
        for i in result.insights["insights"]:
            print(f"  - {i}")
    print(f"\n{C['dim']}Replay this run: "
          f"python -m sage.cli log --db {args.db} --instance {result.instance_id}{C['reset']}")
    engine.close()
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    log = ActivityLog(db_path=args.db)
    events = log.events(args.instance)
    if not events:
        print("No events for that instance.")
        return 1
    for e in events:
        _print_event(e)
    log.close()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    log = ActivityLog(db_path=args.db)
    state = reconstruct(log, args.instance)
    if state.event_count == 0:
        print("No events for that instance.")
        return 1
    print(f"{C['bold']}Reconstructed from the activity log alone:{C['reset']}")
    print(state.describe())
    log.close()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .web.server import serve

    serve(docs=args.docs, goal=args.goal, cycles=args.cycles,
          provider_name=args.provider, db_path=args.db,
          host=args.host, port=args.port)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sage", description="Self-Architecting Genesis Engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="ingest docs and run a goal")
    p_run.add_argument("--goal", required=True)
    p_run.add_argument("--docs", help="file or directory of .md/.txt docs")
    p_run.add_argument("--db", default="sage_state.db")
    p_run.add_argument("--provider", choices=["mock", "claude"], default=None)
    p_run.add_argument("--cycles", type=int, default=1,
                       help="run the loop N times; learnings carry forward each cycle")
    p_run.add_argument("--instance", default=None,
                       help="resume a prior instance id; rehydrates what it learned")
    p_run.set_defaults(func=cmd_run)

    p_log = sub.add_parser("log", help="replay an instance's activity log")
    p_log.add_argument("--instance", required=True)
    p_log.add_argument("--db", default="sage_state.db")
    p_log.set_defaults(func=cmd_log)

    p_status = sub.add_parser("status", help="reconstruct run state from the log alone")
    p_status.add_argument("--instance", required=True)
    p_status.add_argument("--db", default="sage_state.db")
    p_status.set_defaults(func=cmd_status)

    p_serve = sub.add_parser("serve", help="launch the live God-View web dashboard")
    p_serve.add_argument("--goal", required=True)
    p_serve.add_argument("--docs", help="file or directory of .md/.txt docs")
    p_serve.add_argument("--db", default="sage_state.db")
    p_serve.add_argument("--provider", choices=["mock", "claude"], default=None)
    p_serve.add_argument("--cycles", type=int, default=3,
                         help="run the loop N times so you can watch the tree grow")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
