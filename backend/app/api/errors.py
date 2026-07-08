"""Standardized API errors.

Raising ``APIError`` yields a consistent body ``{"error": {"code", "message"}}``
(see the handler registered in ``app.main``) instead of FastAPI's default
``{"detail": ...}``, so the frontend can branch on a stable ``code`` rather than
a free-text string.
"""


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
