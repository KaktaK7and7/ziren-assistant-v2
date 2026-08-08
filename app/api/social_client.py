from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import httpx

from app.api.desktop_auth import (
    DesktopAuthenticationError,
    desktop_authorization_headers,
    normalize_desktop_token,
)
from app.config.settings import AUTH_SITE_URL, DESKTOP_TOKEN_ENV, get_desktop_token


FRIEND_CACHE_SECONDS = 15.0
MAX_OUTGOING_MESSAGE_LENGTH = 4_000
NAME_TOKEN_RE = re.compile(r"[0-9a-zа-яё_-]+", re.IGNORECASE)


class SocialAuthenticationError(RuntimeError):
    pass


class SocialApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class SocialFriend:
    id: int
    username: str
    voice_alias: str = ""
    announce_messages: bool = False
    public_profile_url: str | None = None

    @property
    def voice_name(self) -> str:
        return self.voice_alias or self.username


@dataclass(frozen=True)
class SocialMessage:
    id: int
    sender_id: int
    recipient_id: int
    kind: str
    body: str
    created_at: str
    sender_username: str = ""
    sender_voice_name: str = ""
    attachment_url: str | None = None


def normalize_spoken_name(value: object) -> str:
    text = str(value or "").casefold().replace("ё", "е")
    return " ".join(NAME_TOKEN_RE.findall(text))


def _name_variants(value: str) -> set[str]:
    normalized = normalize_spoken_name(value)

    if not normalized:
        return set()

    variants = {normalized}
    words = normalized.split()

    if len(words) == 1:
        word = words[0]
        variants.add(word)

        # Common Russian dative/accusative endings that appear in phrases such
        # as "напиши Диане" or "отправь Диме". A fuzzy name is never enough
        # to execute when two friends remain equally plausible.
        endings = (
            "е",
            "у",
            "ю",
            "а",
            "я",
            "ы",
            "и",
            "ой",
            "ей",
            "ом",
            "ем",
        )
        for ending in endings:
            if word.endswith(ending) and len(word) - len(ending) >= 3:
                variants.add(word[: -len(ending)])

        if word.endswith("а") and len(word) >= 4:
            variants.add(word[:-1] + "е")
            variants.add(word[:-1] + "у")
        elif word.endswith("я") and len(word) >= 4:
            variants.add(word[:-1] + "е")
            variants.add(word[:-1] + "ю")
        elif not word.endswith("а") and len(word) >= 3:
            variants.add(word + "у")
            variants.add(word + "е")

    return {item for item in variants if item}


def _friend_names(friend: SocialFriend) -> list[tuple[str, int]]:
    names: list[tuple[str, int]] = []

    # A private voice alias is an explicit routing choice made by the owner,
    # so it must beat an accidentally similar public username by a clear gap.
    if friend.voice_alias:
        names.append((friend.voice_alias, 10))

    names.append((friend.username, 0))
    return names


def _match_score(spoken: str, configured: str, priority: int) -> float:
    spoken_variants = _name_variants(spoken)
    configured_variants = _name_variants(configured)

    if not spoken_variants or not configured_variants:
        return 0.0

    if spoken_variants & configured_variants:
        return 100.0 + priority

    best_ratio = 0.0
    for left in spoken_variants:
        for right in configured_variants:
            if min(len(left), len(right)) < 3:
                continue

            if (
                len(left) >= 4
                and len(right) >= 4
                and left[:4] == right[:4]
            ):
                best_ratio = max(best_ratio, 0.91)

            best_ratio = max(
                best_ratio,
                SequenceMatcher(a=left, b=right).ratio(),
            )

    if best_ratio < 0.78:
        return 0.0

    return best_ratio * 100 + priority


def resolve_friend_by_voice(
    friends: list[SocialFriend],
    spoken_name: str,
) -> SocialFriend:
    normalized = normalize_spoken_name(spoken_name)

    if not normalized:
        raise SocialApiError("Не услышала, кому отправить сообщение")

    candidates: list[tuple[float, SocialFriend]] = []

    for friend in friends:
        score = max(
            (
                _match_score(normalized, configured, priority)
                for configured, priority in _friend_names(friend)
            ),
            default=0.0,
        )
        if score > 0:
            candidates.append((score, friend))

    if not candidates:
        raise SocialApiError(
            f"Не нашла друга с голосовым именем «{spoken_name.strip()}»"
        )

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_friend = candidates[0]

    if len(candidates) > 1:
        second_score, second_friend = candidates[1]
        if abs(best_score - second_score) < 3.0:
            raise SocialApiError(
                "Нашла несколько похожих друзей: "
                f"{best_friend.voice_name} и {second_friend.voice_name}. "
                "Назови точнее или задай одному из них другое голосовое имя."
            )

    return best_friend


