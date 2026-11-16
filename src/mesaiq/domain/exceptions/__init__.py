"""Domain exceptions for MesaIQ.

These exceptions are pure Python and do not depend on external libraries.
"""


class DomainException(Exception):
    """Base exception for all domain-level validation and rule failures."""


class InvalidRatingError(DomainException):
    """Raised when a review rating is outside the range 1-5."""


class EmptyFieldError(DomainException):
    """Raised when a mandatory review or entity field is empty."""


class InvalidImportJobStateError(DomainException):
    """Raised when an invalid state transition or operation is performed on an ImportJob."""


class InconsistentCountersError(DomainException):
    """Raised when ImportJob row counters are negative or inconsistent."""


class ImportJobNotFoundError(DomainException):
    """Raised when an operation attempts to update a non-existent ImportJob."""
