from docorder.functions.function import Function


class OutputFunction(Function):
    """Type marker for an output operator.

    The operator writes upstream entity data to the job result directory.
    Subclasses do not fill entities.
    """