class SocialClient:
    def __init__(
        self,
        desktop_token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.desktop_token = normalize_desktop_token(
            desktop_token or get_desktop_token()
        )

        try:
            self.authorization_headers = desktop_authorization_headers(
                self.desktop_token
            )
        except DesktopAuthenticationError as error:
            raise RuntimeError(f"{error} ({DESKTOP_TOKEN_ENV})") from error

        self.client = client or httpx.Client(
            base_url=AUTH_SITE_URL,
            timeout=30.0,
        )
        self._friend_cache: list[SocialFriend] = []
        self._friend_cache_at = 0.0
        self._lock = threading.Lock()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "headers": self.authorization_headers,
        }
        if payload is not None:
            options["json"] = payload
        if timeout is not None:
            options["timeout"] = timeout

        response = self.client.request(method, path, **options)

        if response.status_code in (401, 403):
            raise SocialAuthenticationError(
                "Desktop session is no longer authorized"
            )

        try:
            data = response.json()
        except ValueError as error:
            raise SocialApiError("Сервер сообщений вернул некорректный ответ") from error

        if not response.is_success:
            error_text = ""
            if isinstance(data, dict):
                error_text = str(data.get("error") or "").strip()
            raise SocialApiError(
                error_text or f"Ошибка сервера сообщений: {response.status_code}"
            )

        return data if isinstance(data, dict) else {}

    def list_friends(self, force: bool = False) -> list[SocialFriend]:
        with self._lock:
            if (
                not force
                and self._friend_cache
                and time.time() - self._friend_cache_at < FRIEND_CACHE_SECONDS
            ):
                return list(self._friend_cache)

        data = self._request("GET", "/api/social/friends")
        raw_friends = data.get("friends")
        friends: list[SocialFriend] = []

        if isinstance(raw_friends, list):
            for raw in raw_friends:
                if not isinstance(raw, dict):
                    continue
                try:
                    friend_id = int(raw.get("id"))
                except (TypeError, ValueError):
                    continue
                username = str(raw.get("username") or "").strip()
                if friend_id <= 0 or not username:
                    continue
                friends.append(
                    SocialFriend(
                        id=friend_id,
                        username=username,
                        voice_alias=str(raw.get("voice_alias") or "").strip(),
                        announce_messages=bool(raw.get("announce_messages")),
                        public_profile_url=(
                            str(raw.get("public_profile_url"))
                            if raw.get("public_profile_url")
                            else None
                        ),
                    )
                )

        with self._lock:
            self._friend_cache = friends
            self._friend_cache_at = time.time()

        return list(friends)

    def resolve_friend(self, spoken_name: str) -> SocialFriend:
        return resolve_friend_by_voice(self.list_friends(), spoken_name)

    def send_text(
        self,
        friend: SocialFriend,
        body: str,
        *,
        kind: str = "text",
    ) -> SocialMessage:
        text = str(body or "").strip()

        if not text:
            raise SocialApiError("Сообщение получилось пустым")

        if len(text) > MAX_OUTGOING_MESSAGE_LENGTH:
            raise SocialApiError("Сообщение слишком длинное")

        data = self._request(
            "POST",
            "/api/social/messages",
            payload={
                "recipient_id": friend.id,
                "kind": kind,
                "body": text,
            },
        )
        return self._message_from_payload(data.get("message"))

    def send_screenshot(
        self,
        friend: SocialFriend,
        image_data_url: str,
        body: str = "",
    ) -> SocialMessage:
        data = self._request(
            "POST",
            "/api/social/messages",
            payload={
                "recipient_id": friend.id,
                "kind": "screenshot",
                "body": str(body or "").strip()[:MAX_OUTGOING_MESSAGE_LENGTH],
                "image_data_url": image_data_url,
            },
            timeout=45.0,
        )
        return self._message_from_payload(data.get("message"))

    def get_announcements(self) -> list[SocialMessage]:
        data = self._request("GET", "/api/social/announcements")
        raw_messages = data.get("messages")

        if not isinstance(raw_messages, list):
            return []

        messages: list[SocialMessage] = []
        for raw in raw_messages:
            try:
                messages.append(self._message_from_payload(raw))
            except SocialApiError:
                continue
        return messages

    def acknowledge_announcement(self, message_id: int) -> None:
        self._request(
            "POST",
            f"/api/social/messages/{int(message_id)}/announced",
            payload={},
        )

    def _message_from_payload(self, raw: object) -> SocialMessage:
        if not isinstance(raw, dict):
            raise SocialApiError("Сервер не вернул сообщение")

        try:
            message_id = int(raw.get("id"))
            sender_id = int(raw.get("sender_id"))
            recipient_id = int(raw.get("recipient_id"))
        except (TypeError, ValueError) as error:
            raise SocialApiError("Некорректные данные сообщения") from error

        return SocialMessage(
            id=message_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            kind=str(raw.get("kind") or "text"),
            body=str(raw.get("body") or ""),
            created_at=str(raw.get("created_at") or ""),
            sender_username=str(raw.get("sender_username") or ""),
            sender_voice_name=str(raw.get("sender_voice_name") or ""),
            attachment_url=(
                str(raw.get("attachment_url"))
                if raw.get("attachment_url")
                else None
            ),
        )
