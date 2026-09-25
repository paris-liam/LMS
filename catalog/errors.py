"""Expected failures. The CLI prints these as one-line errors (exit 2)
instead of a traceback; anything else is a bug and keeps its traceback."""


class CatalogError(Exception):
    """Base for every expected, user-fixable failure."""


class MissingEnvError(CatalogError):
    """A required environment variable is not set."""


class NoRunError(CatalogError):
    """No usable audit run folder exists."""


class InputShapeError(CatalogError):
    """An input file is not the shape the command expects."""


class ShopifyError(CatalogError):
    """The Shopify CLI failed, is missing, or is not authenticated."""
