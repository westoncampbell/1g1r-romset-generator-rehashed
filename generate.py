#!/usr/bin/python3

# Standard library imports
import atexit  # Register functions to run automatically at program exit
import getopt  # Parse command-line options and arguments (POSIX style)
import glob  # Find files matching Unix shell-style wildcards
import hashlib  # Create and work with secure hash functions (MD5, SHA, etc.)
import os  # Interact with operating system (paths, environment, etc.)
import re  # Work with regular expressions for pattern matching
import shutil  # High-level file operations (copy, move, delete)
import ssl  # Manage SSL/TLS encryption for network connections
import sys  # Access system-specific parameters and functions
import tempfile  # Create temporary files and directories
import textwrap  # Format and wrap text to given width
import urllib.parse  # Parse and build URLs
import urllib.request  # Open and retrieve URLs
from io import BufferedIOBase  # Base class for binary I/O streams
from pathlib import Path  # Object-oriented filesystem paths
from threading import current_thread  # Get currently executing thread object
from typing import (
    Callable,  # Type hint for function or lambda, with specified argument and return types
    Dict,  # Type hint for dictionary: Dict[key_type, value_type]
    IO,  # Generic type hint for file-like objects (binary or text)
    List,  # Type hint for list: List[element_type]
    Match,  # Type hint for regex match object (from re.match / re.search)
    Optional,  # Type hint for value that can be either given type or None
    Pattern,  # Type hint for compiled regex pattern object
    TextIO,  # Type hint for text file-like objects (read/write strings)
    Union  # Type hint for value that can be one of several types
)
from zipfile import (
    is_zipfile,  # Check if file is valid ZIP archive
    ZipFile,  # Class for reading, writing, and extracting ZIP files
    ZipInfo  # Class holding metadata about single file in ZIP archive
)

# Local module imports
from modules import (
    colors,  # Custom module providing ANSI color codes and formatting constants
    datafile,  # Custom XML parser module for datafile format
    header  # Custom module for parsing and applying XML-based header rules
)
from modules.classes import (
    CustomJsonEncoder,  # JSON encoder for GameEntry, Score, rom, and paths
    FileData,  # Simple container for file size and path
    GameEntry,  # Represents game with metadata, ROM list, and score
    GameEntryKeyGenerator,  # Builds sort/filter keys for GameEntry objects
    IndexedThread,  # Thread subclass with index attribute
    MultiThreadedProgressBar,  # Thread-safe, multi-line progress bar
    RegionData,  # Region code, regex pattern, and language list
    Score  # Numeric scoring for region, language, and release flags
)
from modules.header import Rule  # Class for defining and applying byte-level file tests and transformations
from modules.utils import (
    add_padding,  # Zero‑pad dotted‑string segments for aligned sorting
    available_columns,  # Get remaining terminal columns after printing text
    check_in_pattern_list,  # True if name matches any regex in list
    get_index,  # Safe list.index() with default fallback
    get_or_default,  # Return regex group(1) or default string
    is_valid,  # True if string is non‑empty and not whitespace
    to_int_list,  # Convert string to list of ints (char codes × multiplier)
    trim_to  # Truncate string to fit width, with prefix
)

__version__: str = '20250912.0' # Script version

PROGRESSBAR: Optional[MultiThreadedProgressBar] = None  # Progress bar instance

FOUND_PREFIX: str = f'{colors.BRIGHT_CYAN}Found:{colors.RESET} '  # Prefix for file discovery messages

THREADS: int = 4  # Number of I/O threads for file processing

CHUNK_SIZE: int = (32 * 1024 * 1024)  # 32 MiB - Buffered I/O chunk size

MAX_FILE_SIZE: int = (256 * 1024 * 1024)  # 256 MiB - Max file size for header processing

FILE_PREFIX: str = 'file:'  # Prefix for file path arguments
URL_PREFIX: str = 'url:'  # Prefix for URL path arguments

UNSELECTED: int = 10000  # Score value for unselected regions
NOT_PRERELEASE: str = "Z"  # Default value for non-prerelease ROMs

RULES: List[Rule] = []  # Header processing rules from DAT files

LOG_FILE: Optional[TextIO] = None  # Log file handle for output

JSON_ENCODER: CustomJsonEncoder = CustomJsonEncoder()  # JSON encoder instance

DEBUG: bool = False  # Debug mode flag

NO_LOG: bool = False  # Log file creation flag

TEMP_FILES: List[str] = []  # List of temporary files to delete on exit

CLEAR_SCREEN: bool = False  # Clear screen flag

ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')  # Define ANSI characters

# Enable ANSI escape sequence support on Windows
if os.name == 'nt':  # Windows operating system
    try:
        # Import Windows DLL interface for system calls
        from ctypes import windll

        # Access Windows kernel32 DLL for console operations
        kernel32 = windll.kernel32

        # Console output mode flags from WinAPI (wincon.h)
        ENABLE_PROCESSED_OUTPUT = 0x0001  # Process control chars
        ENABLE_WRAP_AT_EOL_OUTPUT = 0x0002  # Auto wrap at width
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004  # Enable ANSI

        # Windows API constants
        STD_OUTPUT_HANDLE = -11
        INVALID_HANDLE_VALUE = -1

        # Combine flags using bitwise OR to enable all features
        console_mode_flags = (  # Result: 0x0007 (decimal 7)
            ENABLE_PROCESSED_OUTPUT |
            ENABLE_WRAP_AT_EOL_OUTPUT |
            ENABLE_VIRTUAL_TERMINAL_PROCESSING
        )

        # Get handle for standard output stream
        stdout_handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)

        # Verify valid handle before proceeding
        if stdout_handle != INVALID_HANDLE_VALUE:
            # Apply console mode settings to enable ANSI support
            kernel32.SetConsoleMode(stdout_handle, console_mode_flags)

    except (ImportError, AttributeError, OSError):
        # Silently fail if ANSI support cannot be enabled
        pass

# Clear screen if flag is True
if CLEAR_SCREEN:
    # Clear screen
    clear_screen()


def visible_len(s):
    # Remove ANSI escape sequences, then get length
    return len(ANSI_ESCAPE.sub('', s))


def color_ljust(s, width):
    # Calculate visible length of string (excluding ANSI codes)
    visible = visible_len(s)

    # Determine how much padding is needed to reach desired width
    padding = width - visible

    # If padding is positive, append spaces to string
    if padding > 0:
        return s + ' ' * padding

    # If no padding is needed, return the string as-is
    return s


def cleanup_temp_files() -> None:
    # Iterate over temporary file paths
    for temp_file in TEMP_FILES:
        try:
            # Delete temporary file
            Path(temp_file).unlink(missing_ok=True)  # Prevent error messages
        except Exception:
            # Ignore errors
            pass


# Register cleanup function to run on script exit
atexit.register(cleanup_temp_files)

# Country and Region codes with matching patterns and languages
COUNTRY_REGION_CORRELATION = [
    RegionData('ARG', re.compile(r'(Argentina)', re.IGNORECASE), ['es']),
    RegionData('ASI', re.compile(r'(Asia)', re.IGNORECASE), ['zh']),
    RegionData('AUS', re.compile(r'(Australia)', re.IGNORECASE), ['en']),
    RegionData('BRA', re.compile(r'(Brazil)', re.IGNORECASE), ['pt']),
    RegionData('CAN', re.compile(r'(Canada)', re.IGNORECASE), ['en', 'fr']),
    RegionData('CHN', re.compile(r'(China)', re.IGNORECASE), ['zh']),
    RegionData('COL', re.compile(r'(Colombia)', re.IGNORECASE), ['es']),
    RegionData('DAN', re.compile(r'(Denmark)', re.IGNORECASE), ['da']),
    RegionData('EUR', re.compile(r'(Europe)', re.IGNORECASE), ['en']),
    RegionData('FIN', re.compile(r'(Finland)', re.IGNORECASE), ['fi']),
    RegionData('FRA', re.compile(r'(France)', re.IGNORECASE), ['fr']),
    RegionData('GER', re.compile(r'(Germany)', re.IGNORECASE), ['de']),
    RegionData('GRE', re.compile(r'(Greece)', re.IGNORECASE), ['el']),
    RegionData('HK', re.compile(r'(Hong Kong)', re.IGNORECASE), ['zh']),
    RegionData('ITA', re.compile(r'(Italy)', re.IGNORECASE), ['it']),
    RegionData('JPN', re.compile(r'(Japan)', re.IGNORECASE), ['ja']),
    RegionData('KOR', re.compile(r'(Korea)', re.IGNORECASE), ['ko']),
    RegionData('LAM', re.compile(r'(Latin America)', re.IGNORECASE), ['en', 'es']),
    RegionData('MEX', re.compile(r'(Mexico)', re.IGNORECASE), ['es']),
    RegionData('HOL', re.compile(r'(Netherlands)', re.IGNORECASE), ['nl']),
    RegionData('NZ', re.compile(r'(New Zealand)', re.IGNORECASE), ['en']),
    RegionData('NOR', re.compile(r'(Norway)', re.IGNORECASE), ['no']),
    RegionData('PER', re.compile(r'(Peru)', re.IGNORECASE), ['es']),
    RegionData('POR', re.compile(r'(Portugal)', re.IGNORECASE), ['pt']),
    RegionData('RUS', re.compile(r'(Russia)', re.IGNORECASE), ['ru']),
    RegionData('SCA', re.compile(r'(Scandinavia)', re.IGNORECASE), ['en']),
    RegionData('SPA', re.compile(r'(Spain)', re.IGNORECASE), ['es']),
    RegionData('SWE', re.compile(r'(Sweden)', re.IGNORECASE), ['sv']),
    RegionData('TAI', re.compile(r'(Taiwan)', re.IGNORECASE), ['zh']),
    RegionData('UK', re.compile(r'(United Kingdom)', re.IGNORECASE), ['en']),
    RegionData('USA', re.compile(r'(USA)', re.IGNORECASE), ['en']),
    RegionData('UNK', re.compile(r'(Unknown)', re.IGNORECASE), ['en']),
    RegionData('WOR', re.compile(r'(World)', re.IGNORECASE), ['en'])
]

# Regular expression patterns for parsing game metadata tags and attributes
AFTERMARKET_REGEX = re.compile(r'\(Aftermarket\)', re.IGNORECASE)
ALPHABETICAL_REGEX = re.compile(r'^[a-z]', re.IGNORECASE)
BAD_REGEX = re.compile(r'\[b\]', re.IGNORECASE)
BETA_REGEX = re.compile(r'\(Beta(?:\s*([a-z0-9.]+))?\)', re.IGNORECASE)
BIOS_REGEX = re.compile(r'\[BIOS\]', re.IGNORECASE)
DEBUG_REGEX = re.compile(r'\(Debug(?:\s*Version)?\)', re.IGNORECASE)
DEMO_REGEX = re.compile(
    r'\(Demo(?:\s*([a-z0-9.]+))?\)|'
    r'\((Multiplayer|Singleplayer|Labeled) Demo\)|'
    r'\(Trial(?:\s*([a-z0-9.]+))?\)|'
    r'\(Tech Demo(?:,)?.*?\)|'
    r'\((?:GameCube\s*)?Preview\)',
    re.IGNORECASE
)
ENHANCEMENT_CHIP_REGEX = re.compile(r'\(Enhancement\s*Chip\)', re.IGNORECASE)
HOMEBREW_REGEX = re.compile(r'\(Homebrew\)', re.IGNORECASE)
KIOSK_REGEX = re.compile(
    r'\(Kiosk(?:,)?.*?\)|'
    r'\(Wi-Fi Kiosk(?:,)?.*?\)',
    re.IGNORECASE
)
LANGUAGES_REGEX = re.compile(r'\(([a-z]{2}(?:[,+][a-z]{2})*)\)', re.IGNORECASE)
PIRATE_REGEX = re.compile(r'\(Pirate\)', re.IGNORECASE)
PROGRAM_REGEX = re.compile(
    r'\((?:Test\s*)?Program\)|'
    r'\(SDK Build\)|'
    r'\(DS (?:Expansion|Cheat) Cartridge\)',
    re.IGNORECASE
)
PROMO_REGEX = re.compile(r'\(Promo\)', re.IGNORECASE)
PROTO_REGEX = re.compile(
    r'\(Proto(?:\s*([a-z0-9.]+))?\)|'
    r'\(Possible Proto\)|'
    r'\(Prototype(?:\s*(.*?))?\)',
    re.IGNORECASE
)
REV_REGEX = re.compile(r'\(Rev\s*([a-z0-9.]+)\)', re.IGNORECASE)
SAMPLE_REGEX = re.compile(r'\(Sample(?:\s*([a-z0-9.]+))?\)', re.IGNORECASE)
SECTIONS_REGEX = re.compile(r'\(([^()]+)\)')
UNL_REGEX = re.compile(r'\(Unl\)', re.IGNORECASE)
VERSION_REGEX = re.compile(r'\(v\s*([a-z0-9.]+)\)', re.IGNORECASE)
ZIP_REGEX = re.compile(r'\.zip$', re.IGNORECASE)


