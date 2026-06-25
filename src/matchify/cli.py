"""Command-line and file processing helpers."""

from __future__ import annotations

import argparse
import multiprocessing
import pathlib
from concurrent.futures import ProcessPoolExecutor, as_completed

from .transform import transform_code


def convert_file(
    path: pathlib.Path, ignore_types_pattern: str | None = None
) -> tuple[pathlib.Path, bool, str | None]:
    """Convert a single file.

    Returns:
        Tuple of (path, changed, error_message)
    """
    try:
        source = path.read_text(encoding="utf-8")
        transformed_code = transform_code(
            source, ignore_types_pattern=ignore_types_pattern
        )

        # Only write back if something changed
        if transformed_code != source:
            path.write_text(transformed_code, encoding="utf-8")
            return (path, True, None)
        return (path, False, None)
    except Exception as e:
        return (path, False, str(e))


def collect_python_files(paths: list[pathlib.Path]) -> list[pathlib.Path]:
    """Collect all Python files from the given paths."""
    python_files = []
    for arg in paths:
        if arg.is_file() and arg.suffix == ".py":
            python_files.append(arg)
        elif arg.is_dir():
            python_files.extend(arg.rglob("*.py"))
        else:
            print(f"Skipping (not a Python file): {arg}")
    return python_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert if/elif/else chains to Python 3.10+ match statements"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=pathlib.Path,
        help="Python files or directories to process",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of parallel jobs (default: number of CPU cores)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show files with no changes"
    )
    parser.add_argument(
        "--no-types",
        type=str,
        default=r".*_TYPES$",
        help="Regex pattern for isinstance type variables to ignore (default: .*_TYPES$)",
    )

    args = parser.parse_args()

    # Collect all Python files
    python_files = collect_python_files(args.paths)

    if not python_files:
        print("No Python files found to process")
        return

    # Determine number of workers
    max_workers = args.jobs or multiprocessing.cpu_count()

    # Process files in parallel
    converted_count = 0
    unchanged_count = 0
    error_count = 0

    if len(python_files) == 1:
        # Single file - no need for multiprocessing
        path, changed, error = convert_file(
            python_files[0], ignore_types_pattern=args.no_types
        )
        if error:
            print(f"Error processing {path}: {error}")
            error_count += 1
        elif changed:
            print(f"Converted: {path}")
            converted_count += 1
        else:
            if args.verbose:
                print(f"No changes: {path}")
            unchanged_count += 1
    else:
        # Multiple files - use parallel processing
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = [
                executor.submit(convert_file, path, args.no_types)
                for path in python_files
            ]

            # Process results as they complete
            for future in as_completed(futures):
                path, changed, error = future.result()
                if error:
                    print(f"Error processing {path}: {error}")
                    error_count += 1
                elif changed:
                    print(f"Converted: {path}")
                    converted_count += 1
                else:
                    if args.verbose:
                        print(f"No changes: {path}")
                    unchanged_count += 1

    # Print summary
    print(
        f"\nSummary: {converted_count} converted, {unchanged_count} unchanged, {error_count} errors"
    )
