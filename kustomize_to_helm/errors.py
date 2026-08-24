"""Exception hierarchy for the migration framework."""


class MigrationError(Exception):
    """Base class for expected, user-actionable migration failures."""


class ConfigurationError(MigrationError):
    """Raised when an input configuration or option is invalid."""


class BuildError(MigrationError):
    """Raised when Kustomize cannot render an input configuration."""


class GenerationError(MigrationError):
    """Raised when a Helm chart cannot be generated safely."""


class ValidationError(MigrationError):
    """Raised when a generated chart is invalid or changes semantics."""
