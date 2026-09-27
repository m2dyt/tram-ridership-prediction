class ApplicationError(Exception):
    def __init__(
        self, code: str, message: str, field: str | None = None, retry_after: int | None = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.retry_after = retry_after
