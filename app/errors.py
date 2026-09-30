"""Application errors. Each carries an HTTP status and a user-safe message."""


class ComicCraftError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ConfigurationError(ComicCraftError):
    status_code = 503
    code = "configuration_error"


class GeminiError(ComicCraftError):
    status_code = 502
    code = "gemini_error"

    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class InvalidStoryError(ComicCraftError):
    status_code = 502
    code = "invalid_story"


class ImageGenerationError(ComicCraftError):
    status_code = 500
    code = "image_error"


class PDFError(ComicCraftError):
    status_code = 500
    code = "pdf_error"


class NotFoundError(ComicCraftError):
    status_code = 404
    code = "not_found"
