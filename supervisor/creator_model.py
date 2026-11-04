"""Compatibility facade for the Creator hypothesis model.

v0.8.2.1 semantic-model hotfix keeps the public creator_model imports stable
while routing updates through the separated Creator/Supervisor/World layer.
"""

from .semantic_models import load_creator_model, update_semantic_models


def update_creator_model(root, config, state, trigger_text, agent_reply=''):
    return update_semantic_models(root, config, state, trigger_text, agent_reply).get('creator', {})
