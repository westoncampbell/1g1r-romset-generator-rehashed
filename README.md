### 1G1R ROM Set Generator: Rehashed

Python script for processing No-Intro DAT files to produce 1G1R ROM sets.

***Rehashed*** is a continuation of the [original version](https://github.com/andrebrait/1g1r-romset-generator) created by [Andre Briat](https://github.com/andrebrait).

#### Requirements

* Python 3 (tested with versions 3.6+, but probably works on earlier versions)

#### Usage


```
Usage: python3 generate.py [options] -d input_file.dat

ROM SELECTION & FILE MANAGEMENT:
    -r,--regions=LIST           Comma-separated regions to include
                                [-r USA,EUR,JPN]
    -l,--languages=LIST         Comma-separated languages for secondary sorting
                                [-l en,es,ru]
    -d,--dat=FILE               DAT file specifying ROM metadata
                                [-d "DATS\Nintendo - Game Boy.dat"]
    -i,--input-dir=PATH         Directory containing source ROM files
                                [-i "ROMS\Nintendo - Game Boy"]
    -o,--output-dir=PATH        Output directory for processed ROMs
                                [-o "1G1R\Nintendo - Game Boy"]
    --move                      Move files to output instead of copying
    --symlink                   Create symbolic links instead of copying (may require admin)
    --relative                  Use relative paths when creating symlinks
    --group-by-first-letter     Organize output into subfolders by first letter

FILE SCANNING:
    --header-file=PATH          File containing header for ROM scanning
                                [--header-file "headers\No-Intro_NES.xml"]
    --threads=INT               Number of concurrent I/O threads
                                [--threads "4"]
    --chunk-size=BYTES          Buffered I/O chunk size
                                [--chunk-size "33554432"] (32*1024*1024) 32 MiB
    --max-file-size=BYTES       Max file size for header scanning
                                [--max-file-size "268435456"] (256*1024*1024) 256 MiB
    --no-scan                   Skip content scan; identify by filename only
    -e,--extension=EXT          File extension used when scanning is disabled
                                [-e zip]

FILTERING:
    --no-bios                   Exclude BIOS ROMs
    --no-program                Exclude Program and Test Program ROMs
    --no-enhancement-chip       Exclude ROMs with Enhancement Chips
    --no-proto                  Exclude Prototypes
    --no-beta                   Exclude Beta Versions
    --no-demo                   Exclude Demos
    --no-sample                 Exclude Sample ROMs
    --no-pirate                 Exclude Pirate Dumps
    --no-bad                    Exclude Bad Dumps
    --no-aftermarket            Exclude Aftermarket ROMs
    --no-homebrew               Exclude Homebrew ROMs
    --no-kiosk                  Exclude Kiosk versions
    --no-promo                  Exclude Promotional ROMs
    --no-debug                  Exclude Debug builds
    --no-all                    Apply all above filters except Unlicensed ROMs
    --no-unlicensed             Exclude Unlicensed ROMs except Aftermarket/Homebrew
    --no-unlicensed-strict      Exclude all Unlicensed ROMs including Aftermarket/Homebrew
    --all-regions               Include fallback regions if selected are missing
    --all-regions-with-lang     As --all-regions, but only if language matches selection
    --only-selected-lang        Exclude ROMs lacking selected languages

ADJUSTMENT AND CUSTOMIZATION:
    -w,--language-weight=INT    Weight multiplier for first selected languages
                                [-w "3"]
    --prioritize-languages      Favor ROMs matching more languages over regions
    --early-revisions           Prefer earlier ROM revisions
    --early-versions            Prefer earlier ROM versions
    --input-order               Prefer ROMs in DAT file order
    --prefer-parents            Favor parent ROMs over clones
    --prefer-prereleases        Favor prerelease ROMs (Beta, Proto, etc.)
    --prefer=WORDS              Prefer ROMs containing listed words or file input
                                [--prefer "Virtual Console,GameCube"]
                                [--prefer "file:prefer.txt"]
    --avoid=WORDS               Avoid ROMs containing listed words (not excluded)
                                [--avoid "Virtual Console,GameCube"]
                                [--avoid "file:avoid.txt"]
    --exclude=WORDS             Exclude ROMs containing listed words
                                [--exclude "Virtual Console,GameCube"]
                                [--exclude "file:avoid.txt"]
    --exclude-after=WORDS       Skip all candidates if best contains listed words
                                [--exclude-after "Virtual Console,GameCube"]
                                [--exclude-after "file:avoid.txt"]
    --ignore-case               Case-insensitive matching for avoid/exclude lists
    --regex                     Use regular expressions for avoid/exclude lists
    --separator=CHAR            Separator character for word lists
                                [--separator ","]

HELP AND DEBUGGING:
    -h,--help                   Display this help message
    -v,--version                Show version info
    -V,--verbose                Enable verbose logging for troubleshooting
    -D,--debug                  Enable detailed debug output
    --force                     Skip confirmation prompts; auto-confirm actions	
```

#### Scoring Strategy

The scoring system implemented here uses additional information provided by the
DAT file and/or the ROM names (following the No-Intro naming convention) to
better select the ROMs that should be part of the generated set, according to the user's preferences.

Sorting happens with the following criteria:
1. Good Dumps
2. Released ROMs (unless `--prefer-prereleases` is used)
3. Non-avoided Items (if `--avoid` is used)
4. Best Region Match (this can be switched with item #5 by using `--prioritize-languages`)
5. Best Language Match (this can be switched with item #4 by using `--prioritize-languages`)
6. Parent ROMs (if `--prefer-parents` is used)
7. Input Order (if `--input-order` is used)
8. Preferred Items (if `--prefer` is used)
9. Latest Revision (unless `--early-revisions` is used)
10. Latest Version (unless `--early-versions` is used)
11. Latest Sample
12. Latest Demo
13. Latest Beta
14. Latest Prototype
15. Most Languages Supported
16. Parent ROMs
