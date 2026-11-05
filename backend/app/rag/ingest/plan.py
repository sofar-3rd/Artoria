from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    added: list[str]
    changed: list[str]
    removed: list[str]
    unchanged: list[str]


def plan(remote: dict[str, str], local: dict[str, str]) -> Plan:
    added = sorted(p for p in remote if p not in local)
    removed = sorted(p for p in local if p not in remote)
    both = [p for p in remote if p in local]
    changed = sorted(p for p in both if remote[p] != local[p])
    unchanged = sorted(p for p in both if remote[p] == local[p])
    return Plan(added, changed, removed, unchanged)
