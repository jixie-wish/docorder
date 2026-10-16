"""Errors the runner treats differently during retry."""


class DocorderError(Exception):
    """Failure of a stage, operator, or job definition."""


class JobValidationError(DocorderError):
    """The job graph is inconsistent."""

class OperatorValidationError(DocorderError):
    """The operator is invalid."""


class FatalError(DocorderError):
    """Do not retry. Input is missing or the contract is broken."""
