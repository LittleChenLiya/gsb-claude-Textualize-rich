class ConsoleError(Exception):
    """An error in console operation."""


class StyleError(Exception):
    """An error in styles."""


class StyleSyntaxError(ConsoleError):
    """Style was badly formatted."""


class MissingStyle(StyleError):
    """No such style."""


class StyleStackError(ConsoleError):
    """Style stack is invalid."""


class NotRenderableError(ConsoleError):
    """Object is not renderable."""


class CellOverflowError(ConsoleError):
    """A table cell exceeded the maximum length permitted when exporting structured data."""


class MarkupError(ConsoleError):
    """Markup was badly formatted."""


class LiveError(ConsoleError):
    """Error related to Live display."""


class NoAltScreen(ConsoleError):
    """Alt screen mode was required."""
