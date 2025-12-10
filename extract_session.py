#!/usr/bin/env python3
"""
Comprehensive JSONL Session File Extractor
Extracts ALL file contents from Claude session history with chronological tracking
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

class FileStateTracker:
    """Tracks file states chronologically with version history"""

    def __init__(self):
        self.files = defaultdict(list)  # filepath -> list of (timestamp, content, source)
        self.partial_reads = defaultdict(list)  # filepath -> list of partial read contents

    def add_write(self, filepath: str, content: str, timestamp: str, source: str):
        """Add a complete file write"""
        self.files[filepath].append({
            'timestamp': timestamp,
            'content': content,
            'source': source,
            'type': 'write'
        })

    def add_read(self, filepath: str, content: str, timestamp: str, is_partial: bool = False):
        """Add a file read result"""
        if is_partial:
            self.partial_reads[filepath].append({
                'timestamp': timestamp,
                'content': content,
                'type': 'partial_read'
            })
        else:
            self.files[filepath].append({
                'timestamp': timestamp,
                'content': content,
                'source': 'read_result',
                'type': 'read'
            })

    def add_edit(self, filepath: str, old_string: str, new_string: str, timestamp: str):
        """Add an edit operation"""
        self.files[filepath].append({
            'timestamp': timestamp,
            'old_string': old_string,
            'new_string': new_string,
            'source': 'edit_operation',
            'type': 'edit'
        })

    def get_final_content(self, filepath: str) -> Optional[str]:
        """Get the final content of a file after applying all operations"""
        if filepath not in self.files and filepath not in self.partial_reads:
            return None

        # Sort all operations by timestamp
        operations = sorted(self.files.get(filepath, []), key=lambda x: x['timestamp'])

        if not operations:
            # Try to reconstruct from partial reads
            return self._reconstruct_from_partials(filepath)

        # Start with the first complete write or read
        content = None
        for op in operations:
            if op['type'] in ['write', 'read']:
                content = op['content']
                break

        if content is None:
            # No complete content found, try partial reconstruction
            return self._reconstruct_from_partials(filepath)

        # Apply all edits in order
        for op in operations:
            if op['type'] == 'edit':
                old_str = op['old_string']
                new_str = op['new_string']

                # Apply the edit (should only replace once)
                if old_str in content:
                    content = content.replace(old_str, new_str, 1)

            elif op['type'] in ['write', 'read']:
                # Update to latest complete content
                content = op['content']

        return content

    def _reconstruct_from_partials(self, filepath: str) -> Optional[str]:
        """Try to reconstruct file from partial reads"""
        if filepath not in self.partial_reads:
            return None

        partials = sorted(self.partial_reads[filepath], key=lambda x: x['timestamp'])
        if not partials:
            return None

        # Just return the last partial we found
        return partials[-1]['content']

    def get_all_files(self) -> List[str]:
        """Get all unique file paths"""
        all_paths = set(self.files.keys()) | set(self.partial_reads.keys())
        return sorted(all_paths)


def extract_content_from_message(msg_content: List[dict], timestamp: str, tracker: FileStateTracker):
    """Extract file contents from message.content array"""

    for item in msg_content:
        if not isinstance(item, dict):
            continue

        item_type = item.get('type')

        # Tool use - Write operations
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

        # Tool result - Read operations
        elif item_type == 'tool_result':
            tool_use_id = item.get('tool_use_id')
            content = item.get('content')

            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        # Check for file content in tool result
                        if c.get('type') == 'file':
                            file_content = c.get('content')
                            filepath = c.get('filePath')
                            if filepath and file_content:
                                # Check if it's a partial read (has line numbers)
                                is_partial = bool(re.search(r'^\s*\d+→', file_content, re.MULTILINE))
                                tracker.add_read(filepath, file_content, timestamp, is_partial)

                        elif c.get('type') == 'text':
                            text = c.get('text', '')
                            # Try to extract file path and content from text
                            # Format: "file: /path/to/file\n<content>"
                            match = re.match(r'file:\s*(.+?)\n(.+)', text, re.DOTALL)
                            if match:
                                filepath = match.group(1).strip()
                                file_content = match.group(2)
                                is_partial = bool(re.search(r'^\s*\d+→', file_content, re.MULTILINE))
                                tracker.add_read(filepath, file_content, timestamp, is_partial)

            elif isinstance(content, str):
                # Single string content - might be a file read result
                # Check if it looks like a file with line numbers
                if re.search(r'^\s*\d+→', content, re.MULTILINE):
                    # This is likely a partial read but we don't know the filepath from here
                    pass


def extract_from_tool_result(result_data, timestamp: str, tracker: FileStateTracker):
    """Extract file contents from toolUseResult"""

    # toolUseResult can be a string or dict
    if not isinstance(result_data, dict):
        return

    # Check for file content
    if 'file' in result_data:
        file_obj = result_data['file']
        if isinstance(file_obj, dict):
            filepath = file_obj.get('filePath')
            content = file_obj.get('content')

            if filepath and content:
                is_partial = bool(re.search(r'^\s*\d+→', content, re.MULTILINE))
                tracker.add_read(filepath, content, timestamp, is_partial)

    # Check for originalFile (Edit operations)
    if 'filePath' in result_data and 'originalFile' in result_data:
        filepath = result_data['filePath']
        content = result_data['originalFile']
        if filepath and content and isinstance(content, str):
            tracker.add_read(filepath, content, timestamp, False)


def parse_jsonl_line(line: str, tracker: FileStateTracker):
    """Parse a single JSONL line and extract file contents"""

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return

    timestamp = data.get('timestamp', '')

    # Extract from message content
    if 'message' in data:
        message = data['message']
        if 'content' in message and isinstance(message['content'], list):
            extract_content_from_message(message['content'], timestamp, tracker)

    # Extract from toolUseResult
    if 'toolUseResult' in data:
        extract_from_tool_result(data['toolUseResult'], timestamp, tracker)


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
        # If filepath is already absolute and within our project, use it
        # Otherwise, save relative to base_dir
        if filepath.startswith('/tmp/cc-agent/60989477/project/'):
            # Use the exact path
            save_path = Path(filepath)
        else:
            # Save relative to base_dir
            # Strip leading slashes
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

    session_file = '/tmp/cc-agent/60989477/.claude/projects/-tmp-cc-agent-60989477-project/9deab743-7a47-4f7f-8ddd-4c4f31d3ed05.jsonl'
    output_dir = '/tmp/cc-agent/60989477/project'

    print("=" * 80)
    print("COMPREHENSIVE JSONL SESSION FILE EXTRACTOR")
    print("=" * 80)
    print(f"\nSession file: {session_file}")
    print(f"Output directory: {output_dir}")

    # Check file exists
    if not os.path.exists(session_file):
        print(f"\nERROR: Session file not found: {session_file}")
        return

    # Get file stats
    file_size = os.path.getsize(session_file)
    print(f"File size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")

    # Count lines
    with open(session_file, 'r', encoding='utf-8') as f:
        line_count = sum(1 for _ in f)
    print(f"Total lines: {line_count}")

    print("\n" + "-" * 80)
    print("PARSING JSONL LINES...")
    print("-" * 80)

    # Create tracker
    tracker = FileStateTracker()

    # Parse all lines
    with open(session_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if i % 20 == 0:
                print(f"Processing line {i}/{line_count}...", end='\r')
            parse_jsonl_line(line.strip(), tracker)

    print(f"Processing line {line_count}/{line_count}... DONE")

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
        # Make path relative for display
        display_path = filepath.replace('/tmp/cc-agent/60989477/project/', '')
        print(f"{size:>8,} bytes  {display_path}")

    if incomplete_files:
        print("\n" + "-" * 80)
        print("INCOMPLETE/FRAGMENTED FILES")
        print("-" * 80)
        for filepath in incomplete_files:
            display_path = filepath.replace('/tmp/cc-agent/60989477/project/', '')
            print(f"  - {display_path}")

    # Generate a summary report
    report_path = os.path.join(output_dir, 'extraction_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("COMPREHENSIVE JSONL SESSION EXTRACTION REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Session file: {session_file}\n")
        f.write(f"File size: {file_size:,} bytes ({file_size / 1024:.1f} KB)\n")
        f.write(f"Total lines: {line_count}\n")
        f.write(f"Total unique files: {len(all_files)}\n")
        f.write(f"Successfully saved: {total_files}\n")
        f.write(f"Incomplete/fragmented: {len(incomplete_files)}\n\n")

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
