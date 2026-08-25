"""OpenKF SPI AES-256-GCM encryption/decryption utilities.

Implements the Dustess OpenKF HTTP SPI v1 encryption envelope protocol.
"""
import base64
import os
import time
import uuid
import logging
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# Header names
H_VERSION = "X-OpenKF-Version"
H_DIRECTION = "X-OpenKF-Direction"
H_APP_ID = "X-OpenKF-App-ID"
H_KEY_ID = "X-OpenKF-Key-ID"
H_ALGORITHM = "X-OpenKF-Algorithm"
H_TIMESTAMP = "X-OpenKF-Timestamp"
H_NONCE = "X-OpenKF-Nonce"
H_IV = "X-OpenKF-IV"
H_REQUEST_ID = "X-OpenKF-Request-ID"

REQUIRED_HEADERS = [
    H_VERSION, H_DIRECTION, H_APP_ID, H_KEY_ID,
    H_ALGORITHM, H_TIMESTAMP, H_NONCE, H_IV, H_REQUEST_ID,
]

# Timestamp tolerance: 5 minutes in milliseconds
TIMESTAMP_TOLERANCE_MS = 5 * 60 * 1000


class OpenKFCryptoError(Exception):
    """Raised when crypto operations fail."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class OpenKFCrypto:
    """Handles AES-256-GCM encryption/decryption for OpenKF SPI protocol."""

    def __init__(self, app_id: str, key_id: str, key_base64: str):
        """
        Args:
            app_id: Our application ID (used in outbound requests we send).
            key_id: Current key version identifier.
            key_base64: Base64-encoded 32-byte AES-256 key.
        """
        self.app_id = app_id
        self.key_id = key_id
        self._key = base64.b64decode(key_base64)
        if len(self._key) != 32:
            raise ValueError(f"AES-256 key must be 32 bytes, got {len(self._key)}")
        self._aesgcm = AESGCM(self._key)

    # ── AAD construction ──────────────────────────────────────────────────────

    def build_aad(self, method: str, path: str, headers: dict) -> bytes:
        """Build Additional Authenticated Data per protocol spec.

        Format: method