def human_readable_size(size: Union[int, float]) -> str:
    # If size is zero
    if size == 0:
        # Return "0 B"
        return "0 B"

    # Iterate over units from bytes up to yottabytes
    for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']:
        # If size is smaller than 1024 in current unit
        if size < 1024.0:
            # Return size formatted to two decimal places with unit
            return f"{size:.2f} {unit}"
        # Otherwise, convert size to next larger unit
        size /= 1024.0

    # Fallback if size exceeds all predefined units
    return f"{size:.2f} YiB"


def add_extension(file_name: str, file_extension: str) -> str:
    # If file extension provided
    if file_extension:
        # Return file name with dot and extension appended
        return file_name + '.' + file_extension
    # If no file extension provided, return file name unchanged
    return file_name


def parse_revision(name: str) -> str:
    # Return matched revision or zero
    return get_or_default(REV_REGEX.search(name), '0')


def parse_version(name: str) -> str:
    # Return matched version or zero
    return get_or_default(VERSION_REGEX.search(name), '0')


def parse_prerelease(match: Optional[Match]) -> str:
    # Return matched prerelease or default value
    return get_or_default(match, NOT_PRERELEASE)


def parse_region_data(name: str) -> List[RegionData]:
    # Initialize empty list to store matched region data
    parsed = []

    # Use pattern to find all matching sections
    for section in SECTIONS_REGEX.finditer(name):
        # Split matched section by commas
        elements = [element.strip() for element in section.group(1).split(',')]

        # For each element extracted from section
        for element in elements:
            # Check each region_data item in COUNTRY_REGION_CORRELATION
            for region_data in COUNTRY_REGION_CORRELATION:
                # If region_data has regex pattern and fully matches element
                if region_data.pattern and region_data.pattern.fullmatch(element):
                    # Add matched region_data to parsed list
                    parsed.append(region_data)

    # Return list of all matched region data objects
    return parsed


def parse_languages(name: str) -> List[str]:
    # Search for language section using pattern
    lang_matcher = LANGUAGES_REGEX.search(name)

    # Initialize empty list to hold parsed language codes
    languages = []

    # If language section is found
    if lang_matcher:
        # Split matched group by commas to separate language entries
        for entry in lang_matcher.group(1).split(','):
            # Further split entries by '+' to handle combined languages
            for lang in entry.split('+'):
                # Add language code to list
                languages.append(lang.lower())

    # Return list of parsed language codes
    return languages


def get_region_data(code: str) -> Optional[RegionData]:
    # Convert code to uppercase
    code = code.upper() if code else code

    # Initialize variable to hold matched region data
    region_data = None

    # Search for matching region by code
    for r in COUNTRY_REGION_CORRELATION:
        # Check if current RegionData code matches given code
        if r.code == code:
            # Assign RegionData to region_data
            region_data = r

            # Stop searching once match is found
            break

    # If no matching region found
    if not region_data:
        # Log warning about unrecognized region code
        log(f"Unrecognized region ({code})")

        # Create new RegionData instance with empty or default values
        region_data = RegionData(code, None, [])

        # Append new region data to global list
        COUNTRY_REGION_CORRELATION.append(region_data)

    # Return found or newly created RegionData object
    return region_data


def get_languages(region_data_list: List[RegionData]) -> List[str]:
    # Initialize empty list to hold unique languages
    languages = []

    # Iterate over each RegionData object in list
    for region_data in region_data_list:
        # Iterate over each language associated with region
        for language in region_data.languages:
            # If language not existing in list
            if language not in languages:
                # Add language to list
                languages.append(language)

    # Return list of unique languages found across all regions
    return languages


def is_present(code: str, region_data: List[RegionData]) -> bool:
    # Iterate over each RegionData object in list
    for r in region_data:
        # Check if current RegionData code matches given code
        if r.code == code:
            # If match is found, return True immediately
            return True

    # If no match found after checking all entries, return False
    return False


def validate_dat(file: Path, use_hashes: bool) -> None:
    # Parse DAT file into structured object
    root = datafile.parse(file, silence=True)  # Suppress parse warnings

    # Flag to track presence of 'cloneof' entries
    has_cloneof = False

    # Flag to track presence of missing SHA-1 hashes
    lacks_sha1 = False

    # String to accumulate names of games missing SHA-1 hashes
    offending_entry = ''

    # Check each game in parsed DAT
    for game in root.game:
        # Check if game has 'cloneof' field
        if game.cloneof:
            # Flag game as clone
            has_cloneof = True

            # Stop checking more games since clone found
            break

    # Check each ROM in every game
    for game in root.game:
        # For each ROM inside current game
        for game_rom in game.rom:
            # Check if SHA-1 hash is missing
            if not game_rom.sha1:
                # If '--force' flag is used to supress errors
                if '--force' in sys.argv:
                    # Set lacks_sha1 flag to False
                    lacks_sha1 = False
                else:
                    # Set lacks_sha1 flag to True
                    lacks_sha1 = True

                    # Record game name
                    offending_entry += '\n - ' + game.name

                    # Stop checking ROMs for this game
                    break

    # If hashes required but some SHA-1 digests missing
    if use_hashes and lacks_sha1:
        # Error message
        print(f"{colors.BRIGHT_RED}[ERROR] No SHA‑1 digests found in DAT for: {offending_entry}{colors.RESET}")

        # Prompt user to confirm continuing
        print(f"\n{colors.BRIGHT_BLUE}[PROMPT] Continue anyway? (y/n){colors.RESET}", file=sys.stderr)

        # Get user input from console
        answer = input()

        # If user input not 'y' or 'Y'
        if answer.strip() not in ('y', 'Y'):
            # Print exiting message
            print(f"{colors.BRIGHT_RED}[ERROR] Operation aborted.{colors.RESET}", file=sys.stderr)

            # Exit script
            sys.exit()
        else:
            # Force disable flag
            lacks_sha1 = False

            # Clear to end of line
            print(f"\033[K")


    # If no 'cloneof' entries found
    if not has_cloneof:
        # Inform user this appears to be Standard DAT
        print(f"{colors.BRIGHT_YELLOW}[WARNING] DAT appears to be Standard (no valid clone relationships). Parent/Clone XML DAT required for 1G1R ROM set generation.{colors.RESET}", file=sys.stderr)

        # Inform user standard DAT can be used for hash-based renaming
        if use_hashes:
            print(f"{colors.BRIGHT_YELLOW}[WARNING] Standard DAT sufficient for hash-based file renaming.{colors.RESET}\n", file=sys.stderr)

        # If '--force' flag not present
        if not '--force' in sys.argv:
            # Prompt user to confirm continuing
            print(f"\n{colors.BRIGHT_BLUE}[PROMPT] Continue anyway? (y/n){colors.RESET}", file=sys.stderr)

            # Get user input from console
            answer = input()

            # If user input not 'y' or 'Y'
            if answer.strip() not in ('y', 'Y'):
                # Print exiting message
                print(f"{colors.BRIGHT_RED}[ERROR] Operation aborted.{colors.RESET}", file=sys.stderr)

                # Exit script
                sys.exit()
            else:
                # Clear to end of line
                print(f"\033[K")
        else:
            # Clear to end of line
            print(f"\033[K")


def parse_games(
    file: Path,
    filter_bios: bool,
    filter_program: bool,
    filter_enhancement_chip: bool,
    filter_pirate: bool,
    filter_bad: bool,
    filter_aftermarket: bool,
    filter_homebrew: bool,
    filter_kiosk: bool,
    filter_promo: bool,
    filter_debug: bool,
    filter_unlicensed: bool,
    filter_unlicensed_strict: bool,
    filter_proto: bool,
    filter_beta: bool,
    filter_demo: bool,
    filter_sample: bool,
    exclude: List[Pattern]
) -> Dict[str, List[GameEntry]]:
    # Initialize dictionary to store parsed games keyed by parent name
    games = {}

    # Parse datafile from given file
    root = datafile.parse(file, silence=True)  # Suppress output

    # Loop through each game entry by index
    for input_index in range(0, len(root.game)):
        # Get current game object
        game = root.game[input_index]

        # Pre-match regex for prerelease indicators in game name
        beta_match = BETA_REGEX.search(game.name)
        demo_match = DEMO_REGEX.search(game.name)
        sample_match = SAMPLE_REGEX.search(game.name)
        proto_match = PROTO_REGEX.search(game.name)

        # Apply filters: skip game if matches excluded categories
        if (  # --no-bios
            filter_bios
            and BIOS_REGEX.search(game.name)
        ): continue

        if (  # --no-unlicensed
            filter_unlicensed
            and UNL_REGEX.search(game.name)
            and not AFTERMARKET_REGEX.search(game.name)
            and not HOMEBREW_REGEX.search(game.name)
        ): continue

        if (  # --no-unlicensed-strict
            filter_unlicensed_strict
            and UNL_REGEX.search(game.name)
        ): continue

        if (  # --no-pirate
            filter_pirate
            and PIRATE_REGEX.search(game.name)
        ): continue

        if (  # --no-bad
            filter_bad
            and BAD_REGEX.search(game.name)
        ): continue

        if (  # --no-aftermarket
            filter_aftermarket
            and AFTERMARKET_REGEX.search(game.name)
        ): continue

        if (  # --no-homebrew
            filter_homebrew
            and HOMEBREW_REGEX.search(game.name)
        ): continue

        if (  # --no-kiosk
            filter_kiosk
            and KIOSK_REGEX.search(game.name)
        ): continue

        if (  # --no-promo
            filter_promo
            and PROMO_REGEX.search(game.name)
        ): continue

        if (  # --no-debug
            filter_debug
            and DEBUG_REGEX.search(game.name)
        ): continue

        if (  # --no-program
            filter_program
            and PROGRAM_REGEX.search(game.name)
        ): continue

        if (  # --no-enhancement-chip
            filter_enhancement_chip
            and ENHANCEMENT_CHIP_REGEX.search(game.name)
        ): continue

        if (  # --no-beta
            filter_beta
            and beta_match
        ): continue

        if (  # --no-demo
            filter_demo
            and demo_match
        ): continue

        if (  # --no-sample
            filter_sample
            and sample_match
        ): continue

        if (  # --no-proto
            filter_proto
            and proto_match
        ): continue

        # Exclude games where names match any pattern in exclude list
        if check_in_pattern_list(game.name, exclude):
            continue

        # Determine if game is parent (not clone)
        is_parent = not game.cloneof

        # Determine if game is marked bad via regex
        is_bad = bool(BAD_REGEX.search(game.name))

        # Parse prerelease info from matched regexes
        beta = parse_prerelease(beta_match)
        demo = parse_prerelease(demo_match)
        sample = parse_prerelease(sample_match)
        proto = parse_prerelease(proto_match)

        # Determine if game is any kind of prerelease
        is_prerelease = bool(
            beta_match
            or demo_match
            or sample_match
            or proto_match
        )

        # Parse revision info from game name
        revision = parse_revision(game.name)

        # Parse version info from game name
        version = parse_version(game.name)

        # Parse region info from game name
        region_data = parse_region_data(game.name)

        # Append region info from releases not already in region_data
        for release in game.release:
            # Check if release has region and not already present
            if release.region and not is_present(release.region, region_data):
                # Append new region data for release region
                region_data.append(get_region_data(release.region))

        # Parse language info from game name
        languages = parse_languages(game.name)

        # If no languages found
        if not languages:
            # Get languages from region data
            languages = get_languages(region_data)

        # Determine parent name (cloneof if present, else game name)
        parent_name = game.cloneof if game.cloneof else game.name

        # Get list of region codes from region data
        region_codes = [rd.code for rd in region_data]

        # Initialize list to hold GameEntry objects for each region
        game_entries: List[GameEntry] = []

        # Create GameEntry for each region code
        for region in region_codes:
            game_entries.append(
                GameEntry(
                    is_bad,
                    is_prerelease,
                    region,
                    languages,
                    input_index,
                    revision,
                    version,
                    sample,
                    demo,
                    beta,
                    proto,
                    is_parent,
                    game.name,
                    game.rom if game.rom else []
                )
            )

        # Add game entries to games dict under parent name
        if game_entries:
            # If parent name not yet a key
            if parent_name not in games:
                # Create new entry list
                games[parent_name] = game_entries
            else:
                # Extend existing list of entries for parent
                games[parent_name].extend(game_entries)
        else:
            # Log warning if no recognizable regions found
            log(f"[{game.name}]: No recognizable regions found")

        # if no ROMs present in dat file for game
        if not game.rom:
            # Log warning
            log(f"[{game.name}]: No ROMs found in DAT file")

    # Return dictionary mapping parent names to lists of GameEntry objects
    return games


