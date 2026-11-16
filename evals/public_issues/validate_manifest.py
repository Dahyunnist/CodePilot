from pathlib import Path
import json

REQUIRED_FROZEN = ("license", "base_sha", "fix_sha", "test_commands", "reproduction_passed")

def validate(candidate: dict) -> list[str]:
    errors = []
    for key in ("id", "repository", "issue_url", "status"):
        if not candidate.get(key): errors.append(f"missing:{key}")
    if candidate.get("status") not in {"pending_reproduction", "frozen", "excluded"}:
        errors.append("invalid:status")
    if candidate.get("status") == "frozen":
        errors.extend(f"missing:{key}" for key in REQUIRED_FROZEN if not candidate.get(key))
    return errors

def main():
    path = Path(__file__).with_name("candidates.json")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    invalid = [(item.get("id"), validate(item)) for item in data if validate(item)]
    if invalid:
        raise SystemExit(json.dumps(invalid, ensure_ascii=False))
    print(f"候选清单格式通过：{len(data)} 条（pending 不代表已冻结）")

if __name__ == "__main__": main()
