"""AgentBox v5 agent registry."""
from .registry import (
    get_agent,
    list_agents,
    register_agent,
    set_agent_status,
    update_agent,
    can_delegate,
    load_delegate_matrix,
    seed_from_config,
)

__all__ = [
    "register_agent",
    "list_agents",
    "get_agent",
    "set_agent_status",
    "update_agent",
    "can_delegate",
    "load_delegate_matrix",
    "seed_from_config",
]