def pad_values(
    games: List[GameEntry],
    get_function: Callable[[GameEntry], str],
    set_function: Callable[[GameEntry, str], None]
) -> None:
    # Create list of padded strings for each game
    padded = add_padding([get_function(g) for g in games])

    # Iterate over all indices in padded list
    for i in range(0, len(padded)):
        # Update original game entry with padded string
        set_function(games[i], padded[i])


def language_value(
    languages: List[str],
    weight: int,
    selected_languages: List[str]
) -> int:
    # Calculate weighted negative sum of positions of each selected language
    return sum([
        (get_index(selected_languages, lang, -1) + 1) * weight * -1
        for lang in languages])


def get_header_rules(root: datafile) -> List[Rule]:
    # Check if 'clrmamepro' section exists in header
    if root.header.clrmamepro:
        # Check if header filename specified inside 'clrmamepro' section
        if root.header.clrmamepro.header:
            # Construct path to header file inside 'headers' directory
            header_file = Path('headers', root.header.clrmamepro.header)

            # Check if header file exists on disk
            if header_file.is_file():
                # Parse and return rules from header file
                return header.parse_rules(header_file)
            else:
                # Log warning if header file missing
                log(
                    f"Header file not found {header_file}. "
                    "Hashes may be calculated incorrectly."
                )

                # Return empty list since rules could not be loaded
                return []


def index_files(
        input_dir: Path,
        dat_file: Path
) -> Dict[str, Optional[Path]]:
    # Initialize result dictionary mapping SHA-1 hash to optional Path
    result: Dict[str, Optional[Path]] = {}

    # Flag to indicate checking inside archives
    also_check_archive: bool = False

    # Parse dat file to get root datafile object, suppressing output
    root = datafile.parse(dat_file, silence=True)

    # Use global RULES variable for hashing rules
    global RULES

    # If no rules loaded yet
    if not RULES:
        # Load rules from header in dat file
        RULES = get_header_rules(root)

    # Iterate over each game entry in dat file
    for game in root.game:
        # Iterate over each ROM entry in current game
        for rom_entry in game.rom:
            # Initialize SHA-1 hash key in result dictionary
            result[rom_entry.sha1.lower()] = None

            # Check if ROM name matches ZIP archive regex and update flag
            also_check_archive |= bool(ZIP_REGEX.search(rom_entry.name))

    # Print scanning directory message to stderr (with erase line sequence)
    print(f"{colors.BRIGHT_CYAN}Scanning directory:{colors.RESET} {input_dir}\033[K\n", file=sys.stderr)

    # List to hold file data objects with size and path
    files_data = []

    # Recursively iterate all files in input directory
    for full_path in input_dir.rglob('*'):
        # Check if not regular file
        if not full_path.is_file():
            # Skip file
            continue
        try:
            # Print found file progress line with relative path
            print(
                f"{FOUND_PREFIX}"
                f"{trim_to(
                    full_path.relative_to(input_dir),
                    available_columns(FOUND_PREFIX) - 2
                )}\033[K",
                end='\r',
                file=sys.stderr
            )

            # Get file size in bytes
            file_size = full_path.stat().st_size

            # Append FileData object to files_data list
            files_data.append(FileData(file_size, full_path))
        except OSError as e:
            # Print error message on failure to read file info
            print(f"{colors.BRIGHT_RED}Error while reading file:{colors.RESET} {e}\033[K", file=sys.stderr)

    # Sort files_data list
    files_data.sort(key=FileData.get_size, reverse=True)

    # Print how many files found
    print(f"{FOUND_PREFIX}{len(files_data)} File(s)\033[K", file=sys.stderr)

    # If files found to process
    if files_data:
        # Declare global PROGRESSBAR to manage progress display
        global PROGRESSBAR

        # Create multi-threaded progress bar
        PROGRESSBAR = MultiThreadedProgressBar(
            len(files_data),  # Total files
            THREADS,  # Thread count
            prefix=f'{colors.BRIGHT_CYAN}Calculating hashes{colors.RESET}')  # Prefix string

        # Initialize progress bar
        PROGRESSBAR.init()

        # Define worker function for threads to process files with progress
        def process_thread_with_progress(
                shared_files_data: List[FileData],
                shared_result_data: List[Dict[str, Path]]
        ) -> None:
            # Get current running thread
            curr_thread = current_thread()

            # Check if current thread is not IndexedThread
            if not isinstance(curr_thread, IndexedThread):
                # Exit with error message
                sys.exit(f"{colors.BRIGHT_RED}[ERROR] Bad thread type. Expected {IndexedThread}{colors.RESET}")

            # Loop indefinitely until no more files
            while True:
                try:
                    # Pop next file data from shared list
                    next_file = shared_files_data.pop(0)

                    # Print current thread progress with relative file path
                    PROGRESSBAR.print_thread(
                        curr_thread.index,
                        next_file.path.relative_to(input_dir))

                    # Process file and append result to shared results list
                    shared_result_data.append(process_file(
                        next_file,
                        also_check_archive))

                    # Print updated progress bar
                    PROGRESSBAR.print_bar()

                except IndexError:
                    # When no more files, print thread done message
                    PROGRESSBAR.print_thread(curr_thread.index, f"{colors.BRIGHT_GREEN}DONE{colors.RESET}")

                    # Exit loop
                    break

        # List to hold all thread objects
        threads = []

        # List to hold partial results from threads
        intermediate_results = []

        # Create and start THREADS number of worker threads
        for i in range(0, THREADS):
            # Create IndexedThread with index and target function
            t = IndexedThread(
                index=i,
                target=process_thread_with_progress,
                args=[files_data, intermediate_results],
                daemon=True)

            # Start thread
            t.start()

            # Add thread to threads list
            threads.append(t)

        # Wait for all threads to finish
        for t in threads:
            t.join()

        # Print newline after progress bar finishes
        print('\n', file=sys.stderr)

        # Merge all intermediate results into final result dictionary
        for intermediate_result in intermediate_results:
            # Iterate over each key-value pair in intermediate result dict
            for key, value in intermediate_result.items():

                # Check if key exists in main result dictionary
                if key in result:
                    # Check if current value is None or not a ZIP file
                    if not (result[key] and is_zipfile(result[key])):
                        # Assign or overwrite value for key in result dictionary
                        result[key] = value

                    # Assign or overwrite value for key in result dictionary
                    result[key] = value

    # Return dictionary mapping SHA-1 hashes to file paths (or None)
    return result


# noinspection PyBroadException
def process_file(
    file_data: FileData,
    also_check_archive: bool
) -> Dict[str, Path]:
    # Get full path to file
    full_path = file_data.path

    # Initialize empty dictionary to store hash digest -> file path mappings
    result: Dict[str, Path] = {}

    # Check if file is ZIP archive
    is_zip = is_zipfile(full_path)

    # If file is ZIP archive
    if is_zip:
        try:
            # Open ZIP archive for reading
            with ZipFile(full_path) as compressed_file:
                # Get list of all files and directories inside archive
                infos: List[ZipInfo] = compressed_file.infolist()

                # Iterate over each item in archive
                for file_info in infos:
                    # Check if directory
                    if file_info.is_dir():
                        # Skip directory
                        continue

                    # Get size of current file inside archive
                    file_size = file_info.file_size

                    # Open internal file for reading
                    with compressed_file.open(file_info) as internal_file:
                        # Compute hash digest of file contents
                        digest = compute_hash(file_size, internal_file)

                        # Map computed digest to archive's full path
                        result[digest] = full_path

                        # If debugging enabled
                        if DEBUG:
                            # Log hash and file info
                            log(
                                f"[DEBUG] Scan result for file "
                                f"[{full_path}:{file_info.filename}]: {digest}"
                            )
        except Exception as e:
            # Print error message for any exceptions
            print(
                f"{colors.BRIGHT_RED}[ERROR] Error while reading file [{full_path}]:{colors.RESET} {e}\033[K",
                file=sys.stderr
            )

    # If file is not ZIP archive, or want to check archive as a whole
    if not is_zip or also_check_archive:
        try:
            # Get size of full file on disk
            file_size: int = full_path.stat().st_size

            # Open file for reading in binary mode
            with full_path.open('rb') as uncompressed_file:

                # Compute hash digest of full file
                digest = compute_hash(file_size, uncompressed_file)

                # If debugging enabled
                if DEBUG:
                    # Log hash and file info
                    log(f"[DEBUG] Scan result for file [{full_path}]: {digest}")

                # If digest not in result, or existing mapping is ZIP file
                if digest not in result or (result[digest] and is_zipfile(result[digest])):
                    # Update result dictionary to map digest to current file path
                    result[digest] = full_path
        except Exception as e:
            # Print error message for any exceptions
            print(f"{colors.BRIGHT_RED}[ERROR] Error while reading file:{colors.RESET} {e}\033[K", file=sys.stderr)

    # Return dictionary of digest-to-filepath mappings
    return result


def compute_hash(
    file_size: int,
    internal_file: Union[BufferedIOBase, IO[bytes]]
) -> str:
    # Create new SHA-1 hash object
    hasher = hashlib.sha1()

    # Check if RULES exist and file size within allowed max size
    if RULES and file_size <= MAX_FILE_SIZE:
        # Read entire file contents into memory
        file_bytes = internal_file.read()

        # Iterate over each rule in RULES
        for rule in RULES:
            # Test if current rule applies to file bytes
            if rule.test(file_bytes):
                # Modify file bytes by applying rule
                file_bytes = rule.apply(file_bytes)

        # Update hash with (possibly modified) file bytes
        hasher.update(file_bytes)
    else:
        # No rules or file too large
        while True:
            # Read next chunk of file
            chunk = internal_file.read(CHUNK_SIZE)

            # If no more data
            if not chunk:
                # Exit loop
                break

            # Update hash with current chunk
            hasher.update(chunk)

    # Return SHA-1 hex digest
    return hasher.hexdigest().lower()


