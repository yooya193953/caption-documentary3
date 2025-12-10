#!/usr/bin/env python3
"""
Comprehensive Multi-Session JSONL File Extractor
Extracts ALL file contents from ALL Claude session files
"""

import json
import os
import re
import glob
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

class FileStateTracker:
    """Tracks file states chronologically with version history"""

    def __init__(self):
        self.files = defaultdict(list)  # filepath -> list of operations
        self.stats = {
            'writes': 0,
            'reads': 0,
            'edits': 0,
            'partial_reads': 0
        }

    def add_write(self, filepath: str, content: str, timestamp: str, source: str):
        """Add a complete file write"""
        self.files[filepath].append({
            'timestamp': timestamp,
            'content': content,
            'source': source,
            'type': 'write'
        })
        self.stats['writes'] += 1
        print(f"    [WRITE] {filepath} ({len(content)} bytes)")

    def add_read(self, filepath: str, content: str, timestamp: str, is_partial: bool = False, total_lines: int = None):
        """Add a file read result"""
        if is_partial:
            self.files[filepath].append({
                'timestamp': timestamp,
                'content': content,
                'source': 'partial_read',
                'type': 'partial_read',
                'total_lines': total_lines
            })
            self.stats['partial_reads'] += 1
            print(f"    [PARTIAL READ] {filepath} ({len(content)} bytes, {total_lines} total lines)")
        else:
            self.files[filepath].append({
                'timestamp': timestamp,
                'content': content,
                'source': 'read_result',
                'type': 'read'
            })
            self.stats['reads'] += 1
            print(f"    [READ] {filepath} ({len(content)} bytes)")

    def add_edit(self, filepath: str, old_string: str, new_string: str, timestamp: str):
        """Add an edit operation"""
        self.files[filepath].append({
            'timestamp': timestamp,
            'old_string': old_string,
            'new_string': new_string,
            'source': 'edit_operation',
            'type': 'edit'
        })
        self.stats['edits'] += 1
        print(f"    [EDIT] {filepath} (-{len(old_string)}, +{len(new_string)} bytes)")

    def get_final_content(self, filepath: str) -> Optional[str]:
        """Get the final content of a file after applying all operations"""
        if filepath not in self.files:
            return None

        # Sort all operations by timestamp
        operations = sorted(self.files[filepath], key=lambda x: x['timestamp'])

        # Find the best starting point (prefer full reads/writes over partials)
        content = None
        start_idx = 0

        # Look for the last complete write or read
        for i, op in enumerate(operations):
            if op['type'] in ['write', 'read']:
                content = op['content']
                start_idx = i + 1

        # If no complete content, try to use the longest partial read
        if content is None:
            best_partial = None
            best_size = 0
            for i, op in enumerate(operations):
                if op['type'] == 'partial_read':
                    if len(op['content']) > best_size:
                        best_size = len(op['content'])
                        best_partial = op
                        start_idx = i + 1

            if best_partial:
                content = best_partial['content']

        if content is None:
            return None

        # Apply all subsequent edits in order
        for op in operations[start_idx:]:
            if op['type'] == 'edit':
                old_str = op['old_string']
                new_str = op['new_string']

                # Apply the edit (should only replace once)
                if old_str in content:
                    content = content.replace(old_str, new_str, 1)
                else:
                    # Edit couldn't be applied - content might be outdated
                    pass

            elif op['type'] in ['write', 'read']:
                # Update to latest complete content
                content = op['content']

        return content

    def get_all_files(self) -> List[str]:
        """Get all unique file paths"""
        return sorted(self.files.keys())


def extract_content_from_message(msg_content: List[dict], timestamp: str, tracker: FileStateTracker):
    """Extract file contents from message.content array"""

    for item in msg_content:
        if not isinstance(item, dict):
            continue

        item_type = item.get('type')

        # Tool use - Write, Edit operations in the request
        if item_type == 'tool_use':
            tool_name = item.get('name')
            tool_input = item.get('input', {})

            if tool_name == 'Write':
                filepath = tool_input.get('file_path')
                content = tool_input.get('content')
                if filepath and content:
                    tracker.add_write(filepath, content, timestamp, 'Write_tool')

            elif tool_name == 'Edit':
                filepath = tool_input.get('file_path')
                old_string = tool_input.get('old_string')
                new_string = tool_input.get('new_string')
                if filepath and old_string is not None and new_string is not None:
                    tracker.add_edit(filepath, old_string, new_string, timestamp)


