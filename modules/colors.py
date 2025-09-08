# modules/colors.py

USE_COLORS: bool = True  # ANSI colors flag

if USE_COLORS:
    # Regular (non-bold) colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright / High-intensity colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Formatting
    RESET = "\033[0m"
    BOLD = "\033[1m"
else:
    # Empty values
    BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = \
    BRIGHT_BLACK = BRIGHT_RED = BRIGHT_GREEN = BRIGHT_YELLOW = BRIGHT_BLUE = \
    BRIGHT_MAGENTA = BRIGHT_CYAN = BRIGHT_WHITE = RESET = BOLD = ""