def main(argv: List[str]):
    # Check if no command line arguments provided
    if not argv:
        # Exit with help message
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] No options or arguments provided{colors.RESET}"))

    try:
        # Parse command line options and arguments using getopt
        opts, args = getopt.getopt(argv, 'hd:r:e:i:Vo:l:w:vD', [
            'help',
            'dat=',
            'regions=',
            'no-bios',
            'no-program',
            'no-enhancement-chip',
            'no-beta',
            'no-demo',
            'no-sample',
            'no-proto',
            'no-pirate',
            'no-bad',
            'no-aftermarket',
            'no-homebrew',
            'no-kiosk',
            'no-promo',
            'no-debug',
            'no-all',
            'no-unlicensed',
            'no-unlicensed-strict',
            'all-regions',
            'early-revisions',
            'early-versions',
            'input-order',
            'extension=',
            'no-scan',
            'input-dir=',
            'prefer=',
            'avoid=',
            'exclude=',
            'exclude-after=',
            'separator=',
            'ignore-case',
            'regex',
            'verbose',
            'output-dir=',
            'languages=',
            'prioritize-languages',
            'language-weight=',
            'prefer-parents',
            'prefer-prereleases',
            'all-regions-with-lang',
            'debug',
            'move',
            'symlink',
            'relative',
            'chunk-size=',
            'threads=',
            'header-file=',
            'max-file-size=',
            'version',
            'only-selected-lang',
            'group-by-first-letter',
            'force'
        ])
    except getopt.GetoptError as e:
        # Exit with help message on getopt errors
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] {e}{colors.RESET}"))

    # Initialize variable to hold DAT file path (or None)
    dat_file: Optional[Path] = None

    # Initialize flag to filter BIOS entries
    filter_bios = False

    # Initialize flag to filter program entries
    filter_program = False

    # Initialize flag to filter enhancement-chip entries
    filter_enhancement_chip = False

    # Initialize flag to filter unlicensed entries (except Aftermarket/Homebrew)
    filter_unlicensed = False

    # Initialize flag to filter unlicensed entries (including Aftermarket/Homebrew)
    filter_unlicensed_strict = False

    # Initialize flag to filter pirate ROMs
    filter_pirate = False

    # Initialize flag to filter bad dumps
    filter_bad = False

    # Initialize flag to filter aftermarket ROMs
    filter_aftermarket = False

    # Initialize flag to filter homebrew ROMs
    filter_homebrew = False

    # Initialize flag to filter kiosk ROMs
    filter_kiosk = False

    # Initialize flag to filter promo ROMs
    filter_promo = False

    # Initialize flag to filter debug ROMs
    filter_debug = False

    # Initialize flag to filter prototypes
    filter_proto = False

    # Initialize flag to filter betas
    filter_beta = False

    # Initialize flag to filter demos
    filter_demo = False

    # Initialize flag to filter sample ROMs
    filter_sample = False

    # Initialize flag to include all regions
    all_regions = False

    # Initialize flag to include all regions but require matching languages
    all_regions_with_lang = False

    # Initialize flag to restrict to only selected languages
    only_selected_lang = False

    # Initialize flag to sort by earliest revision
    revision_asc = False

    # Initialize flag to sort by earliest version
    version_asc = False

    # Initialize verbose logging flag
    verbose = False

    # Initialize flag to disable scanning
    no_scan = False

    # Initialize force flag (skip confirmations)
    force = False

    # Initialize flag to preserve input order
    input_order = False

    # Initialize list of selected region codes
    selected_regions: List[str] = []

    # Initialize file extension string (empty by default)
    file_extension = ""

    # Initialize input directory Path (or None)
    input_dir: Optional[Path] = None

    # Initialize prefer list source string
    prefer_str = ""

    # Initialize exclude list source string
    exclude_str = ""

    # Initialize avoid list source string
    avoid_str = ""

    # Initialize exclude-after list source string
    exclude_after_str = ""

    # Initialize separator character for lists
    sep = ','

    # Initialize ignore-case flag for lists
    ignore_case = False

    # Initialize regex flag for lists
    regex = False

    # Initialize output directory Path (or None)
    output_dir: Optional[Path] = None

    # Initialize selected languages list
    selected_languages: List[str] = []

    # Initialize prioritize languages flag
    prioritize_languages = False

    # Initialize prefer parents flag
    prefer_parents = False

    # Initialize prefer prereleases flag
    prefer_prereleases = False

    # Initialize grouping by first letter flag
    group_by_first_letter = False

    # Initialize language weighting factor
    language_weight = 3

    # Initialize move flag
    move = False

    # Initialize symlink flag
    symlink = False

    # Initialize relative flag
    relative = False

    # Declare global variables and flags this function will use/modify
    global THREADS
    global RULES
    global MAX_FILE_SIZE
    global CHUNK_SIZE
    global DEBUG

    # Iterate over parsed command-line options
    for opt, arg in opts:
        # If help option requested
        if opt in ('-h', '--help'):
            # Print help
            print(help_msg())

            # Exit
            sys.exit()

        # If version option requested
        if opt in ('-v', '--version'):
            # Print version
            print(f"{colors.BRIGHT_CYAN}1G1R ROM Set Generator: Rehashed{colors.RESET} {colors.BRIGHT_YELLOW}({__version__}){colors.RESET}")

            # Exit
            sys.exit()

        # If regions option provided
        if opt in ('-r', '--regions'):
            # Parse comma-separated region codes
            selected_regions = [
                # Validate regions
                x.strip().upper() for x in arg.split(',') if is_valid(x)
            ]

        # If languages option provided
        if opt in ('-l', '--languages'):
            # Parse comma-separated languages
            selected_languages = [
                # Validate languages
                x.strip().lower() for x in reversed(arg.split(',')) if is_valid(x)
            ]

        # If language-weight option provided
        if opt in ('-w', '--language-weight'):
            try:
                # Parse language weight integer
                language_weight = int(arg.strip())

                # Validate language weight positive
                if language_weight <= 0:
                    # Exit with help message if invalid
                    sys.exit(
                        help_msg(f"{colors.BRIGHT_RED}[ERROR] language-weight must be a positive integer{colors.RESET}")
                    )
            except ValueError:
                # Exit with help message if parsing failed
                sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] language-weight has an invalid value{colors.RESET}"))

        # Update prioritize_languages flag if option present
        prioritize_languages |= opt == '--prioritize-languages'

        # Update filter_bios flag if option present
        filter_bios |= opt in ('--no-bios', '--no-all')

        # Update filter_program flag if option present
        filter_program |= opt in ('--no-program', '--no-all')

        # Update filter_enhancement_chip flag if option present
        filter_enhancement_chip |= opt in ('--no-enhancement-chip', '--no-all')

        # Update filter_proto flag if option present
        filter_proto |= opt in ('--no-proto', '--no-all')

        # Update filter_beta flag if option present
        filter_beta |= opt in ('--no-beta', '--no-all')

        # Update filter_demo flag if option present
        filter_demo |= opt in ('--no-demo', '--no-all')

        # Update filter_sample flag if option present
        filter_sample |= opt in ('--no-sample', '--no-all')

        # Update filter_pirate flag if option present
        filter_pirate |= opt in ('--no-pirate', '--no-all')

        # Update filter_bad flag if option present
        filter_bad |= opt in ('--no-bad', '--no-all')

        # Update filter_aftermarket flag if option present
        filter_aftermarket |= opt in ('--no-aftermarket', '--no-all')

        # Update filter_homebrew flag if option present
        filter_homebrew |= opt in ('--no-homebrew', '--no-all')

        # Update filter_kiosk flag if option present
        filter_kiosk |= opt in ('--no-kiosk', '--no-all')

        # Update filter_promo flag if option present
        filter_promo |= opt in ('--no-promo', '--no-all')

        # Update filter_debug flag if option present
        filter_debug |= opt in ('--no-debug', '--no-all')

        # Update filter_unlicensed flag if option present
        filter_unlicensed |= opt == '--no-unlicensed'

        # Update filter_unlicensed_strict flag if option present
        filter_unlicensed_strict |= opt == '--no-unlicensed-strict'

        # Update all_regions flag if option present
        all_regions |= opt == '--all-regions'

        # Update all_regions_with_lang flag if option present
        all_regions_with_lang |= opt == '--all-regions-with-lang'

        # Update only_selected_lang flag if option present
        only_selected_lang |= opt == '--only-selected-lang'

        # Update revision_asc flag if option present
        revision_asc |= opt == '--early-revisions'

        # Update version_asc flag if option present
        version_asc |= opt == '--early-versions'

        # Update DEBUG flag if debug option present
        DEBUG |= opt in ('-D', '--debug')

        # Update verbose flag if debug or verbose option present
        verbose |= DEBUG or opt in ('-V', '--verbose')

        # Update ignore_case flag if option present
        ignore_case |= opt == '--ignore-case'

        # Update regex flag if option present
        regex |= opt == '--regex'

        # If separator option provided
        if opt == '--separator':
            # Set separator string without whitespace
            sep = arg.strip()

        # Update input_order flag if option present
        input_order |= opt == '--input-order'

        # Update prefer_parents flag if option present
        prefer_parents |= opt == '--prefer-parents'

        # Update prefer_prereleases flag if option present
        prefer_prereleases |= opt == '--prefer-prereleases'

        # If DAT option provided
        if opt in ('-d', '--dat'):
            # Resolve prefer file via helper (URL/file/pattern)
            dat_file = handle_url_or_file_argument(arg, option_name="DAT file", temp_suffix='.dat', validate_direct_path=True, separator=sep)

        # If extension option provided
        if opt in ('-e', '--extension'):
            # Strip and remove leading dot
            file_extension = arg.strip().lstrip('.')

        # Update no_scan flag if option present
        no_scan |= opt == '--no-scan'

        # If prefer file provided
        if opt == '--prefer':
            # Resolve prefer file via helper
            prefer_str = handle_url_or_file_argument(arg, "prefer list", separator=sep)

        # If avoid file provided
        if opt == '--avoid':
            # Resolve avoid file via helper
            avoid_str = handle_url_or_file_argument(arg, "avoid list", separator=sep)

        # If exclude file provided
        if opt == '--exclude':
            # Resolve exclude file via helper
            exclude_str = handle_url_or_file_argument(arg, "exclude list", separator=sep)

        # If exclude-after file provided
        if opt == '--exclude-after':
            # Resolve exclude-after file via helper
            exclude_after_str = handle_url_or_file_argument(arg, "exclude-after list", separator=sep)

        # If input-dir option provided
        if opt in ('-i', '--input-dir'):
            # Expand and create Path
            input_dir = Path(arg.strip()).expanduser()

            # Validate that path is directory
            if not input_dir.is_dir():
                # Exit with error if invalid input directory
                sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Invalid input directory: {input_dir}{colors.RESET}"))

        # If output dir doesn't exist
        if opt in ('-o', '--output-dir'):
            # Expand and create Path for output directory
            output_dir = Path(arg.strip()).expanduser()

            # If output dir doesn't exist
            if not output_dir.is_dir():
                try:
                    # Create directory with parents if necessary
                    output_dir.mkdir(parents=True, exist_ok=True)
                except OSError:
                    # Exit with error if creation failed
                    sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Invalid output directory: {output_dir}{colors.RESET}"))

        # Update move flag if move option present
        move |= opt == '--move'

        # Update symlink flag if symlink option present
        symlink |= opt == '--symlink'

        # Update relative flag if relative option present
        relative |= opt == '--relative'

        # If chunk-size option provided
        if opt == '--chunk-size':
            # Assign CHUNK_SIZE global
            CHUNK_SIZE = int(arg)

        # If threads option provided
        if opt == '--threads':
            # Assign THREADS global
            THREADS = int(arg)

        # If header-file option provided
        if opt == '--header-file':
            # Resolve header file via helper (requires direct path)
            header_file = handle_url_or_file_argument(arg, "header file", temp_suffix='.xml', validate_direct_path=True)

            # Parse rules from header file into RULES
            RULES = header.parse_rules(header_file)

        # If max-file-size option provided
        if opt == '--max-file-size':
            # Assign MAX_FILE_SIZE global
            MAX_FILE_SIZE = int(arg)

        # Update group_by_first_letter flag if option present
        group_by_first_letter |= opt == '--group-by-first-letter'

        # If force option provided
        if opt == '--force':
            # Turn on force mode (skip prompts)
            force = True

    # If scanning enabled but no input directory specified, warn and confirm
    if not no_scan and not input_dir:
        # Print warning that scanning is disabled due to missing input dir
        print(
            f"{colors.BRIGHT_YELLOW}[WARNING] Input directory not specified -- file scanning skipped.{colors.RESET}",
            file=sys.stderr
        )

        # If not forced, ask user whether to continue
        if not force:
            # Prompt user
            print(f"\n{colors.BRIGHT_BLUE}[PROMPT] Continue anyway? (y/n){colors.RESET}", file=sys.stderr)

            # Read user input
            answer = input()

            # If answer is not affirmative, exit
            if answer.strip() not in ('y', 'Y'):
                # Print exiting message
                print(f"{colors.BRIGHT_RED}[ERROR] Operation aborted.{colors.RESET}", file=sys.stderr)

                # Exit script
                sys.exit()
            else:
                # Clear to end of line
                print(f"\033[K")
        else:
            # Clear to end of line
            print(f"\033[K")

    # Determine if file hashing will be used (requires input dir and scan)
    use_hashes = bool(not no_scan and input_dir)

    # Check for invalid combination of extension and scanning
    if file_extension and use_hashes:
        # Exit with help message for invalid combination
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Scanning does not support extensions{colors.RESET}"))

    # Require DAT file to be specified
    if not dat_file:
        # Exit with help message if missing DAT
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] DAT file is required{colors.RESET}"))

    # Require at least one region to be selected
    if not selected_regions:
        # Exit with help message if no regions selected
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Invalid region selection{colors.RESET}"))

    # Validate mutual exclusivity: early-revisions/early-versions vs input-order
    if (revision_asc or version_asc) and input_order:
        # Exit with help message describing conflict
        sys.exit(help_msg(
            f"{colors.BRIGHT_RED}[ERROR] early-revisions and early-versions are mutually exclusive "
            f"with input-order{colors.RESET}"))

    # Validate mutual exclusivity: early-revisions/early-versions vs prefer-parents
    if (revision_asc or version_asc) and prefer_parents:
        # Exit with help message describing conflict
        sys.exit(help_msg(
            f"{colors.BRIGHT_RED}[ERROR] early-revisions and early-versions are mutually exclusive "
            f"with prefer-parents{colors.RESET}"))

    # Validate mutual exclusivity: prefer-parents vs input-order
    if prefer_parents and input_order:
        # Exit with help message describing conflict
        sys.exit(help_msg(
            f"{colors.BRIGHT_RED}[ERROR] prefer-parents is mutually exclusive with input-order{colors.RESET}"))

    # Output directory requires input directory
    if output_dir and not input_dir:
        # Exit with help message
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] output-dir requires an input-dir{colors.RESET}"))

    # ignore-case requires a prefer, avoid, or exclude list to work
    if ignore_case and not prefer_str and not avoid_str and not exclude_str:
        # Exit with help message explaining requirement
        sys.exit(help_msg(
            f"{colors.BRIGHT_RED}[ERROR] ignore-case only works if there's a prefer, "
            f"avoid or exclude list too{colors.RESET}"))

    # regex requires a prefer, avoid, or exclude list to work
    if regex and not prefer_str and not avoid_str and not exclude_str:
        # Exit with help message explaining requirement
        sys.exit(help_msg(
            f"{colors.BRIGHT_RED}[ERROR] regex only works if there's a prefer, avoid or exclude list too{colors.RESET}"))

    # all-regions and all-regions-with-lang are mutually exclusive
    if all_regions and all_regions_with_lang:
        # Exit with help message describing conflict
        sys.exit(help_msg(
            f"{colors.BRIGHT_RED}[ERROR] all-regions is mutually exclusive with all-regions-with-lang{colors.RESET}"))

    # group-by-first-letter requires output directory
    if group_by_first_letter and not output_dir:
        # Exit with help message explaining requirement
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] group-by-first-letter requires an output directory{colors.RESET}"))

    # Validate THREADS is positive integer
    if THREADS <= 0:
        # Exit with help message for invalid thread count
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Number of threads should be > 0{colors.RESET}"))

    # Validate MAX_FILE_SIZE is positive integer
    if MAX_FILE_SIZE <= 0:
        # Exit with help message for invalid max file size
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Maximum file size should be > 0{colors.RESET}"))

    # Parse prefer list file/string into patterns
    try:
        # Parse prefer list using helper
        prefer = parse_list(prefer_str, ignore_case, regex, sep)
    except (re.error, OSError) as e:
        # Exit with help message if parsing fails
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Invalid prefer list: {e}{colors.RESET}"))

    # Parse avoid list file/string into patterns
    try:
        # Parse avoid list using helper
        avoid = parse_list(avoid_str, ignore_case, regex, sep)
    except (re.error, OSError) as e:
        # Exit with help message if parsing fails
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Invalid avoid list: {e}{colors.RESET}"))

    # Parse exclude list file/string into patterns
    try:
        # Parse exclude list using helper
        exclude = parse_list(exclude_str, ignore_case, regex, sep)
    except (re.error, OSError) as e:
        # Exit with help message if parsing fails
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Invalid exclude list: {e}{colors.RESET}"))

    # Parse exclude-after list file/string into patterns
    try:
        # Parse exclude-after list using helper
        exclude_after = parse_list(exclude_after_str, ignore_case, regex, sep)
    except (re.error, OSError) as e:
        # Exit with help message if parsing fails
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Invalid exclude-after list: {e}{colors.RESET}"))

    # Validate DAT file structure and contents
    validate_dat(dat_file, use_hashes)

    # Initialize hash index mapping SHA-1 to optional Path
    hash_index: Dict[str, Optional[Path]] = {}

    # If using hashes and input directory provided
    if use_hashes and input_dir:
        # Create index mapping SHA-1 -> Path by scanning input dir
        hash_index = index_files(input_dir, dat_file)

        # If debug mode
        if DEBUG:
            # Log resulting index as JSON
            log(f"[DEBUG] Scanned files: {JSON_ENCODER.encode(hash_index)}")

    # Parse games from DAT file using filters
    parsed_games = parse_games(
        dat_file,
        filter_bios,
        filter_program,
        filter_enhancement_chip,
        filter_pirate,
        filter_bad,
        filter_aftermarket,
        filter_homebrew,
        filter_kiosk,
        filter_promo,
        filter_debug,
        filter_unlicensed,
        filter_unlicensed_strict,
        filter_proto,
        filter_beta,
        filter_demo,
        filter_sample,
        exclude
    )

    # If verbose mode
    if verbose:
        # Label for region-based ranking
        region_text = 'Best region match'

        # Label for language-based ranking
        lang_text = 'Best language match'

        # Label for parent ROMs criterion
        parents_text = 'Parent ROMs'

        # Label for input order criterion
        index_text = 'Input order'

        # List of filters and their descriptions
        filters = [
            (filter_bios, 'BIOSes'),
            (filter_program, 'Programs'),
            (filter_enhancement_chip, 'Enhancement Chips'),
            (filter_proto, 'Prototypes'),
            (filter_beta, 'Betas'),
            (filter_demo, 'Demos'),
            (filter_sample, 'Samples'),
            (filter_unlicensed, 'Unlicensed ROMs (Except Aftermarket and Homebrew)'),
            (filter_unlicensed_strict, 'Unlicensed ROMs (Including Aftermarket and Homebrew)'),
            (filter_pirate, 'Pirate ROMs'),
            (filter_bad, 'Bad Dump ROMs'),
            (filter_aftermarket, 'Aftermarket ROMs'),
            (filter_homebrew, 'Homebrew ROMs'),
            (filter_kiosk, 'Kiosk ROMs'),
            (filter_promo, 'Promo ROMs'),
            (filter_debug, 'Debug ROMs'),
            (only_selected_lang, 'ROMs not matching selected languages'),
            (bool(exclude_str), 'Excluded ROMs by name'),
            (bool(exclude_after_str), 'Excluded ROMs by name (after selection)')
        ]

        # Filter to only active filters descriptions
        active_filters = [f[1] for f in filters if f[0]]

        # If any filters active
        if active_filters:
            # Print numbered list
            print(
                f'{colors.BRIGHT_CYAN}Filtering out:{colors.RESET}\n' + "".join(
                    [
                        f"\t{i[0] + 1}. {i[1]}\n"
                        for i in enumerate(active_filters)
                    ]
                ),
                file=sys.stderr
            )

        # Print sorting criteria information
        print(
            f'{colors.BRIGHT_CYAN}Sorting with the following criteria:{colors.RESET}\n'
            '\t1. Good Dumps\n'
            f"\t2. {"Prelease ROMs" if prefer_prereleases else "Released ROMs"}\n"
            f"\t3. Non-avoided Items{" (Ignored)" if not avoid else ""}\n"
            f"\t4. {lang_text if prioritize_languages else region_text}\n"
            f"\t5. {region_text if prioritize_languages else lang_text}\n"
            f"\t6. {parents_text if prefer_parents else parents_text + " (Ignored)"}\n"
            f"\t7. {index_text if input_order else index_text + " (Ignored)"}\n"
            f"\t8. Preferred items{" (Ignored)" if not prefer else ""}\n"
            f"\t9. {"Earliest" if revision_asc else "Latest"} revision\n"
            f"\t10. {"Earliest" if version_asc else "Latest"} version\n"
            '\t11. Latest Sample\n'
            '\t12. Latest Demo\n'
            '\t13. Latest Beta\n'
            '\t14. Latest Prototype\n'
            '\t15. Most Languages Supported\n'
            '\t16. Parent ROMs\n',
            file=sys.stderr
        )

    # Create key generator object for sorting game entries
    key_generator = GameEntryKeyGenerator(
        prioritize_languages,
        prefer_prereleases,
        prefer_parents,
        input_order,
        prefer,
        avoid
    )

    # Iterate over each parent key in parsed games
    for key in parsed_games:
        # Get list of GameEntry objects for parent key
        games = parsed_games[key]

        # Pad version values for all entries so comparisons align
        pad_values(
            games,
            GameEntry.get_version,
            GameEntry.set_version
        )

        # Pad revision values for all entries
        pad_values(
            games,
            GameEntry.get_revision,
            GameEntry.set_revision
        )

        # Pad sample values for all entries
        pad_values(
            games,
            GameEntry.get_sample,
            GameEntry.set_sample
        )

        # Pad demo values for all entries
        pad_values(
            games,
            GameEntry.get_demo,
            GameEntry.set_demo
        )

        # Pad beta values for all entries
        pad_values(
            games,
            GameEntry.get_beta,
            GameEntry.set_beta
        )

        # Pad prototype values for all entries
        pad_values(
            games,
            GameEntry.get_proto,
            GameEntry.set_proto
        )

        # Compute and set scores for each entry based on criteria
        set_scores(
            games,
            selected_regions,
            selected_languages,
            language_weight,
            revision_asc,
            version_asc
        )

        # Sort games list in-place using generated key
        games.sort(key=key_generator.generate)

        # If verbose enabled
        if verbose:
            # Log information about ordering for debugging/inspection
            log(f"Candidate order for [{key}]: {[g.name for g in games]}")

    # Initialize list for printed item names
    printed_items: List[str] = []

    # Initialize list for printed item sizes (uncompressed sizes)
    printed_sizes: List[int] = []

    # Initialize list to collect actual file sizes (on-disk)
    actual_file_sizes = []

    # Define helper to decide if candidate GameEntry should be included
    def include_candidate(x: GameEntry) -> bool:
        # If all-regions-with-lang mode is enabled
        if all_regions_with_lang:
            # Parse explicit languages from entry name
            explicit_langs = parse_languages(x.name)

            # If explicit languages found
            if explicit_langs:
                # If none of explicit languages are in selected_languages
                if not any(lang in selected_languages for lang in explicit_langs):
                    # Do not include candidate
                    return False
            else:
                # If no explicit languages, include only when language score is negative
                return x.score.languages < 0

        # If only-selected-lang mode and candidate languages score is non-negative
        if only_selected_lang and x.score.languages >= 0:
            # Do not include candidate
            return False

        # If all-regions-with-lang and language score is negative
        if all_regions_with_lang and x.score.languages < 0:
            # Include candidate
            return True

        # If all regions mode is enabled
        if all_regions:
            # Include candidate
            return True

        # Default: include only if region is selected
        return x.score.region != UNSELECTED

    # Iterate over parent keys
    for game in sorted(parsed_games.keys()):
        # Get entries list for game
        entries = parsed_games[game]

        # If debugging enabled
        if DEBUG:
            # Log JSON-encoded candidate entries for debugging
            log(
                f"[DEBUG] Candidates for game [{game}] before filtering: "
                f"{JSON_ENCODER.encode(entries)}"
            )

        # If not including all regions
        if not all_regions:
            # Create filtered list of entries
            entries = [x for x in entries if include_candidate(x)]

        # If debugging enabled
        if DEBUG:
            # Log JSON-encoded candidate entries after filtering
            log(
                f"[DEBUG] Candidates for game [{game}] after filtering: "
                f"{JSON_ENCODER.encode(entries)}"
            )

        # Get number of candidate entries
        size = len(entries)

        # Initialize current output directory for game
        curr_out_dir = output_dir

        # Iterate through candidate entries by index
        for i in range(0, size):
            # Get current candidate entry
            entry = entries[i]

            # Iterate through ROM descriptors in entry to get rom_size
            for entry_rom in entry.roms:
                # Assign ROM size for later reporting
                rom_size = entry_rom.size

            # If entry name matches any exclude-after pattern
            if check_in_pattern_list(entry.name, exclude_after):
                # Break out of candidate loop for parent
                break

            # Compute subdirectory name based on first character (or '#')
            if output_dir and group_by_first_letter:
                curr_out_dir = (
                    output_dir / (
                        entry.name[0].lower()
                        if ALPHABETICAL_REGEX.search(entry.name)
                        else '#'
                    )
                )

            # If using file hashes to locate ROMs
            if use_hashes:
                # Track files already copied for candidate to avoid duplicates
                copied_files = set()

                # Number of ROM files expected for candidate
                num_roms = len(entry.roms)

                # Iterate over each ROM descriptor for candidate
                for entry_rom in entry.roms:
                    # Normalize SHA-1 digest to lowercase
                    digest = entry_rom.sha1.lower()

                    # Look up input path for digest in index
                    rom_input_path = hash_index[digest]

                    # If path was found for digest
                    if rom_input_path:
                        # Determine if found path is ZIP archive
                        is_zip = is_zipfile(rom_input_path)

                        # Compute relative path of ROM file from input_dir
                        file = rom_input_path.relative_to(input_dir)

                        # If no output directory specified (printing mode)
                        if not curr_out_dir:
                            # If file hasn't been accounted for yet
                            if rom_input_path not in copied_files:
                                # Append relative path string to printed items
                                printed_items.append(str(file))

                                # Append reported ROM size (uncompressed)
                                printed_sizes.append(rom_size)

                                try:
                                    # Append actual on-disk size if available
                                    actual_file_sizes.append(rom_input_path.stat().st_size)
                                except Exception:
                                    # Ignore errors getting actual file size
                                    pass

                                # Mark input path as copied/processed
                                copied_files.add(rom_input_path)

                        # Have output directory and haven't copied file yet
                        elif rom_input_path not in copied_files:
                            # If not ZIP and there are multiple ROMs, create subdir per entry name
                            if not is_zip and num_roms > 1:
                                # Set output directory to subdirectory named after entry
                                rom_output_dir = curr_out_dir / entry.name
                            else:
                                # Use current output directory directly
                                rom_output_dir = curr_out_dir

                            # Ensure rom_output_dir exists
                            rom_output_dir.mkdir(
                                parents=True,
                                exist_ok=True)

                            # If input is ZIP file, name output as zip_name
                            if is_zip:
                                # Generate zip filename using entry name
                                zip_name = add_extension(entry.name, 'zip')

                                # Compute full output path for zip
                                rom_output_path = rom_output_dir / zip_name
                            else:
                                # Compute full output path for zip
                                rom_output_path = rom_output_dir / entry_rom.name

                            # Transfer file (move/copy/symlink depending on flags)
                            transfer_file(
                                rom_input_path,
                                rom_output_path,
                                move,
                                symlink,
                                relative
                            )

                            # Append printed relative input path for reporting
                            printed_items.append(str(file))

                            # Append uncompressed ROM size for reporting
                            printed_sizes.append(rom_size)

                            try:
                                # Append actual on-disk size if available
                                actual_file_sizes.append(rom_input_path.stat().st_size)
                            except Exception:
                                # Ignore errors getting actual file size
                                pass

                            # Mark input path as copied/processed
                            copied_files.add(rom_input_path)
                    else:
                        # Log warning if ROM file for candidate not found
                        log(
                            f"ROM file [{entry_rom.name}] for candidate "
                            f"[{entry.name}] not found"
                        )

                # If at least one file copied/added for candidate
                if copied_files:
                    # Break out of candidate loop (found files for parent)
                    break
                else:
                    # Log warning that candidate wasn't found and try next
                    log(
                        f"Candidate [{entry.name}] not found, "
                        "trying next one"
                    )

                    # If last candidate for parent
                    if i == size - 1:
                        # Log warning that no eligible candidate found for parent
                        log(
                            f"No eligible candidates for [{game}] "
                            "have been found!"
                        )

            # If input directory is provided but not using hashes
            elif input_dir:
                # Construct expected filename using entry name and extension
                file_name = add_extension(entry.name, file_extension)

                # Construct full path to expected file in input directory
                full_path = input_dir / file_name

                # If expected file exists as file
                if full_path.is_file():
                    # If output directory is specified
                    if curr_out_dir:
                        # Ensure output directory exists
                        curr_out_dir.mkdir(parents=True, exist_ok=True)

                        # If requested to symlink
                        if symlink:
                            # Set curr_out_dir to path for symlink target file
                            curr_out_dir = curr_out_dir / file_name

                        # Transfer file according to requested action (move/copy/symlink)
                        transfer_file(full_path, curr_out_dir, move, symlink, relative)
                    else:
                        # If not copying to output dir, add filename to printed items
                        printed_items.append(file_name)
                        try:
                            # Append actual file size for reporting
                            actual_file_sizes.append(full_path.stat().st_size)
                        except Exception:
                            # Ignore errors getting actual file size
                            pass
                    break

                # If full_path is directory
                elif full_path.is_dir():
                    # Iterate all ROM descriptors to look for files inside directory
                    for entry_rom in entry.roms:
                        # Compute path to ROM file inside directory
                        rom_input_path = full_path / entry_rom.name

                        # If ROM file exists inside directory
                        if rom_input_path.is_file():
                            # If output directory specified
                            if curr_out_dir:
                                # Compute output subdirectory path for entry
                                rom_output_dir = curr_out_dir / file_name

                                # Ensure output subdirectory exists
                                rom_output_dir.mkdir(
                                    parents=True,
                                    exist_ok=True
                                )

                                # Transfer found ROM file to output subdirectory
                                transfer_file(
                                    rom_input_path,
                                    rom_output_dir,
                                    move,
                                    symlink,
                                    relative
                                )

                                # Copy metadata from source dir to output dir
                                shutil.copystat(
                                    str(full_path),
                                    str(rom_output_dir)
                                )
                            else:
                                # Append printed item with directory notation and rom name
                                printed_items.append(
                                    file_name + '/' + entry_rom.name)
                                try:
                                    # Append actual file size for reporting
                                    actual_file_sizes.append(rom_input_path.stat().st_size)
                                except Exception:
                                    # Ignore errors getting actual file size
                                    pass
                        else:
                            # Log warning if specific ROM file inside directory wasn't found
                            log(
                                f"ROM file [{entry_rom.name}] for candidate "
                                f"[{file_name}] not found"
                            )

                    # Break out of candidate loop after checking directory contents
                    break
                else:
                    # Log warning that candidate file wasn't found at expected path
                    log(
                        f"Candidate [{file_name}] not found, "
                        "trying next one"
                    )

                    # If last candidate
                    if i == size - 1:
                        # Log that no eligible candidates were found
                        log(
                            f"No eligible candidates for [{game}] "
                            "have been found!"
                        )
            else:
                # Append expected filename with extension to printed items
                printed_items.append(add_extension(entry.name, file_extension))

                # Append reported ROM size to printed sizes
                printed_sizes.append(rom_size)

                # Break out of candidate loop after adding this entry
                break

    # Sort printed items as case-insensitive
    printed_items.sort(key=str.casefold)

    # Iterate over each best candidate name
    for item in printed_items:
        # Print each item on its own line
        print(item)

    # Sum total of uncompressed sizes
    printed_sizes_total = sum(int(item) for item in printed_sizes)

    # Sum total of on-disk sizes
    actual_sizes_total = sum(actual_file_sizes)

    # Build message with file counts and size
    msg = (
        f"{len(printed_items):,} {'File' if len(printed_items) == 1 else 'Files'}, "
        f"{human_readable_size(printed_sizes_total)} (Uncompressed)"
    )

    # If input directory specified
    if input_dir:
        # Append actual size info to message
        msg += f" / {human_readable_size(sum(actual_file_sizes))} (Actual)"

    # Print final info message
    print(f"\n{colors.BRIGHT_CYAN}[INFO] {msg}{colors.RESET}")


