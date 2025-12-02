import http
import logging
import time

from django.conf import settings
from django.http import HttpResponseServerError

SETTING_TIMEOUT = "REQUEST_QUEUE_TIMEOUT_IN_SECONDS"
SETTING_TIMEOUT_DEFAULT = 30

logger = logging.getLogger(__name__)


class RequestQueueTimeoutMiddleware:
    """
    Discards requests that have queued for longer than a configurable timeout
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_start_header = request.headers.get("X-Request-Start")
        if request_start_header is None:
            return self.get_response(request)

        try:
            request_start = self._parse_request_start(request_start_header)
        except (TypeError, ValueError):
            logger.warning(
                f"Could not interpret `X-Request-Start` header value: {request_start_header}"
            )
            request.queue_time_in_seconds = None
            return self.get_response(request)

        request.queue_time_in_seconds = time.time() - request_start
        timeout_threshold = getattr(settings, SETTING_TIMEOUT, SETTING_TIMEOUT_DEFAULT)
        if request.queue_time_in_seconds > timeout_threshold:
            logger.warning(
                f"ev=request_queue_timeout, router_queue_time={request.queue_time_in_seconds:.2f}"
            )
            return HttpResponseServerError(
                "Busy", status=http.HTTPStatus.SERVICE_UNAVAILABLE
            )

        return self.get_response(request)

    def _parse_request_start(self, header_value):
        """
        Parse the X-Request-Start header value into seconds since epoch.

        Supports two formats:
        - Heroku: milliseconds since epoch (e.g., "1693406590527")
        - Scalingo: "t=" prefix with seconds.milliseconds (e.g., "t=1693406590.527")

        Returns:
            float: seconds since epoch

        Raises:
            ValueError: if the header value cannot be parsed
        """
        # Handle Scalingo format: t=1693406590.527
        if header_value.startswith("t="):
            return float(header_value[2:])

        # Handle Heroku format: milliseconds since epoch
        return int(header_value) / 1000
