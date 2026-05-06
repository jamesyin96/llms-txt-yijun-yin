"""Robots.txt fetching and rule evaluation.

This module owns robots.txt concerns only: locating `/robots.txt`, parsing
user-agent groups, collecting sitemap hints, and answering whether a URL is
allowed for this crawler. Network access goes through `fetcher.py`.
"""

from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urljoin, urlparse

import httpx

from app.config import USER_AGENT
from app.services.fetcher import FetchConfig, FetchError, FetchResult, fetch_url


ROBOTS_PATH = "/robots.txt"


@dataclass(frozen=True)
class RobotsRule:
    """One Allow or Disallow path rule from robots.txt."""

    directive: str
    pattern: str


@dataclass(frozen=True)
class RobotsGroup:
    """A user-agent group and its path rules."""

    user_agents: tuple[str, ...]
    rules: tuple[RobotsRule, ...]


@dataclass(frozen=True)
class RobotsRules:
    """Parsed robots.txt policy for one website."""

    root_url: str
    groups: tuple[RobotsGroup, ...] = field(default_factory=tuple)
    sitemap_urls: tuple[str, ...] = field(default_factory=tuple)

    def is_allowed(self, url: str, user_agent: str = USER_AGENT) -> bool:
        """Return whether `user_agent` may crawl `url`.

        V1 implements the common robots behavior needed for this project:
        choose the most specific matching user-agent group, then apply the
        longest matching Allow/Disallow path rule. If no rule matches, allow.
        """

        group = _select_group(self.groups, user_agent)
        if group is None:
            return True

        path = _path_for_matching(url)
        matching_rules = [rule for rule in group.rules if _rule_matches(rule.pattern, path)]
        if not matching_rules:
            return True

        winning_rule = max(
            matching_rules,
            key=lambda rule: (len(rule.pattern), 1 if rule.directive == "allow" else 0),
        )
        return winning_rule.directive == "allow"


class FetchRobotsFn(Protocol):
    """Callable shape for dependency-injected robots fetching."""

    def __call__(
        self,
        url: str,
        *,
        config: FetchConfig | None = None,
        client: httpx.Client | None = None,
    ) -> FetchResult:
        pass


def fetch_robots_rules(
    root_url: str,
    *,
    config: FetchConfig | None = None,
    client: httpx.Client | None = None,
    fetcher: FetchRobotsFn = fetch_url,
) -> RobotsRules:
    """Fetch and parse robots.txt for a root URL.

    Missing or unavailable robots.txt allows crawling for V1. Explicit 4xx
    responses also allow crawling. A 2xx response is parsed for rules and
    sitemap hints.
    """

    robots_url = robots_url_for(root_url)
    try:
        result = fetcher(robots_url, config=config, client=client)
    except FetchError:
        return RobotsRules(root_url=root_url)

    if result.status_code == 404 or result.status_code == 410:
        return RobotsRules(root_url=root_url)
    if result.status_code >= 400:
        return RobotsRules(root_url=root_url)

    return parse_robots_txt(result.text, root_url=root_url)


def robots_url_for(root_url: str) -> str:
    """Return the absolute robots.txt URL for a normalized root URL."""

    return urljoin(root_url, ROBOTS_PATH)


def parse_robots_txt(content: str, *, root_url: str) -> RobotsRules:
    """Parse robots.txt content into user-agent groups and sitemap hints."""

    groups: list[RobotsGroup] = []
    sitemap_urls: list[str] = []
    current_agents: list[str] = []
    current_rules: list[RobotsRule] = []
    has_group_rules = False

    for raw_line in content.splitlines():
        line = _strip_comment(raw_line).strip()
        if not line or ":" not in line:
            continue

        field, value = line.split(":", 1)
        field = field.strip().lower()
        value = value.strip()

        if field == "sitemap":
            if value:
                sitemap_urls.append(urljoin(root_url, value))
            continue

        if field == "user-agent":
            if has_group_rules:
                groups.append(_build_group(current_agents, current_rules))
                current_agents = []
                current_rules = []
                has_group_rules = False
            current_agents.append(value.lower())
            continue

        if field in {"allow", "disallow"} and current_agents:
            has_group_rules = True
            if value == "" and field == "disallow":
                continue
            current_rules.append(RobotsRule(directive=field, pattern=value or "/"))

    if current_agents or current_rules:
        groups.append(_build_group(current_agents, current_rules))

    return RobotsRules(
        root_url=root_url,
        groups=tuple(group for group in groups if group.user_agents),
        sitemap_urls=tuple(dict.fromkeys(sitemap_urls)),
    )


def _build_group(user_agents: list[str], rules: list[RobotsRule]) -> RobotsGroup:
    return RobotsGroup(user_agents=tuple(user_agents), rules=tuple(rules))


def _select_group(groups: tuple[RobotsGroup, ...], user_agent: str) -> RobotsGroup | None:
    normalized_agent = user_agent.lower()
    candidates: list[tuple[int, RobotsGroup]] = []

    for group in groups:
        for group_agent in group.user_agents:
            if group_agent == "*":
                candidates.append((1, group))
            elif group_agent and group_agent in normalized_agent:
                candidates.append((len(group_agent), group))

    if not candidates:
        return None

    return max(candidates, key=lambda candidate: candidate[0])[1]


def _rule_matches(pattern: str, path: str) -> bool:
    if pattern == "":
        return False
    if pattern == "/":
        return True
    if "*" not in pattern and "$" not in pattern:
        return path.startswith(pattern)

    anchored = pattern.endswith("$")
    normalized_pattern = pattern[:-1] if anchored else pattern
    parts = normalized_pattern.split("*")
    position = 0

    if parts[0] and not path.startswith(parts[0]):
        return False

    for index, part in enumerate(parts):
        if part == "":
            continue
        found_at = path.find(part, position)
        if found_at == -1:
            return False
        if index == 0 and found_at != 0:
            return False
        position = found_at + len(part)

    return not anchored or position == len(path)


def _path_for_matching(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        return f"{path}?{parsed.query}"
    return path


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0]