def parse_list(
    arg_input: Union[str, List[str]],  # String or list of strings
    ignore_case: bool,  # Flag to enable case-insensitive matching
    regex: bool,  # Flag to treat input as regex
    separator: str  # Separator used if input is a string
) -> List[re.Pattern]:
    # Check if input is already a list
    if isinstance(arg_input, list):
        # Strip and validate each item in the list
        arg_list = [x.strip() for x in arg_input if is_valid(x)]
    else:
        # Treat input as a string
        arg_str = arg_input

        # Proceed only if string is not empty
        if arg_str:
            # Check if input refers to a file
            if arg_str.startswith(FILE_PREFIX):
                # Get the file path and expand user directory
                file = Path(arg_str[len(FILE_PREFIX):].strip()).expanduser()

                # if file does not exist
                if not file.is_file():
                    # Raise error
                    raise OSError(f"invalid file: {file}")
                # Read and validate lines from the file
                #arg_list = [x.strip() for x in open(file) if is_valid(x)]
                arg_list = [
                    re.sub(r'\s*(<[^>]*>|//.*$|<!--.*?-->)', '', x.strip()) for x in open(file) if is_valid(x)]
            else:
                # Split string by separator and validate each item
                arg_list = [x.strip() for x in arg_str.split(separator) if is_valid(x)]
        else:
            # If string is empty, use an empty list
            arg_list = []

        # Ignore case enabled
        if ignore_case:
            # Build regex list with case-insensitive matching
            return [
                # Escape string unless regex is enabled, then compile with IGNORECASE
                re.compile(x if regex else re.escape(x), re.IGNORECASE)

                # Only include valid entries
                for x in arg_list if is_valid(x)
            ]

        # Ignore case not enabled
        else:
            # Build regex list with case-sensitive matching
            return [
                # Compile regex with case-insensitive flag
                re.compile(x if regex else re.escape(x))

                # Compile regex with default case sensitivity
                for x in arg_list if is_valid(x)
            ]

    # Return empty list if input was a list but no valid items found
    return []


