"""Entry point — launches the GUI.

Run with ``python -m secure_messenger_client`` or, after an editable
install, the ``secure-messenger-client`` console script.
"""

from ui.app import App


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
