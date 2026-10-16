"""Output function: publish upstream entities as job result files."""

from docorder.functions.output_function import OutputFunction


class Output(OutputFunction):
    """Publish each upstream entity as a file under the job result directory.

    Config keys:

    - ``directory``: optional destination. The default is ``.job_result``
      under the job root. A relative path is resolved from the operator home.
    - ``name_template``: optional Jinja template rendered with the entity tag.
      The default file name is the entity name.
    """