# Define a function to handle file or URL arguments
def handle_url_or_file_argument(
    arg: str,                      # The input string (could be a URL, file path, or pattern)
    option_name: str,              # A label used in error messages for clarity
    separator: str,                # Separator for list parsing (not used here)
    temp_suffix: str = '.txt',     # Default suffix for temporary files (used for downloads)
    validate_direct_path: bool = False,  # Whether to return a Path object instead of a string
    auto_cleanup: bool = True      # Whether to clean up temp files later
) -> Union[str, Path]:             # Return type can be a string or Path object

    # Check if the argument starts with 'url:' (indicating a remote file)
    if arg.startswith('url:'):
        # Extract the URL from the argument
        url = arg[len('url:'):].strip()
        try:
            # Print a status message to stderr about the download
            print(f"{colors.BRIGHT_CYAN}[STATUS] Downloading{colors.RESET} [{option_name}] {colors.BRIGHT_CYAN}from{colors.RESET} [{url}]\n", file=sys.stderr)
            # Create a default SSL context for secure download
            ssl_context = ssl.create_default_context()
            # Disable hostname verification
            ssl_context.check_hostname = False
            # Disable certificate verification
            ssl_context.verify_mode = ssl.CERT_NONE

            # Create a temporary file to store the downloaded content
            with tempfile.NamedTemporaryFile(mode='wb', suffix=temp_suffix, delete=False) as temp_file:
                # Open the URL and read its contents
                with urllib.request.urlopen(url, context=ssl_context) as response:
                    # Write the downloaded data to the temp file
                    temp_file.write(response.read())

                # Get the path to the temporary file
                temp_file_path = temp_file.name
                # If cleanup is enabled, register the temp file for deletion
                if auto_cleanup:
                    TEMP_FILES.append(temp_file_path)

                # Return the path as a Path object or string depending on the flag
                return Path(temp_file_path) if validate_direct_path else f"file:{temp_file_path}"

        # Handle any exception during download or file creation
        except Exception as e:
            # Exit with a formatted error message
            sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Failed to download {option_name}: {e}{colors.RESET}"))

    # Handle local file path or glob pattern (with or without 'file:' prefix)
    pattern = arg[len('file:'):].strip() if arg.startswith('file:') else arg.strip()
    # Use glob to find all matching files in the user's home directory
    matches = sorted([m for m in Path().expanduser().glob(pattern) if m.is_file()])

    # If no files matched the pattern, exit with an error
    if not matches:
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] No {option_name} file found matching pattern: {pattern}{colors.RESET}"))
    # If multiple files matched, list them and exit with an error
    elif len(matches) > 1:
        listed = '\n'.join(f" - {m}" for m in matches)
        sys.exit(help_msg(f"{colors.BRIGHT_RED}[ERROR] Multiple {option_name} files matched pattern: {pattern}\n{listed}{colors.RESET}"))

    # Return the single matched file as a Path or string depending on the flag
    return matches[0] if validate_direct_path else f"file:{matches[0]}"


