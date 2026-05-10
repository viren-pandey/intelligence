import json
import httpx
from datetime import datetime, timezone
from typing import Optional

from core.database import execute, fetchrow
from core.config import settings
from core.logging import get_logger


async def deliver_webhook(
    request_id: str, client_id: str, webhook_url: str, event_type: str, payload: dict
):
    log = get_logger("webhook_delivery")
    payload_bytes = len(json.dumps(payload).encode())
    status_code = None
    error_msg = None

    for attempt in range(settings.WEBHOOK_RETRY_MAX):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    webhook_url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-NEXUS-Event": event_type,
                        "X-NEXUS-Request-ID": request_id,
                        "X-NEXUS-Attempt": str(attempt + 1),
                    },
                )
                status_code = resp.status_code
                if status_code < 500:
                    break
                error_msg = f"HTTP {status_code}"
        except Exception as e:
            error_msg = str(e)
            status_code = 0

    await execute(
        """INSERT INTO webhook_deliveries
           (request_id, client_id, webhook_url, event_type, payload_size_bytes,
            http_status, delivered_at, retry_count, error_message)
           VALUES ($1, $2::uuid, $3, $4, $5, $6, NOW(), $7, $8)""",
        request_id,
        client_id,
        webhook_url,
        event_type,
        payload_bytes,
        status_code or 0,
        attempt,
        error_msg,
    )

    if status_code and status_code < 400:
        log.info(
            "webhook_delivered",
            request_id=request_id,
            event=event_type,
            status=status_code,
        )
    else:
        log.warning(
            "webhook_failed",
            request_id=request_id,
            event=event_type,
            status=status_code,
            error=error_msg,
        )
