import hashlib
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

from werkzeug.security import check_password_hash, generate_password_hash


USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{3,32}$")
PASSWORD_MIN_LENGTH = 16
INVITATION_TTL_SECONDS = 24 * 60 * 60


class AccountStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_database(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS invitations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_hash TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                    created_by INTEGER NOT NULL,
                    expires_at REAL NOT NULL,
                    used_at REAL,
                    FOREIGN KEY (created_by) REFERENCES users (id)
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _hash_invitation(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_username(username: str) -> str:
        normalized = username.strip().lower()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("Username must be 3-32 letters, numbers, dots, underscores, or hyphens.")
        return normalized

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long.")

    def create_initial_admin(self, username: str, password: str) -> None:
        username = self._validate_username(username)
        self._validate_password(password)
        password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count:
                raise ValueError("Initial administrator already exists; use the admin interface for accounts.")
            connection.execute(
                """
                INSERT INTO users (username, password_hash, role, created_at, updated_at)
                VALUES (?, ?, 'admin', ?, ?)
                """,
                (username, password_hash, now, now),
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise ValueError("That username already exists.") from error
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, object]]:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
            if row is None or not row["is_active"]:
                return None
            if not check_password_hash(str(row["password_hash"]), password):
                return None
            return {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "role": str(row["role"]),
            }
        finally:
            connection.close()

    def get_user(self, user_id: int) -> Optional[Dict[str, object]]:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT id, username, role, is_active FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if row is None or not row["is_active"]:
                return None
            return {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "role": str(row["role"]),
                "is_active": bool(row["is_active"]),
            }
        finally:
            connection.close()

    def create_invitation(self, role: str, created_by: int) -> str:
        if role not in {"admin", "user"}:
            raise ValueError("Invitation role must be admin or user.")
        token = secrets.token_urlsafe(32)
        now = time.time()
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO invitations (token_hash, role, created_by, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    self._hash_invitation(token),
                    role,
                    created_by,
                    now + INVITATION_TTL_SECONDS,
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return token

    def accept_invitation(self, token: str, username: str, password: str) -> None:
        username = self._validate_username(username)
        self._validate_password(password)
        password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")
        now_epoch = time.time()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            invitation = connection.execute(
                """
                SELECT id, role FROM invitations
                WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
                """,
                (self._hash_invitation(token), now_epoch),
            ).fetchone()
            if invitation is None:
                raise ValueError("Invitation is invalid, expired, or already used.")
            connection.execute(
                """
                INSERT INTO users (username, password_hash, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, password_hash, str(invitation["role"]), now, now),
            )
            connection.execute(
                "UPDATE invitations SET used_at = ? WHERE id = ?",
                (now_epoch, int(invitation["id"])),
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise ValueError("That username already exists.") from error
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_users(self):
        connection = self._connect()
        try:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, username, role, is_active, created_at
                    FROM users ORDER BY username COLLATE NOCASE
                    """
                ).fetchall()
            ]
        finally:
            connection.close()

    def set_user_status(self, user_id: int, is_active: bool) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            user = connection.execute(
                "SELECT role, is_active FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if user is None:
                raise ValueError("User not found.")
            if not is_active and user["role"] == "admin" and user["is_active"]:
                active_admins = connection.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
                ).fetchone()[0]
                if active_admins <= 1:
                    raise ValueError("Cannot deactivate the last active administrator.")
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            connection.execute(
                "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
                (int(is_active), now, user_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def set_user_role(self, user_id: int, role: str) -> None:
        if role not in {"admin", "user"}:
            raise ValueError("Role must be admin or user.")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            user = connection.execute(
                "SELECT role, is_active FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if user is None:
                raise ValueError("User not found.")
            if role != "admin" and user["role"] == "admin" and user["is_active"]:
                active_admins = connection.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
                ).fetchone()[0]
                if active_admins <= 1:
                    raise ValueError("Cannot remove the role from the last active administrator.")
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            connection.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
                (role, now, user_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def check_storage(self) -> bool:
        connection = self._connect()
        try:
            connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            connection.execute("SELECT 1 FROM invitations LIMIT 1").fetchone()
            return True
        finally:
            connection.close()
