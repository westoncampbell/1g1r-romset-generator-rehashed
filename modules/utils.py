# Standard library imports
import os  # Interact with operating system (paths, environment, etc.)
import shutil  # High-level file operations (copy, move, delete)
from typing import (
    Any,  # Type hint for any Python object (no type restrictions)
    Iterable,  # Type hint for any iterable object (lists, tuples, generators, etc.)
    List,  # Type hint for list: List[element_type]
    Match,  # Type hint for regex match object (from re.match / re.search)
    Optional,  # Type hint for value that can be either given type or None
    Pattern  # Type hint for compiled regex pattern object
)

TRIM_PREFIX = '(...)'  # Prefix for truncated text


def get_index(
    ls: List[Any],  # List to search
    item: Any,  # Item to find in list
    default: int  # Value to return if item is not found
) -> int:
    # Attempt to execute code that may raise a ValueError
    try:
        # If list is not empty
        if ls:
            # try to find index of item
            return ls.index(item)
        # If list is empty, immediately return default value
        return default
    # If item is not found in list, .index() raises ValueError
    except ValueError:
        # Return default value when item is not present
        return default


def check_in_pattern_list(
    name: str,  # String to test against patterns
    patterns: Iterable[Pattern]  # Iterable of compiled regex Pattern objects
) -> bool:
    # Only proceed if patterns iterable is not empty or None
    if patterns:
        # Loop through each compiled regex pattern in the iterable
        for pattern in patterns:
            # If current pattern matches anywhere in name string
            if pattern.search(name):
                # Return True immediately on first successful match
                return True
    # If no patterns match (or patterns is empty), return False
    return False


def to_int_list(
    string: str,  # Input string whose characters will be converted
    multiplier: int  # Integer factor to multiply each code point by
) -> List[int]:
    # Return list of multiplied code points
    return [multiplier * ord(x) for x in string]


def get(
    ls: List[int],  # List of integers to retrieve from
    index: int  # Position of desired element in list
) -> int:
    # Check if requested index is within the list's bounds
    if index < len(ls):
        # If true, return element at that index
        return ls[index]
    # If index out of range, return 0 as default value
    return 0


def add_padding(
    strings: List[str]  # List of dotted strings (e.g., version numbers)
) -> List[str]:
    # Split each string into parts using '.' as the separator
    parts_list = [s.split('.') for s in strings]

    # Record length of each part for every string
    lengths = [[len(part) for part in parts] for parts in parts_list]

    # Find maximum number of parts across all strings
    max_parts = max([len(parts) for parts in parts_list])

    # For each part position, find maximum length across all strings
    max_lengths = [
        max([get(lenght, i) for lenght in lengths])
        for i in range(0, max_parts)
    ]

    # Loop through each list of parts
    for parts in parts_list:
        # Loop through each part in current list
        for i in range(0, len(parts)):
            # Pad part with leading zeros to match max length for that position
            parts[i] = ('0' * (max_lengths[i] - len(parts[i]))) + parts[i]

    # Rejoin padded parts into dotted strings and return list
    return ['.'.join(parts) for parts in parts_list]


def get_or_default(
    match: Optional[Match],  # Regex match object or None
    default: str  # Value to return if match is None or group is empty
) -> str:
    # If match is not None,
    if match:
        # Extract first capture group
        version = match.group(1)
    else:
        # Otherwise set version to None
        version = None

    # If version is truthy (non-empty string)
    if version:
        # Return version
        return version
    # Otherwise return default value
    return default


def available_columns(
    current_text: str  # Text already present in terminal line
) -> int:
    # Get terminal size, with fallback of 80 columns × 20 rows
    term_size = shutil.get_terminal_size((80, 20))

    # Calculate remaining columns by subtracting text length from total columns
    remaining = term_size.columns - len(current_text)

    # Ensure result is not negative
    return max(0, remaining)


def trim_to(
    obj: Any,  # Object to convert to string
    n: int  # Maximum allowed length of returned string
) -> str:
    # Convert object to its string representation
    text = str(obj)

    # If string is longer than allowed length
    if len(text) > n:
        # Return TRIM_PREFIX followed by last (n - len(TRIM_PREFIX)) characters
        return '%s%s' % (TRIM_PREFIX, text[-(n - len(TRIM_PREFIX)):])

    # If string is within allowed length, return it unchanged
    return text


def is_valid(
    x: str  # String to validate
) -> bool:
    # Ensure string is not empty or None
    if not x:
        # Return False if string is empty or None
        return False

    # Check if string contains only whitespace characters
    if x.isspace():
        # Return False if string is only whitespace
        return False

    # Return True if string has at least one non-whitespace character
    return True

def clear_screen():
    # Check operating system type
    if os.name == 'nt':  # Windows operating system
        # Use the 'cls' command
        command = 'cls'
    else:
        # Otherwise, assume Unix-like system and use 'clear' command
        command = 'clear'

    # Execute chosen clear command in system shell
    exit_code = os.system(command)

    # If system command failed (non-zero exit code)
    if exit_code != 0:
        # fall back to ANSI escape codes to clear screen and reset cursor position
        print("\033[2J\033[H", end="")
