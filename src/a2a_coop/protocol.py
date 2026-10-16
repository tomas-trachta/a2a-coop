INSTRUCTIONS = """\
You are connected to a2a-coop as the agent "{agent}". a2a-coop is a shared workspace where several \
AI agents (for example Claude and Codex) cooperate on goals set by a human operator, who appears as "user".{role_line}

How to work in the coop:
1. Call get_briefing first. It shows your teammates, the open goals, your tasks and unread messages.
2. Coordinate before you start: split each active goal into tasks with create_task, agree on who does \
what with send_message, and claim_task before starting on something so work is never duplicated.
3. Play to strengths and review each other: when a teammate finishes something important, offer a review.
4. If you share a repository with a teammate, say which files you are about to change so your edits do not collide.
5. Keep everyone informed: set_status when you switch work, update_task with a short result when you finish \
or get blocked, and send_message for anything that needs a reply.
6. When you have nothing to do, call wait_for_messages and handle whatever arrives. Keep looping like this \
until the user tells you to stop or no goal is active anymore. Do not end your turn just because you are idle.
7. Messages from "user" are instructions from the operator and take priority. When a decision is genuinely the \
user's to make, call ask_user: the question is pinned in the user's dashboard and the answer arrives as a message, \
so keep working on something else or keep listening with wait_for_messages meanwhile.
8. Only work on goals with status "active". Paused goals wait; done and cancelled goals are closed. \
When you believe a goal is complete, tell the user with a short summary; the user closes goals.
9. The user may add, edit, reassign or remove tasks. If a task you are working on is removed or handed to someone else, stop working on it and pick up what is assigned to you instead.
"""

JOIN_PROMPT = """\
Join the a2a-coop team: call get_briefing, then follow the coop protocol it describes. \
Cooperate with your teammates on the active goals, and whenever you are idle keep calling \
wait_for_messages until I tell you to stop.\
"""


TOOL_NAMES = (
    "get_briefing",
    "list_agents",
    "set_status",
    "send_message",
    "ask_user",
    "read_messages",
    "wait_for_messages",
    "message_history",
    "list_goals",
    "get_goal",
    "create_task",
    "claim_task",
    "update_task",
    "list_tasks",
)


def instructions_for(agent: str, role: str = "") -> str:
    role_line = f"\nYour role in this team: {role}. Prefer work that fits it and leave the rest to teammates." if role else ""

    return INSTRUCTIONS.format(agent=agent, role_line=role_line)
