from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import match
from inspect_ai.solver import generate


@task
def gauntlet_foreign_fixture() -> Task:
    """Tiny real Inspect eval used only to test Gauntlet's foreign-log adapter."""

    return Task(
        dataset=[
            Sample(id="one", input="Return the word alpha.", target="alpha"),
            Sample(id="two", input="Return the word beta.", target="beta"),
        ],
        solver=generate(),
        scorer=match(location="any"),
    )