def extract_from_tool_result(result_data, timestamp: str, tracker: FileStateTracker):
    """Extract file contents from toolUseResult (top-level field)"""

    if not isinstance(result_data, dict):
        return

    result_type = result_data.get('type')

    # Type: 'text' with file object
    if result_type == 'text' and 'file' in result_data:
        file_obj = result_data['file']
        if isinstance(file_obj, dict):
            filepath = file_obj.get('filePath')
            content = file_obj.get('content')

            if filepath and content:
                # Check if partial (has numLines, startLine info)
                num_lines = file_obj.get('numLines')
                total_lines = file_obj.get('totalLines')
                is_partial = num_lines and total_lines and num_lines < total_lines

                tracker.add_read(filepath, content, timestamp, is_partial, total_lines)

    # Type: 'create' - Write operation result
    elif result_type == 'create':
        filepath = result_data.get('filePath')
        content = result_data.get('content')
        if filepath and content:
            tracker.add_write(filepath, content, timestamp, 'Write_result')

    # Type: 'edit' - Edit operation result (contains pre-edit state)
    elif result_type == 'edit':
        filepath = result_data.get('filePath')
        original_file = result_data.get('originalFile')
        if filepath and original_file:
            # The originalFile is the state BEFORE the edit
            # We track this as a read of the pre-edit state
            tracker.add_read(filepath, original_file, timestamp, False)


def parse_jsonl_line(line: str, tracker: FileStateTracker):
    """Parse a single JSONL line and extract file contents"""

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return

    timestamp = data.get('timestamp', '')

    # Extract from message content (tool use requests)
    if 'message' in data:
        message = data['message']
        if 'content' in message and isinstance(message['content'], list):
            extract_content_from_message(message['content'], timestamp, tracker)

    # Extract from toolUseResult (top-level field - tool responses)
    if 'toolUseResult' in data:
        extract_from_tool_result(data['toolUseResult'], timestamp, tracker)


def process_session_file(filepath: str, tracker: FileStateTracker):
    """Process a single session file"""

    file_size = os.path.getsize(filepath)
    with open(filepath, 'r', encoding='utf-8') as f:
        line_count = sum(1 for _ in f)

    print(f"\n  File: {os.path.basename(filepath)}")
    print(f"  Size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")
    print(f"  Lines: {line_count}")

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            parse_jsonl_line(line.strip(), tracker)


def save_files(tracker: FileStateTracker, base_dir: str) -> Tuple[int, List[Tuple[str, int]], List[str]]:
    """
    Save all extracted files to disk
    Returns: (total_files, [(filepath, size)], incomplete_files)
    """

    base_path = Path(base_dir)
    saved_files = []
    incomplete_files = []

    for filepath in tracker.get_all_files():
        content = tracker.get_final_content(filepath)

        if content is None:
            incomplete_files.append(filepath)
            continue

        # Check if this looks incomplete (partial read with line numbers)
        is_incomplete = bool(re.search(r'^\s*\d+→', content, re.MULTILINE))

        # Determine the save path
        if filepath.startswith('/tmp/cc-agent/60989477/project/'):
            save_path = Path(filepath)
        else:
            rel_path = filepath.lstrip('/')
            save_path = base_path / rel_path

        # Create parent directories
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        try:
            save_path.write_text(content, encoding='utf-8')
            size = len(content)
            saved_files.append((str(save_path), size))

            if is_incomplete:
                incomplete_files.append(str(save_path))
        except Exception as e:
            print(f"Error saving {save_path}: {e}")
            incomplete_files.append(str(save_path))

    return len(saved_files), saved_files, incomplete_files