def set_scores(
    games: List[GameEntry],
    selected_regions: List[str],
    selected_languages: List[str],
    language_weight: int,
    revision_asc: bool,
    version_asc: bool
) -> None:
    # Loop over each game in provided list
    for game in games:
        # Determine region score based on game region and selected regions
        region_score = get_index(selected_regions, game.region, UNSELECTED)

        # Calculate language score by summing weighted values for each game language
        languages_score = sum([
            # Get index of language
            (get_index(selected_languages, lang, -1) + 1) * -language_weight

            # Do this for every language the game supports
            for lang in game.languages
        ])

        # Convert revision string into list of integers
        revision_int = to_int_list(
            game.revision,
            1 if revision_asc else -1
        )

        # Convert version string into list of integers
        version_int = to_int_list(game.version, 1 if version_asc else -1)

        # Convert sample flag into list of integers
        sample_int = to_int_list(game.sample, -1)

        # Convert demo flag into list of integers
        demo_int = to_int_list(game.demo, -1)

        # Convert beta flag into list of integers
        beta_int = to_int_list(game.beta, -1)

        # Convert proto flag into list of integers
        proto_int = to_int_list(game.proto, -1)

        # Assign new Score object to game score attribute
        game.score = Score(
            region_score,
            languages_score,
            revision_int,
            version_int,
            sample_int,
            demo_int,
            beta_int,
            proto_int
        )


def transfer_file(
    input_path: Path,
    output_path: Path,
    move: bool,
    symlink: bool,
    relative: bool
) -> None:
    try:
        # If move flag is set
        if move:
            # Announce move operation
            print(f"{colors.BRIGHT_CYAN}Moving{colors.RESET} [{input_path}] {colors.BRIGHT_CYAN}to{colors.RESET} [{output_path}]")

            # Perform move using shutil
            shutil.move(str(input_path), str(output_path))

        # If symlink flag is set
        elif symlink:
            # Announce linking operation
            print(f"{colors.BRIGHT_CYAN}Linking{colors.RESET} [{input_path}] {colors.BRIGHT_CYAN}to{colors.RESET} [{output_path}]")

            # If relative symlink not requested
            if not relative:
                # Create absolute symlink pointing to resolved input path
                output_path.symlink_to(input_path.resolve())
            else:
                # Create relative symlink using path relative to output parent
                output_path.symlink_to(os.path.relpath(input_path, output_path.parent))

        else:
            # Announce copy operation
            print(f"{colors.BRIGHT_CYAN}Copying{colors.RESET} [{input_path}] {colors.BRIGHT_CYAN}to{colors.RESET} [{output_path}]\033[K")

            # Copy file preserving metadata
            shutil.copy2(str(input_path), str(output_path))

    except OSError as e:
        # Print transfer error message to stderr
        print(
            f"{colors.BRIGHT_RED}[ERROR] Error while transferring file:{colors.RESET} {e}\033[K",
            file=sys.stderr
        )


def log(s: str) -> None:
    # Print to LOG_FILE or stderr
    print(s, file=LOG_FILE if LOG_FILE else sys.stderr)


def format_help(options_desc, indent=4, sep=4, desc_min_width=30):
    # Get terminal width or fallback to 80 columns if unknown
    term_width = shutil.get_terminal_size(fallback=(80, 20)).columns

    # Calculate max option width ignoring full_line entries
    max_opt_width = max(
        # Get visible length of option string, skip if full_line True
        visible_len(opt) for opt, *rest in options_desc
        if not (len(rest) > 1 and rest[1])
    )

    # Limit max option width to fit terminal width minus description and indents
    max_opt_width = min(max_opt_width,
                       term_width - desc_min_width - indent - sep)

    # Initialize list to accumulate formatted lines
    lines = []

    # Iterate over each item in options list
    for item in options_desc:
        # Unpack tuple; if 3 elements, get full_line flag too
        if len(item) == 3:
            # Extract option, description, and full_line flag from 3-tuple
            opt, desc, full_line = item
        else:
            # Otherwise default full_line to False
            opt, desc = item[0], item[1]
            full_line = False

        # If this is a full line entry (no option column)
        if full_line:
            # For full line entries, we need to handle ANSI codes in wrapping
            # Create a custom wrapper that accounts for ANSI sequences
            def wrap_with_ansi(text, width):
                # Split text into individual words for manual wrapping
                words = text.split()
                # Initialize list to hold completed lines
                lines = []
                # Track current line being built
                current_line = ""
                # Track visible length of current line (excluding ANSI codes)
                current_visible_length = 0

                # Process each word individually
                for word in words:
                    # Get actual visible length of word (ignoring ANSI codes)
                    word_visible_length = visible_len(word)
                    # Check if adding this word would exceed the width
                    if current_line and current_visible_length + 1 + word_visible_length > width:
                        # Current line is full, save it and start new line
                        lines.append(current_line)
                        # Start new line with just this word
                        current_line = word
                        # Reset visible length counter to this word's length
                        current_visible_length = word_visible_length
                    else:
                        # Word fits on current line
                        if current_line:
                            # Add space separator and word to existing line
                            current_line += " " + word
                            # Add 1 for space plus word length to visible counter
                            current_visible_length += 1 + word_visible_length
                        else:
                            # First word on line, no space needed
                            current_line = word
                            # Set visible length to just this word
                            current_visible_length = word_visible_length

                # Don't forget the last line if it has content
                if current_line:
                    lines.append(current_line)

                # Return all lines as a list
                return lines

            # Wrap the description text accounting for ANSI codes
            wrapped_lines = wrap_with_ansi(desc, term_width)
            # Join wrapped lines with newlines to create final string
            line = '\n'.join(wrapped_lines)
        else:
            # Calculate available width for description column
            desc_width = term_width - indent - sep - max_opt_width

            # For description wrapping, we need to handle ANSI codes and maintain column alignment
            def wrap_description_with_ansi(text, width, subsequent_indent=""):
                # Split description text into individual words
                words = text.split()
                # Initialize list to collect completed lines
                lines = []
                # Track the line currently being built
                current_line = ""
                # Track visible length of current line (excluding ANSI codes)
                current_visible_length = 0
                # Flag to track if we're still on the first line
                is_first_line = True

                # Process each word in the description
                for word in words:
                    # Calculate actual visible width of this word (no ANSI codes)
                    word_visible_length = visible_len(word)
                    # Check if adding this word would exceed the width
                    if current_line and current_visible_length + 1 + word_visible_length > width:
                        # Line is full, save current line to results
                        lines.append(current_line)
                        # Start new line with proper indentation plus the word
                        current_line = subsequent_indent + word
                        # Calculate new visible length: indent + word (using visible_len for indent)
                        current_visible_length = visible_len(subsequent_indent) + word_visible_length
                        # No longer on first line
                        is_first_line = False
                    else:
                        # Word fits on current line
                        if current_line:
                            # Add space separator and the word to existing content
                            current_line += " " + word
                            # Update visible length: +1 for space, +word length
                            current_visible_length += 1 + word_visible_length
                        else:
                            # First word of the line
                            if not is_first_line:
                                # Continuation line: add indentation before word
                                current_line = subsequent_indent + word
                                # Visible length = visible indent + word length
                                current_visible_length = visible_len(subsequent_indent) + word_visible_length
                            else:
                                # Very first line: no indentation needed
                                current_line = word
                                # Visible length is just the word
                                current_visible_length = word_visible_length

                # Add final line if it contains any content
                if current_line:
                    lines.append(current_line)

                # Join all lines with newlines and return as single string
                return '\n'.join(lines)

            # Wrap description text with continuation lines indented to description column start
            wrapped_desc = wrap_description_with_ansi(
                desc,
                desc_width,
                ' ' * (indent + sep + max_opt_width)  # Indent to align with description column
            )

            # Construct complete line: indent + padded option + separator + wrapped description
            line = (' ' * indent + color_ljust(opt, max_opt_width) + ' ' * sep
                    + wrapped_desc)

        # Add the fully formatted line to our results list
        lines.append(line)

    # Join all formatted lines with newlines and return the complete help text
    return '\n'.join(lines)


