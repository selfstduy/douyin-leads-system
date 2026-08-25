"""OpenKF SPI v1 inbound endpoints.

These endpoints receive encrypted calls from chatdoing.
No JWT auth — security is provided by the AES-256-GCM envelope.
"""
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.core.deps import async_session_factory
from app.services.openkf_crypto import (
    OpenKFCryptoError,
    get_crypto,
    H_VERSION, H_DIRECTION, H_APP_ID, H_KEY_ID,
    H_ALGORITHM, H_TIMESTAMP, H_NONCE, H_IV, H_REQUEST_ID,
)
from app.services.openkf_service import openkf_service, _nonce_seen

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/open-kf/spi/v1", tags=["OpenKF SPI"])


def _headers_dict(request: Request) -> dict:
    """Extract OpenKF headers from the request into a plain dict."""
    keys = [H_VERSION, H_DIRECTION, H_APP_ID, H_KEY_ID,
            H_ALGORITHM, H_TIMESTAMP, H_NONCE, H_IV, H_REQUEST_ID]
    return {k: request.headers.get(k, "") for k in keys}


def _encrypted_response(
    request: Request,
    request_headers: dict,
    code: int = 0,
    message: str = "",
    request_id: str = "",
    duplicate: bool = False,
    data=None,
):
    """Build a unified JSON response, encrypt it, and return a Response."""
    crypto = get_crypto()
    body = {
        "code": code,
        "message": message,
        "request_id": request_id or request_headers.get(H_REQUEST_ID, ""),
        "duplicate": duplicate,
        "data": data,
    }
    plaintext = json.dumps(body, ensure_ascii=False).encode("utf-8")
    path = request.url.path
    ciphertext, resp_headers = crypto.encrypt_response(
        "POST", path, request_headers, plaintext
    )
    return Response(
        content=ciphertext,
        media_type="application/octet-stream",
        headers=resp_headers,
    )


def _error_response(
    request: Request,
    request_headers: dict,
    code: int,
    message: str,
):
    """Return an encrypted error response."""
    return _encrypted_response(
        request, request_headers, code=code, message=message
    )


async def _process_spi(request: Request, handler_name: str):
    """Common SPI processing pipeline: read body, validate, decrypt, dispatch."""
    headers = _headers_dict(request)
    raw_body = await request.body()
    path = request.url.path

    try:
        crypto = get_crypto()

        # Validate headers
        crypto.validate_headers(headers, "request")

        # Replay check on nonce
        app_id = headers.get(H_APP_ID, "")
        nonce = headers.get(H_NONCE, "")
        if await _nonce_seen(app_id, nonce):
            return _error_response(request, headers, 40003, "Nonce replay detected")

        # Decrypt
        plaintext = crypto.decrypt_request("POST", path, headers, raw_body)
        body = json.loads(plaintext.decode("utf-8"))

    except OpenKFCryptoError as exc:
        logger.warning("SPI %s crypto error: [%d] %s", handler_name, exc.code, exc.message)
        return _error_response(request, headers, exc.code, exc.message)
    except json.JSONDecodeError:
        return _error_response(request, headers, 40001, "Invalid JSON after decryption")
    except Exception as exc:
        logger.error("SPI %s unexpected error: %s", handler_name, exc, exc_info=True)
        return _error_response(request, headers, 40001, "Internal processing error")

    return headers, body


@router.post("/messages/send")
async def spi_send_message(request: Request):
    """Receive a message from chatdoing."""
    result = await _process_spi(request, "send_message")
    if isinstance(result, Response):
        return result

    headers, body = result
    request_id = headers.get(H_REQUEST_ID, "")

    async with async_session_factory() as db:
        try:
            result_data = await openkf_service.handle_send_message(db, body)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("handle_send_message DB error: %s", exc, exc_info=True)
            return _error_response(request, headers, 40001, "Database error")

    return _encrypted_response(
        request, headers,
        request_id=request_id,
        duplicate=result_data.get("duplicate", False),
    )


@router.post("/chats/transfer")
async def spi_transfer(request: Request):
    """Handle transfer-to-human from chatdoing."""
    result = await _process_spi(request, "transfer")
    if isinstance(result, Response):
        return result

    headers, body = result
    request_id = headers.get(H_REQUEST_ID, "")

    async with async_session_factory() as db:
        try:
            result_data = await openkf_service.handle_transfer(db, body)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("handle_transfer DB error: %s", exc, exc_info=True)
            return _error_response(request, headers, 40001, "Database error")

    return _encrypted_response(
        request, headers,
        request_id=request_id,
        duplicate=result_data.get("duplicate", False),
    )


@router.post("/contacts/get")
async def spi_contact_get(request: Request):
    """Query visitor/contact info."""
    result = await _process_spi(request, "contact_get")
    if isinstance(result, Response):
        return result

    headers, body = result
    request_id = headers.get(H_REQUEST_ID, "")

    async with async_session_factory() as db:
        try:
            result_data = await openkf_service.handle_contact_query(db, body)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.error("handle_contact_query DB error: %s", exc, exc_info=True)
            return _error_response(request, headers, 40001, "Database error")

    return _encrypted_response(
        request, headers,
        request_id=request_id,
        duplicate=result_data.get("duplicate", False),
        data=result_data.get("data"),
    )