def main():
    """Main extraction function"""

    sessions_dir = '/tmp/cc-agent/60989477/.claude/projects/-tmp-cc-agent-60989477-project/'
    output_dir = '/tmp/cc-agent/60989477/project'

    print("=" * 80)
    print("COMPREHENSIVE MULTI-SESSION JSONL FILE EXTRACTOR")
    print("=" * 80)

    # Find all session files
    pattern = os.path.join(sessions_dir, '*.jsonl')
    session_files = glob.glob(pattern)
    session_files = [f for f in session_files if os.path.getsize(f) > 0]  # Skip empty files
    session_files.sort(key=lambda f: os.path.getsize(f), reverse=True)  # Process largest first

    print(f"\nFound {len(session_files)} session files")
    print(f"Output directory: {output_dir}")

    print("\n" + "-" * 80)
    print("PROCESSING SESSION FILES...")
    print("-" * 80)

    # Create tracker
    tracker = FileStateTracker()

    # Process all session files
    for session_file in session_files:
        process_session_file(session_file, tracker)

    print("\n" + "-" * 80)
    print("EXTRACTION STATS")
    print("-" * 80)
    print(f"Writes: {tracker.stats['writes']}")
    print(f"Reads: {tracker.stats['reads']}")
    print(f"Edits: {tracker.stats['edits']}")
    print(f"Partial reads: {tracker.stats['partial_reads']}")

    print("\n" + "-" * 80)
    print("RECONSTRUCTING FILE STATES...")
    print("-" * 80)

    all_files = tracker.get_all_files()
    print(f"Found {len(all_files)} unique file paths")

    print("\n" + "-" * 80)
    print("SAVING FILES...")
    print("-" * 80)

    total_files, saved_files, incomplete_files = save_files(tracker, output_dir)

    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)

    print(f"\nTotal unique files found: {len(all_files)}")
    print(f"Successfully saved: {total_files}")
    print(f"Incomplete/fragmented: {len(incomplete_files)}")

    print("\n" + "-" * 80)
    print("FILE LIST (sorted by size)")
    print("-" * 80)

    # Sort by size descending
    saved_files.sort(key=lambda x: x[1], reverse=True)

    for filepath, size in saved_files:
        display_path = filepath.replace('/tmp/cc-agent/60989477/project/', '')
        print(f"{size:>8,} bytes  {display_path}")

    if incomplete_files:
        print("\n" + "-" * 80)
        print("INCOMPLETE/FRAGMENTED FILES (with line numbers)")
        print("-" * 80)
        for filepath in incomplete_files:
            display_path = filepath.replace('/tmp/cc-agent/60989477/project/', '')
            print(f"  - {display_path}")

    # Generate a summary report
    report_path = os.path.join(output_dir, 'extraction_report_all.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("COMPREHENSIVE MULTI-SESSION JSONL EXTRACTION REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Processed {len(session_files)} session files\n")
        f.write(f"Total unique files: {len(all_files)}\n")
        f.write(f"Successfully saved: {total_files}\n")
        f.write(f"Incomplete/fragmented: {len(incomplete_files)}\n\n")

        f.write("Extraction Stats:\n")
        f.write(f"  Writes: {tracker.stats['writes']}\n")
        f.write(f"  Reads: {tracker.stats['reads']}\n")
        f.write(f"  Edits: {tracker.stats['edits']}\n")
        f.write(f"  Partial reads: {tracker.stats['partial_reads']}\n\n")

        f.write("-" * 80 + "\n")
        f.write("ALL FILES (sorted by size)\n")
        f.write("-" * 80 + "\n")
        for filepath, size in saved_files:
            display_path = filepath.replace('/tmp/cc-agent/60989477/project/', '')
            f.write(f"{size:>8,} bytes  {display_path}\n")

        if incomplete_files:
            f.write("\n" + "-" * 80 + "\n")
            f.write("INCOMPLETE/FRAGMENTED FILES\n")
            f.write("-" * 80 + "\n")
            for filepath in incomplete_files:
                display_path = filepath.replace('/tmp/cc-agent/60989477/project/', '')
                f.write(f"  - {display_path}\n")

    print(f"\nReport saved to: {report_path}")


if __name__ == '__main__':
    main()
