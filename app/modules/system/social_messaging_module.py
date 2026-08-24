from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.api.social_client import (
    SocialApiError,
    SocialAuthenticationError,
    SocialClient,
    SocialFriend,
    SocialMessage,
)
from app.config.settings import DESKTOP_TOKEN_ENV
from app.core.log_bus import add_log
from app.events.event_bus import emit_event
from app.features.plans import Plan
from app.modules.base import AssistantModule, ModuleResponse
from app.pc_control.clipboard import ClipboardError, read_text
from app.vision.screen_capture import capture_primary_screen
from app.voice.runtime import get_tts


POLL_SECONDS = 4.0
ERROR_BACKOFF_SECONDS = 15.0
MAX_ANNOUNCED_BODY_LENGTH = 600
MAX_OUTGOING_BODY_LENGTH = 4_000


@dataclass(frozen=True)
class SocialCommand:
    kind: str
    friend: SocialFriend
    body: str = ""


class SystemSocialMessagingModule(AssistantModule):
    feature_id = "social.messaging"
    display_name = "Сообщения друзьям Ziren"
    plan = Plan.FREE
    default_trigger_groups = {
        "social.message.text": {
            "display_name": "Написать другу",
            "triggers": ["напиши", "отправь сообщение"],
            "argument_hint": (
                "arguments.recipient — ник или личное голосовое имя друга; "
                "arguments.message — текст сообщения."
            ),
        },
        "social.message.screenshot": {
            "display_name": "Отправить снимок экрана",
            "triggers": [
                "сделай скриншот и отправь",
                "сделай скрин и отправь",
                "отправь скриншот",
                "отправь скрин",
            ],
            "argument_hint": "arguments.recipient — ник или личное голосовое имя друга.",
        },
        "social.message.clipboard": {
            "display_name": "Отправить скопированный текст",
            "triggers": [
                "отправь скопированное сообщение",
                "отправь скопированный текст",
                "отправь то что скопировано",
                "отправь то, что скопировано",
            ],
            "argument_hint": "arguments.recipient — ник или личное голосовое имя друга.",
        },
    }

    def __init__(
        self,
        client: SocialClient | None = None,
        *,
        start_inbox_listener: bool = True,
    ) -> None:
        self.client = client or SocialClient()
        self._stop_event = threading.Event()
        self._announced_in_session: set[int] = set()
        self._announce_lock = threading.Lock()
        self._listener_thread: threading.Thread | None = None

        if start_inbox_listener and os.environ.get(DESKTOP_TOKEN_ENV):
            self._listener_thread = threading.Thread(
                target=self._poll_announcements,
                daemon=True,
                name="ziren-social-inbox",
            )
            self._listener_thread.start()

    def can_handle(self, text: str) -> bool:
        return self._match_action_trigger(text) is not None

    def handle(self, text: str) -> ModuleResponse:
        try:
            return self._execute_command(self._parse_command(text))
        except ClipboardError as error:
            return ModuleResponse(text=f"Не смогла отправить буфер обмена: {error}")
        except SocialAuthenticationError:
            return ModuleResponse(
                text="Сессия Ziren устарела. Перезайди в аккаунт, чтобы отправлять сообщения."
            )
        except SocialApiError as error:
            return ModuleResponse(text=str(error))
        except Exception as error:
            add_log(
                "social.message.failed",
                level="error",
                meta={"error": str(error)},
            )
            return ModuleResponse(text="Не получилось отправить сообщение.")

    def execute_action(
        self,
        action_id: str,
        arguments: dict[str, Any] | None = None,
    ) -> ModuleResponse | None:
        if action_id not in self.default_trigger_groups:
            return None

        args = arguments or {}
        recipient = str(args.get("recipient") or "").strip()
        if not recipient:
            return ModuleResponse(text="Уточни, кому отправить сообщение.")

        try:
            friend = self._resolve_recipient_only(recipient)
            if action_id == "social.message.text":
                body = str(args.get("message") or "").strip()
                if not body:
                    return ModuleResponse(text="Скажи, что написать другу.")
                if len(body) > MAX_OUTGOING_BODY_LENGTH:
                    return ModuleResponse(text="Сообщение слишком длинное для одной голосовой команды.")
                command = SocialCommand(kind="text", friend=friend, body=body)
            elif action_id == "social.message.screenshot":
                command = SocialCommand(kind="screenshot", friend=friend)
            else:
                command = SocialCommand(kind="clipboard", friend=friend)
            return self._execute_command(command)
        except ClipboardError as error:
            return ModuleResponse(text=f"Не смогла отправить буфер обмена: {error}")
        except SocialAuthenticationError:
            return ModuleResponse(
                text="Сессия Ziren устарела. Перезайди в аккаунт, чтобы отправлять сообщения."
            )
        except SocialApiError as error:
            return ModuleResponse(text=str(error))
        except Exception as error:
            add_log(
                "social.message.semantic_failed",
                level="error",
                meta={"action_id": action_id, "error": str(error)},
            )
            return ModuleResponse(text="Не получилось отправить сообщение.")

    def _execute_command(self, command: SocialCommand) -> ModuleResponse:
        if command.kind == "text":
            self.client.send_text(command.friend, command.body, kind="text")
            return ModuleResponse(
                text=f"Отправила сообщение для {command.friend.voice_name}."
            )

        if command.kind == "clipboard":
            copied = read_text()
            self.client.send_text(
                command.friend,
                copied,
                kind="clipboard",
            )
            return ModuleResponse(
                text=f"Отправила скопированный текст для {command.friend.voice_name}."
            )

        if command.kind == "screenshot":
            screenshot = capture_primary_screen()
            self.client.send_screenshot(
                command.friend,
                screenshot.data_url,
            )
            return ModuleResponse(
                text=f"Сделала скриншот и отправила его для {command.friend.voice_name}."
            )

        return ModuleResponse(text="Не поняла, что нужно отправить.")

    def stop(self) -> None:
        self._stop_event.set()

    def _parse_command(self, text: str) -> SocialCommand:
        source = " ".join(str(text or "").split()).strip()
        matched = self._match_action_trigger(source)
        if matched is None:
            raise SocialApiError("Не поняла команду сообщения")

        action_id, end_word_index = matched
        source_words = source.split()
        remainder = " ".join(source_words[end_word_index:]).strip(" ,.!?:;-")

        if action_id == "social.message.screenshot":
            recipient = self._clean_recipient_tail(remainder)
            if not recipient:
                raise SocialApiError("Не услышала, кому отправить скриншот")
            return SocialCommand(
                kind="screenshot",
                friend=self._resolve_recipient_only(recipient),
            )

        if action_id == "social.message.clipboard":
            recipient = self._clean_recipient_tail(remainder)
            if not recipient:
                raise SocialApiError("Не услышала, кому отправить скопированный текст")
            return SocialCommand(
                kind="clipboard",
                friend=self._resolve_recipient_only(recipient),
            )

        if not remainder:
            raise SocialApiError("Скажи имя друга и текст сообщения")

        friend, body = self._resolve_friend_and_body(remainder)
        if not body:
            raise SocialApiError("Скажи, что написать другу")
        return SocialCommand(kind="text", friend=friend, body=body)

    def _match_action_trigger(self, source: str) -> tuple[str, int] | None:
        source_words = str(source or "").split()
        source_tokens = [self._normalize_word(word) for word in source_words]
        matches: list[tuple[int, int, str, int]] = []

        for action_id in self.default_trigger_groups:
            for trigger in self.get_action_triggers(action_id):
                trigger_words = str(trigger or "").split()
                trigger_tokens = [self._normalize_word(word) for word in trigger_words]
                trigger_tokens = [word for word in trigger_tokens if word]
                if not trigger_tokens:
                    continue

                width = len(trigger_tokens)
                for start in range(0, len(source_tokens) - width + 1):
                    if source_tokens[start : start + width] != trigger_tokens:
                        continue
                    # Start-of-command matches outrank incidental mentions. The
                    # global Snake router then compares this trigger length with
                    # other modules, so "напиши здесь" beats broad "напиши".
                    prefix_bonus = 20_000 if start == 0 else 10_000
                    score = prefix_bonus + len(" ".join(trigger_tokens))
                    matches.append((score, width, action_id, start + width))

        if not matches:
            return None

        _, _, action_id, end_word_index = max(matches, key=lambda item: item[0])
        return action_id, end_word_index

    @staticmethod
    def _normalize_word(value: str) -> str:
        normalized = str(value or "").lower().replace("ё", "е")
        return re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)

    @staticmethod
    def _clean_recipient_tail(value: str) -> str:
        recipient = str(value or "").strip(" ,.!?:;-")
        recipient = re.sub(
            r"^(?:его|это|для|к|другу|пользователю)\s+",
            "",
            recipient,
            flags=re.IGNORECASE,
        )
        return recipient.strip(" ,.!?:;-")

    def _resolve_recipient_only(self, spoken: str) -> SocialFriend:
        recipient = re.sub(
            r"^(?:для|к|другу|пользователю)\s+",
            "",
            spoken.strip(),
            flags=re.IGNORECASE,
        )
        return self.client.resolve_friend(recipient)

    def _resolve_friend_and_body(self, remainder: str) -> tuple[SocialFriend, str]:
        words = remainder.split()

        if len(words) < 2:
            raise SocialApiError("Скажи имя друга и текст сообщения")

        matches: list[tuple[int, SocialFriend, str]] = []
        max_name_words = min(5, len(words) - 1)

        for split_index in range(1, max_name_words + 1):
            spoken_name = " ".join(words[:split_index])
            body = " ".join(words[split_index:]).strip()

            try:
                friend = self.client.resolve_friend(spoken_name)
            except SocialApiError:
                continue

            if body:
                matches.append((split_index, friend, body))

        if not matches:
            raise SocialApiError(
                "Не смогла уверенно определить друга. Назови его ник или голосовое имя."
            )

        matches.sort(key=lambda item: item[0], reverse=True)
        best = matches[0]
        distinct_friends = {item[1].id for item in matches}

        if len(distinct_friends) > 1:
            top_length = best[0]
            top_friends = {
                item[1].id
                for item in matches
                if item[0] == top_length
            }
            if len(top_friends) > 1:
                raise SocialApiError("Не уверена, кому отправить сообщение. Назови друга точнее.")

        return best[1], best[2]

    def _normalize(self, text: str) -> str:
        return " ".join(str(text or "").lower().replace("ё", "е").split())

    def _poll_announcements(self) -> None:
        time.sleep(2.0)
        delay = POLL_SECONDS

        while not self._stop_event.wait(delay):
            try:
                messages = self.client.get_announcements()
                delay = POLL_SECONDS
            except SocialAuthenticationError:
                add_log(
                    "social.inbox.authentication_required",
                    level="warn",
                )
                delay = ERROR_BACKOFF_SECONDS
                continue
            except Exception as error:
                add_log(
                    "social.inbox.poll_failed",
                    level="warn",
                    meta={"error": str(error)},
                )
                delay = ERROR_BACKOFF_SECONDS
                continue

            for message in messages:
                if self._stop_event.is_set():
                    return

                if message.id in self._announced_in_session:
                    continue

                if self._try_announce(message):
                    break

    def _try_announce(self, message: SocialMessage) -> bool:
        with self._announce_lock:
            if message.id in self._announced_in_session:
                return False

            tts = get_tts()

            if (
                tts is None
                or tts.model is None
                or tts.state.shutdown.is_set()
                or tts.state.is_speaking.is_set()
            ):
                return False

            spoken_text = self._announcement_text(message)
            self._announced_in_session.add(message.id)

            try:
                def on_start() -> None:
                    emit_event(
                        "social.message.announced",
                        payload={
                            "message_id": message.id,
                            "sender_id": message.sender_id,
                            "kind": message.kind,
                        },
                    )
                    add_log(
                        "Входящее сообщение озвучивается",
                        meta={
                            "message_id": message.id,
                            "sender": message.sender_voice_name
                            or message.sender_username,
                        },
                    )

                tts.speak(spoken_text, on_start=on_start)

                if not tts.state.is_speaking.is_set():
                    self._announced_in_session.discard(message.id)
                    return False

                try:
                    self.client.acknowledge_announcement(message.id)
                except Exception as error:
                    add_log(
                        "social.inbox.ack_failed",
                        level="warn",
                        meta={
                            "message_id": message.id,
                            "error": str(error),
                        },
                    )
                return True
            except Exception as error:
                self._announced_in_session.discard(message.id)
                add_log(
                    "social.inbox.tts_failed",
                    level="warn",
                    meta={"message_id": message.id, "error": str(error)},
                )
                return False

    def _announcement_text(self, message: SocialMessage) -> str:
        sender = (
            message.sender_voice_name
            or message.sender_username
            or "друга"
        )

        if message.kind == "screenshot":
            return f"От {sender} пришёл скриншот."

        body = " ".join(message.body.split())
        if len(body) > MAX_ANNOUNCED_BODY_LENGTH:
            body = body[:MAX_ANNOUNCED_BODY_LENGTH].rstrip() + ". Сообщение длиннее, открой чат, чтобы прочитать полностью."

        if not body:
            return f"Новое сообщение от {sender}."

        return f"Сообщение от {sender}: {body}"
