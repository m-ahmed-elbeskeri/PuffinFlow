"""Compatibility module for the prompts integration."""

# Import functions from other modules to provide backward compatibility
from .ask import ask

# For backward compatibility with __prompt__.ask
__prompt__ = ask