path
version
direction
appID
keyID
algorithm
timestamp
nonce
iv
requestID
        """
        parts = [
            method.upper(),
            path,
            headers.get(H_VERSION, ""),
            headers.get(H_DIRECTION, ""),
            headers.get(H_APP_ID, ""),
            headers.get(H_KEY_ID, ""),
            headers.get(H_ALGORITHM, ""),
            headers.get(H_TIMESTAMP, ""),
            headers.get(H_NONCE, ""),
            headers.get(H_IV, ""),
            headers.get(H_REQUEST_ID, ""),
        ]
        return "\n".join(parts).encode("utf-8")

    # ── Header validation ─────────────────────────────────────────────────────

    def validate_headers(self, headers: dict, expected_direction: str) -> bool:
        """Validate required headers, timestamp window, nonce/IV lengths.

        Raises OpenKFCryptoError with specific error codes on failure.
        """
        # Check all required headers present
        for h in REQUIRED_HEADERS:
            if not headers.get(h):
                raise OpenKFCryptoError(40001, f"Missing required header: {h}")

        # Version must be "1"
        if headers.get(H_VERSION) != "1":
            raise OpenKFCryptoError(40001, "Unsupported protocol version")

        # Direction
        if headers.get(H_DIRECTION) != expected_direction:
            raise OpenKFCryptoError(40001, f"Expected direction={expected_direction}")

        # Algorithm
        if headers.get(H_ALGORITHM) != "AES-256-GCM":
            raise OpenKFCryptoError(40001, "Unsupported algorithm")

        # Timestamp window (milliseconds)
        try:
            ts = int(headers[H_TIMESTAMP])
        except (ValueError, TypeError):
            raise OpenKFCryptoError(40004, "Invalid timestamp format")

        now_ms = int(time.time() * 1000)
        if abs(now_ms - ts) > TIMESTAMP_TOLERANCE_MS:
            raise OpenKFCryptoError(40004, "Timestamp outside tolerance window")

        # Nonce: base64 of 16 bytes → 24 chars
        try:
            nonce_bytes = base64.b64decode(headers[H_NONCE])
            if len(nonce_bytes) != 16:
                raise OpenKFCryptoError(40001, "Nonce must be 16 bytes")
        except Exception:
            raise OpenKFCryptoError(40001, "Invalid nonce encoding")

        # IV: base64 of 12 bytes → 16 chars
        try:
            iv_bytes = base64.b64decode(headers[H_IV])
            if len(iv_bytes) != 12:
                raise OpenKFCryptoError(40001, "IV must be 12 bytes for GCM")
        except Exception:
            raise OpenKFCryptoError(40001, "Invalid IV encoding")

        return True

    # ── Decrypt inbound request (chatdoing → us) ────────────────────────────

    def decrypt_request(
        self, method: str, path: str, headers: dict, ciphertext: bytes
    ) -> bytes:
        """Decrypt an inbound SPI request body.

        Args:
            method: HTTP method (POST).
            path: Request path.
            headers: Dict-like headers from the request.
            ciphertext: Raw body bytes (ciphertext || 16-byte tag).

        Returns:
            Decrypted plaintext bytes.

        Raises:
            OpenKFCryptoError on failure.
        """
        self.validate_headers(headers, "request")
        aad = self.build_aad(method, path, headers)
        iv = base64.b64decode(headers[H_IV])
        try:
            plaintext = self._aesgcm.decrypt(iv, ciphertext, aad)
            return plaintext
        except Exception as exc:
            logger.error("decrypt_request failed: %s", exc)
            raise OpenKFCryptoError(40002, "Decryption failed") from exc

    # ── Encrypt response (us → chatdoing) ────────────────────────────────────

    def encrypt_response(
        self, method: str, path: str, request_headers: dict, plaintext: bytes
    ) -> Tuple[bytes, dict]:
        """Encrypt a response to an inbound SPI request.

        Returns:
            (ciphertext_bytes, response_headers_dict)
        """
        iv = os.urandom(12)
        nonce = os.urandom(16)
        now_ms = str(int(time.time() * 1000))
        request_id = str(uuid.uuid4())

        resp_headers = {
            H_VERSION: "1",
            H_DIRECTION: "response",
            H_APP_ID: request_headers.get(H_APP_ID, self.app_id),
            H_KEY_ID: request_headers.get(H_KEY_ID, self.key_id),
            H_ALGORITHM: "AES-256-GCM",
            H_TIMESTAMP: now_ms,
            H_NONCE: base64.b64encode(nonce).decode(),
            H_IV: base64.b64encode(iv).decode(),
            H_REQUEST_ID: request_id,
        }

        aad = self.build_aad(method, path, resp_headers)
        ciphertext = self._aesgcm.encrypt(iv, plaintext, aad)
        return ciphertext, resp_headers

    # ── Encrypt outbound request (us → chatdoing callback) ───────────────────

    def encrypt_request(
        self, method: str, path: str, plaintext: bytes,
        request_id: Optional[str] = None,
    ) -> Tuple[bytes, dict]:
        """Encrypt an outbound request (callback to chatdoing).

        Args:
            method: HTTP method.
            path: URL path (without scheme/host).
            plaintext: JSON payload bytes.
            request_id: Optional fixed request ID (for retries).
                        If None a new UUID v4 is generated.

        Returns:
            (ciphertext_bytes, request_headers_dict)
        """
        iv = os.urandom(12)
        nonce = os.urandom(16)
        now_ms = str(int(time.time() * 1000))
        if request_id is None:
            request_id = str(uuid.uuid4())

        req_headers = {
            H_VERSION: "1",
            H_DIRECTION: "request",
            H_APP_ID: self.app_id,
            H_KEY_ID: self.key_id,
            H_ALGORITHM: "AES-256-GCM",
            H_TIMESTAMP: now_ms,
            H_NONCE: base64.b64encode(nonce).decode(),
            H_IV: base64.b64encode(iv).decode(),
            H_REQUEST_ID: request_id,
        }

        aad = self.build_aad(method, path, req_headers)
        ciphertext = self._aesgcm.encrypt(iv, plaintext, aad)
        return ciphertext, req_headers

    # ── Decrypt response (chatdoing → us, callback reply) ────────────────────

    def decrypt_response(
        self, method: str, path: str, headers: dict, ciphertext: bytes
    ) -> bytes:
        """Decrypt a response to our outbound callback request.

        Raises:
            OpenKFCryptoError on failure.
        """
        self.validate_headers(headers, "response")
        aad = self.build_aad(method, path, headers)
        iv = base64.b64decode(headers[H_IV])
        try:
            plaintext = self._aesgcm.decrypt(iv, ciphertext, aad)
            return plaintext
        except Exception as exc:
            logger.error("decrypt_response failed: %s", exc)
            raise OpenKFCryptoError(40002, "Decryption of response failed") from exc
