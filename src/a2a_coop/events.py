from .models import Goal, Task


def goal_created(goal: Goal) -> str:
    details = f"\n{goal.description}" if goal.description else ""

    return f"user set a new goal #{goal.id}: {goal.title}{details}"


def goal_status_changed(goal: Goal) -> str:
    return f"user marked goal #{goal.id} as {goal.status}: {goal.title}"


def task_created(actor: str, task: Task) -> str:
    return f"{actor} created task #{task.id} on goal #{task.goal_id}: {task.title} ({task.assignee or 'unassigned'})"


def task_claimed(actor: str, task: Task) -> str:
    return f"{actor} claimed task #{task.id}: {task.title}"


def task_updated(actor: str, task: Task) -> str:
    result = f"\nResult: {task.result}" if task.result else ""

    return f"{actor} updated task #{task.id} [{task.status}, {task.assignee or 'unassigned'}]: {task.title}{result}"


def task_removed(actor: str, task: Task) -> str:
    return f"{actor} removed task #{task.id}: {task.title}"


def goal_edited(goal: Goal) -> str:
    details = f"\n{goal.description}" if goal.description else ""

    return f"user edited goal #{goal.id}: {goal.title}{details}"


def goal_removed(goal: Goal, task_count: int) -> str:
    return f"user removed goal #{goal.id} and its {task_count} task(s): {goal.title}"
