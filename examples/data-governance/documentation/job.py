from pathlib import Path

from dotenv import load_dotenv

from docorder.core.job import Job
from docorder.core.runner import execute

REPO_PATH = Path(__file__).resolve().parents[1]
JOB_ROOT = REPO_PATH / "documentation"
load_dotenv(JOB_ROOT / ".env")


def main() -> None:
    job = Job("documentation", JOB_ROOT / "runs")
    job.add_operator_node("read_table_list", "source", config={"directory": str(JOB_ROOT / ".input")})
    job.add_operator_node(
        "json_to_common_prompt",
        "json_to_common_prompt",
        upstream="read_table_list",
    )
    job.add_operator_node(
        "output",
        "output",
        upstream="json_to_common_prompt",
        config={"directory": str(JOB_ROOT / ".output")},
    )

    execute(job, "demo2", start_from_scratch=True)


if __name__ == "__main__":
    main()