def help_msg(s: Optional[Union[str, Exception]] = None) -> str:
    options = [
        ("", f"{colors.BRIGHT_CYAN}Usage: python3 {sys.argv[0]} [options] -d input_file.dat{colors.RESET}", True),  # Full Line
        ("", ""),  # Empty Line
        ("", f"{colors.BRIGHT_BLUE}ROM SELECTION & FILE MANAGEMENT:{colors.RESET}", True),  # Full Line
        (f"{colors.BRIGHT_CYAN}-r,--regions=LIST{colors.RESET}", "Comma-separated regions to include"),
        ("", f"{colors.BRIGHT_YELLOW}[-r USA,EUR,JPN]{colors.RESET}"),  # Example
        (f"{colors.BRIGHT_CYAN}-l,--languages=LIST{colors.RESET}", "Comma-separated languages for secondary sorting"),
        ("", f"{colors.BRIGHT_YELLOW}[-l en,es,ru]{colors.RESET}"),  # Example
        (f"{colors.BRIGHT_CYAN}-d,--dat=FILE{colors.RESET}", "DAT file specifying ROM metadata"),
        ("", f'{colors.BRIGHT_YELLOW}[-d "DATS\\Nintendo - Game Boy.dat"]{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}-i,--input-dir=PATH{colors.RESET}", "Directory containing source ROM files"),
        ("", f'{colors.BRIGHT_YELLOW}[-i "ROMS\\Nintendo - Game Boy"]{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}-o,--output-dir=PATH{colors.RESET}", "Output directory for processed ROMs"),
        ("", f'{colors.BRIGHT_YELLOW}[-o "1G1R\\Nintendo - Game Boy"]{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}--move{colors.RESET}", "Move files to output instead of copying"),
        (f"{colors.BRIGHT_CYAN}--symlink{colors.RESET}", "Create symbolic links instead of copying (may require admin)"),
        (f"{colors.BRIGHT_CYAN}--relative{colors.RESET}", "Use relative paths when creating symlinks"),
        (f"{colors.BRIGHT_CYAN}--group-by-first-letter{colors.RESET}", "Organize output into subfolders by first letter"),
        ("", ""),  # Empty Line
        ("", f"{colors.BRIGHT_BLUE}FILE SCANNING:{colors.RESET}", True),  # Full Line
        (f"{colors.BRIGHT_CYAN}--header-file=PATH{colors.RESET}", "File containing header for ROM scanning"),
        ("", f'{colors.BRIGHT_YELLOW}[--header-file "headers\\No-Intro_NES.xml"]{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}--threads=INT{colors.RESET}", "Number of concurrent I/O threads"),
        ("", f'{colors.BRIGHT_YELLOW}[--threads "4"]{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}--chunk-size=BYTES{colors.RESET}", "Buffered I/O chunk size"),
        ("", f'{colors.BRIGHT_YELLOW}[--chunk-size "33554432"]{colors.RESET} {colors.YELLOW}(32*1024*1024) 32 MiB{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}--max-file-size=BYTES{colors.RESET}", "Max file size for header scanning"),
        ("", f'{colors.BRIGHT_YELLOW}[--max-file-size "268435456"]{colors.RESET} {colors.YELLOW}(256*1024*1024) 256 MiB{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}--no-scan{colors.RESET}", "Skip content scan; identify by filename only"),
        (f"{colors.BRIGHT_CYAN}-e,--extension=EXT{colors.RESET}", "File extension used when scanning is disabled"),
        ("", f"{colors.BRIGHT_YELLOW}[-e zip]{colors.RESET}"),  # Example
        ("", ""),  # Empty Line
        ("", f"{colors.BRIGHT_BLUE}FILTERING:{colors.RESET}", True),  # Full Line
        (f"{colors.BRIGHT_CYAN}--no-bios{colors.RESET}", "Exclude BIOS ROMs"),
        (f"{colors.BRIGHT_CYAN}--no-program{colors.RESET}", "Exclude Program and Test Program ROMs"),
        (f"{colors.BRIGHT_CYAN}--no-enhancement-chip{colors.RESET}", "Exclude ROMs with Enhancement Chips"),
        (f"{colors.BRIGHT_CYAN}--no-proto{colors.RESET}", "Exclude Prototypes"),
        (f"{colors.BRIGHT_CYAN}--no-beta{colors.RESET}", "Exclude Beta Versions"),
        (f"{colors.BRIGHT_CYAN}--no-demo{colors.RESET}", "Exclude Demos"),
        (f"{colors.BRIGHT_CYAN}--no-sample{colors.RESET}", "Exclude Sample ROMs"),
        (f"{colors.BRIGHT_CYAN}--no-pirate{colors.RESET}", "Exclude Pirate Dumps"),
        (f"{colors.BRIGHT_CYAN}--no-bad{colors.RESET}", "Exclude Bad Dumps"),
        (f"{colors.BRIGHT_CYAN}--no-aftermarket{colors.RESET}", "Exclude Aftermarket ROMs"),
        (f"{colors.BRIGHT_CYAN}--no-homebrew{colors.RESET}", "Exclude Homebrew ROMs"),
        (f"{colors.BRIGHT_CYAN}--no-kiosk{colors.RESET}", "Exclude Kiosk versions"),
        (f"{colors.BRIGHT_CYAN}--no-promo{colors.RESET}", "Exclude Promotional ROMs"),
        (f"{colors.BRIGHT_CYAN}--no-debug{colors.RESET}", "Exclude Debug builds"),
        (f"{colors.BRIGHT_CYAN}--no-all{colors.RESET}", "Apply all above filters except Unlicensed ROMs"),
        (f"{colors.BRIGHT_CYAN}--no-unlicensed{colors.RESET}", "Exclude Unlicensed ROMs except Aftermarket/Homebrew"),
        (f"{colors.BRIGHT_CYAN}--no-unlicensed-strict{colors.RESET}", "Exclude all Unlicensed ROMs including Aftermarket/Homebrew"),
        (f"{colors.BRIGHT_CYAN}--all-regions{colors.RESET}", "Include fallback regions if selected are missing"),
        (f"{colors.BRIGHT_CYAN}--all-regions-with-lang{colors.RESET}", "As --all-regions, but only if language matches selection"),
        (f"{colors.BRIGHT_CYAN}--only-selected-lang{colors.RESET}", "Exclude ROMs lacking selected languages"),
        ("", ""),  # Empty Line
        ("", f"{colors.BRIGHT_BLUE}ADJUSTMENT AND CUSTOMIZATION:{colors.RESET}", True),  # Full Lines
        (f"{colors.BRIGHT_CYAN}-w,--language-weight=INT{colors.RESET}", "Weight multiplier for first selected languages"),
        ("", f'{colors.BRIGHT_YELLOW}[-w "3"]{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}--prioritize-languages{colors.RESET}", "Favor ROMs matching more languages over regions"),
        (f"{colors.BRIGHT_CYAN}--early-revisions{colors.RESET}", "Prefer earlier ROM revisions"),
        (f"{colors.BRIGHT_CYAN}--early-versions{colors.RESET}", "Prefer earlier ROM versions"),
        (f"{colors.BRIGHT_CYAN}--input-order{colors.RESET}", "Prefer ROMs in DAT file order"),
        (f"{colors.BRIGHT_CYAN}--prefer-parents{colors.RESET}", "Favor parent ROMs over clones"),
        (f"{colors.BRIGHT_CYAN}--prefer-prereleases{colors.RESET}", "Favor prerelease ROMs (Beta, Proto, etc.)"),
        (f"{colors.BRIGHT_CYAN}--prefer=WORDS{colors.RESET}", "Prefer ROMs containing listed words or file input"),
        ("", f'{colors.BRIGHT_YELLOW}[--prefer "Virtual Console,GameCube"]{colors.RESET}'),  # Example
        ("", f'{colors.BRIGHT_YELLOW}[--prefer "file:prefer.txt"]{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}--avoid=WORDS{colors.RESET}", "Avoid ROMs containing listed words (not excluded)"),
        ("", f'{colors.BRIGHT_YELLOW}[--avoid "Virtual Console,GameCube"]{colors.RESET}'),  # Example
        ("", f'{colors.BRIGHT_YELLOW}[--avoid "file:avoid.txt"]{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}--exclude=WORDS{colors.RESET}", "Exclude ROMs containing listed words"),
        ("", f'{colors.BRIGHT_YELLOW}[--exclude "Virtual Console,GameCube"]{colors.RESET}'),  # Example
        ("", f'{colors.BRIGHT_YELLOW}[--exclude "file:avoid.txt"]{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}--exclude-after=WORDS{colors.RESET}", "Skip all candidates if best contains listed words"),
        ("", f'{colors.BRIGHT_YELLOW}[--exclude-after "Virtual Console,GameCube"]{colors.RESET}'),  # Example
        ("", f'{colors.BRIGHT_YELLOW}[--exclude-after "file:avoid.txt"]{colors.RESET}'),  # Example
        (f"{colors.BRIGHT_CYAN}--ignore-case{colors.RESET}", "Case-insensitive matching for avoid/exclude lists"),
        (f"{colors.BRIGHT_CYAN}--regex{colors.RESET}", "Use regular expressions for avoid/exclude lists"),
        (f"{colors.BRIGHT_CYAN}--separator=CHAR{colors.RESET}", "Separator character for word lists"),
        ("", f'{colors.BRIGHT_YELLOW}[--separator ","]{colors.RESET}'),  # Example
        ("", ""),  # Empty Line
        ("", f"{colors.BRIGHT_BLUE}HELP AND DEBUGGING:{colors.RESET}", True),  # Full Lines
        (f"{colors.BRIGHT_CYAN}-h,--help{colors.RESET}", "Display this help message"),
        (f"{colors.BRIGHT_CYAN}-v,--version{colors.RESET}", "Show version info"),
        (f"{colors.BRIGHT_CYAN}-V,--verbose{colors.RESET}", "Enable verbose logging for troubleshooting"),
        (f"{colors.BRIGHT_CYAN}-D,--debug{colors.RESET}", "Enable detailed debug output"),
        (f"{colors.BRIGHT_CYAN}--force{colors.RESET}", "Skip confirmation prompts; auto-confirm actions"),
    ]

    # Combine usage line, options header, and formatted options into one help string
    help_str = format_help(options)

    # If string `s` provided
    if s:
        # Prepend with two newlines before help text
        return f"{s}\n\n{help_str}"
    else:
        # Otherwise, just return the help string
        return help_str


if __name__ == '__main__':
    # Get script filename
    script_file = sys.argv[0]

    # If filename contains dot (.)
    if '.' in script_file:
        # Strip off file extension
        script_file = script_file[:script_file.rindex('.')]

    # Build log file name (script_name.log)
    log_file = add_extension(script_file, 'log')

    try:
        # If logging enabled
        if not NO_LOG:
            try:
                # Open log file in write mode
                LOG_FILE = open(log_file, 'w')
            except OSError as w_e:
                # Print error message if log file cannot be opened
                print(f"{colors.BRIGHT_RED}Unable to open {log_file} file for writing: {w_e}{colors.RESET}\n", file=sys.stderr)

        # Run main() function, passing all arguments except script name
        main(sys.argv[1:])

        # Prepare "finished" message based on NO_LOG
        if not NO_LOG:
            # Prepare "finished" message with log filename
            final_message = f"[SUCCESS] Execution finished. See {log_file} for details."
        else:
            # Prepare "finished" message without log filename
            final_message = f"[SUCCESS] Execution finished."

        # Print "finished" message
        print(f"\n{colors.BRIGHT_GREEN}{final_message}{colors.RESET}", file=sys.stderr)

    # If user presses Ctrl+C
    except KeyboardInterrupt:
        # Prepare "interrupted" message based on NO_LOG
        if not NO_LOG:
            # Prepare "interrupted" message with log filename
            final_message = f"[ERROR] Execution interrupted. See {log_file} for details."
        else:
            # Prepare "interrupted" message without log filename
            final_message = f"[ERROR] Execution interrupted."

        # If progress bar in use
        if PROGRESSBAR:
            # Lock progress bar before exiting to prevent display corruption
            with PROGRESSBAR.lock:
                # Exit with the "interrupted" message
                sys.exit(f"\n{colors.BRIGHT_RED}{final_message}{colors.RESET}")
        else:
            # Exit cleanly with the "interrupted" message
            sys.exit(f"\n{colors.BRIGHT_RED}{final_message}{colors.RESET}")
