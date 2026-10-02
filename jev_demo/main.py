"""CLI: run one command list through both engines and compare the decisions."""

import argparse
import os

from .config import load_env, settings
from .engines import JevError, get_engine, ping
from .keywords import KeywordEngine
from .policy import BLOCK, CONFIRM, decide

BLOCKED_BY_JEV = {BLOCK}


def load_cases(path: str) -> list[dict]:
    cases = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            case_id, _, command = line.partition("|")
            cases.append({"id": case_id.strip(), "command": command.strip()})
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="data/commands.txt")
    parser.add_argument(
        "--engine",
        choices=["auto", "jev", "recorded"],
        default="auto",
        help="auto uses the live API when TYPESAFE_API_KEY is set",
    )
    parser.add_argument("--details", action="store_true", help="show the raw judgments")
    parser.add_argument(
        "--transport",
        choices=["auto", "sdk", "http", "chat"],
        default="auto",
        help="auto uses typesafe-sdk when installed, otherwise the stdlib HTTP client",
    )
    parser.add_argument(
        "--ping", action="store_true", help="check the endpoint, the key and the model name, then exit"
    )
    parser.add_argument("--quiet", action="store_true", help="do not announce the loaded .env")
    args = parser.parse_args()

    env_file = load_env()
    if env_file and not args.quiet:
        print(f"config: loaded {env_file}\n")

    if args.ping:
        _, api_key, model, _ = settings()
        if not api_key:
            raise SystemExit("TYPESAFE_API_KEY is not set")
        try:
            ping(args.transport)
        except JevError as error:
            raise SystemExit(str(error))
        return

    recorded_path = os.path.join(os.path.dirname(args.cases), "recorded_answers.json")
    prefer = args.engine
    if prefer == "auto":
        prefer = "jev" if settings()[1] else "recorded"

    jev_engine = get_engine(recorded_path, prefer, args.transport)
    keyword_engine = KeywordEngine()
    cases = load_cases(args.cases)

    if jev_engine.name == "recorded":
        print("! no API key: replaying recorded answers, not live jev\n")

    rows = []
    for case in cases:
        keyword_judgment = keyword_engine.judge(case)
        try:
            jev_judgment = jev_engine.judge(case)
        except JevError as error:
            raise SystemExit(f"{case['id']}: {error}")
        rows.append((case, keyword_judgment, jev_judgment, decide(keyword_judgment), decide(jev_judgment)))

    width = 62
    label = jev_engine.name
    print(f"{'command':<{width}} {'keywords':<22} {label:<22}")
    print(f"{'-' * width} {'-' * 22} {'-' * 22}")

    differences, misses = 0, []
    for case, keyword_judgment, jev_judgment, from_keywords, from_jev in rows:
        mark = " "
        if from_keywords != from_jev:
            mark = "*"
            differences += 1
            if from_jev in BLOCKED_BY_JEV and from_keywords not in BLOCKED_BY_JEV:
                misses.append((case, from_keywords, from_jev))
        print(f"{mark}{case['command'][: width - 1]:<{width}} {from_keywords:<22} {from_jev:<22}")
        if args.details:
            for judgment in (keyword_judgment, jev_judgment):
                print(
                    f"    {judgment.source:<9} risk={judgment.risk:<12} conf={judgment.confidence:.2f}"
                    f" data_loss={judgment.data_loss:.2f} blast_radius={judgment.blast_radius:.1f}"
                    f"  ({judgment.reason})"
                )

    print(f"\n{len(rows)} commands, {differences} decisions differ (*)")
    if misses:
        print("\nthe jev engine blocks commands the keyword engine would let run:")
        for case, a, b in misses:
            print(f"  {case['command']}  -> {a} vs {b}")
    print("policy is identical for both columns; only the judgments changed")


if __name__ == "__main__":
    main()