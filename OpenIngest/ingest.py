from __future__ import annotations

import argparse

from OpenIngest.orchestrator import run_pipeline


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenIngest CLI")
    parser.add_argument("path", help="Path to DOCX/PDF file")
    parser.add_argument("--metadata", default="{}", help="JSON metadata payload")
    parser.add_argument("--config", default=None, help="Path to YAML/JSON config")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    import json

    metadata = json.loads(args.metadata) if args.metadata else {}
    if not isinstance(metadata, dict):
        metadata = {}
    stats = run_pipeline(args.path, metadata, args.config)
    print(
        {
            "source_uri": stats.source_uri,
            "doc_id": stats.doc_id,
            "images_total": stats.images_total,
            "parents_total": stats.parents_total,
            "children_total": stats.children_total,
            "uploaded_rows": stats.uploaded_rows,
            "skipped_as_unchanged": stats.skipped_as_unchanged,
        }
    )


if __name__ == "__main__":
    main()
