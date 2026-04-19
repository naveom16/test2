import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class PlayerSessionManager:
    def __init__(self, disconnect_timeout: int = 10, event_bus: Any = None) -> None:
        self.disconnect_timeout = disconnect_timeout
        self.event_bus = event_bus
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.sid_to_player: Dict[str, str] = {}
        self.cleanup_timers: Dict[str, threading.Timer] = {}
        self.lock = threading.RLock()

    def _log(self, message: str, **kwargs: Any) -> None:
        logger.info(message + " %s", kwargs)

    def _publish(self, event_name: str, **kwargs: Any) -> None:
        if not self.event_bus:
            return
        try:
            self.event_bus.publish(event_name, **kwargs)
        except Exception:
            logger.exception('Event publish failed: %s', event_name)

    def register_new_player(self, name: str, sid: str, color: str) -> Dict[str, Any]:
        with self.lock:
            player_id = uuid.uuid4().hex
            session = {
                "player_id": player_id,
                "sid": sid,
                "name": name,
                "color": color,
                "hearts": 3,
                "connected": True,
                "last_seen": time.time()
            }
            self.sessions[player_id] = session
            self.sid_to_player[sid] = player_id
            self._publish("player_created", player_id=player_id, session=session)
            self._log("Registered new player", player_id=player_id, sid=sid, name=name)
            return session

    def attach_session(self, player_id: str, sid: str, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self.lock:
            session = self.sessions.get(player_id)
            if session is None:
                return None

            old_sid = session.get("sid")
            if old_sid and old_sid != sid:
                self.sid_to_player.pop(old_sid, None)
            self.sid_to_player[sid] = player_id
            session["sid"] = sid
            session["connected"] = True
            session["last_seen"] = time.time()
            if name:
                session["name"] = name
            timer = self.cleanup_timers.pop(player_id, None)
            if timer:
                timer.cancel()
            self._publish("player_reconnected", player_id=player_id, session=session)
            self._log("Attached existing player session", player_id=player_id, sid=sid, name=session["name"])
            return session

    def detach_session(self, sid: str) -> None:
        with self.lock:
            player_id = self.sid_to_player.pop(sid, None)
            if player_id is None:
                logger.debug("Disconnect event for unknown sid %s", sid)
                return
            session = self.sessions.get(player_id)
            if session is None:
                logger.debug("Disconnect event for unknown player_id %s", player_id)
                return

            session["connected"] = False
            session["last_seen"] = time.time()
            self._schedule_cleanup(player_id)
            self._publish("player_disconnected", player_id=player_id, session=session)
            self._log("Marked player disconnected", player_id=player_id, sid=sid)

    def _schedule_cleanup(self, player_id: str) -> None:
        timer = self.cleanup_timers.get(player_id)
        if timer:
            timer.cancel()

        timer = threading.Timer(self.disconnect_timeout, self._cleanup_if_stale, args=(player_id,))
        timer.daemon = True
        timer.start()
        self.cleanup_timers[player_id] = timer
        logger.debug("Scheduled cleanup for player_id %s in %s seconds", player_id, self.disconnect_timeout)

    def _cleanup_if_stale(self, player_id: str) -> None:
        with self.lock:
            session = self.sessions.get(player_id)
            if session is None or session.get("connected"):
                return
            age = time.time() - session.get("last_seen", 0)
            if age < self.disconnect_timeout:
                return

            self.sessions.pop(player_id, None)
            self.cleanup_timers.pop(player_id, None)
            self._publish("player_removed", player_id=player_id, session=session)
            self._log("Removed stale player session", player_id=player_id)

    def get_by_sid(self, sid: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            player_id = self.sid_to_player.get(sid)
            return self.sessions.get(player_id) if player_id else None

    def get_by_player_id(self, player_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.sessions.get(player_id)

    def get_player_id(self, sid: str) -> Optional[str]:
        with self.lock:
            return self.sid_to_player.get(sid)

    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        with self.lock:
            return {pid: dict(session) for pid, session in self.sessions.items()}
