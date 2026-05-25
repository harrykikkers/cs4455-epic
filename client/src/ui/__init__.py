"""CustomTkinter GUI.

``app.py`` owns the window and frame manager; ``login_frame`` and
``register_frame`` are the auth screens; ``main_frame`` is the (currently
monolithic) chat UI. ``inbox_frame``/``compose_frame``/``message_frame``/
``widgets`` are the planned decomposition of ``main_frame`` — see the
README *Project Structure*.
"""

from .app import App

__all__ = ["App"]
