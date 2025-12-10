#!/usr/bin/env python3
"""
Comprehensive JSONL Project Restore Script v2
Parses Claude Code history file and extracts all project files
Handles Read results (cat -n format) and Write operations
"""

import json
import os
import sys
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, Optional, List, Tuple

class ProjectRestorer:
    def __init__(self, jsonl_path: str, project_root: str):
        self.jsonl_path = jsonl_path
        self.project_root = project_root
        self.file_states: Dict[str, dict] = {}  # path -> {content, timestamp, line_num}
        self.tool_uses: Dict[str, dict] = {}  # tool_use_id -> {name, input, line_num}

    def parse_jsonl(self):
        """Parse the entire JSONL file line by line"""
        print(f"Parsing JSONL file: {self.jsonl_path}")

        line_num = 0
        with open(self.jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line_num += 1
                try:
                    entry = json.loads(line.strip())
                    self.process_entry(entry, line_num)
                except json.JSONDecodeError as e:
                    # Some lines might have embedded JSON - skip them
                    continue
                except Exception as e:
                    print(f"Warning: Error processing line {line_num}: {e}")
                    continue

        print(f"Processed {line_num} lines from JSONL file")
        print(f"Found {len(self.file_states)} unique files")

    def process_entry(self, entry: dict, line_num: int):
        """Process a single JSONL entry"""
        message = entry.get('message', {})
        role = message.get('role')
        content = message.get('content', [])

        if role == 'assistant':
            # Track tool uses (Write, Read, Edit)
            for item in content:
                if item.get('type') == 'tool_use':
                    tool_id = item.get('id')
                    tool_name = item.get('name')
                    tool_input = item.get('input', {})

                    self.tool_uses[tool_id] = {
                        'name': tool_name,
                        'input': tool_input,
                        'line_num': line_num
                    }

                    # Process Write immediately (has content in tool_use)
                    if tool_name == 'Write':
                        self.process_write(tool_input, line_num)

        elif role == 'user':
            # Process tool results (Read, Edit results)
            for item in content:
                if item.get('type') == 'tool_result':
                    tool_id = item.get('tool_use_id')
                    tool_content = item.get('content', '')

                    if tool_id in self.tool_uses:
                        tool_info = self.tool_uses[tool_id]
                        tool_name = tool_info['name']
                        tool_input = tool_info['input']

                        if tool_name == 'Read':
                            self.process_read_result(tool_input, tool_content, line_num)
                        elif tool_name == 'Edit':
                            self.process_edit_result(tool_input, tool_content, line_num)

    def process_write(self, tool_input: dict, line_num: int):
        """Process Write tool operation"""
        file_path = tool_input.get('file_path', '')
        content = tool_input.get('content', '')

        if not self.is_project_file(file_path):
            return

        rel_path = self.get_relative_path(file_path)
        print(f"  [{line_num:3d}] Write: {rel_path} ({len(content)} bytes)")

        # Store or update file state
        if rel_path not in self.file_states or self.file_states[rel_path]['line_num'] < line_num:
            self.file_states[rel_path] = {
                'content': content,
                'line_num': line_num,
                'source': 'Write'
            }

    def process_read_result(self, tool_input: dict, tool_content: str, line_num: int):
        """Process Read tool result (cat -n format)"""
        file_path = tool_input.get('file_path', '')

        if not self.is_project_file(file_path):
            return

        # Parse cat -n format to extract actual content
        content = self.parse_cat_n_format(tool_content)

        if content is None:
            return

        rel_path = self.get_relative_path(file_path)
        print(f"  [{line_num:3d}] Read:  {rel_path} ({len(content)} bytes)")

        # Store or update file state
        if rel_path not in self.file_states or self.file_states[rel_path]['line_num'] < line_num:
            self.file_states[rel_path] = {
                'content': content,
                'line_num': line_num,
                'source': 'Read'
            }

    def process_edit_result(self, tool_input: dict, tool_content: str, line_num: int):
        """Process Edit tool result"""
        file_path = tool_input.get('file_path', '')
        old_string = tool_input.get('old_string', '')
        new_string = tool_input.get('new_string', '')
        replace_all = tool_input.get('replace_all', False)

        if not self.is_project_file(file_path):
            return

        rel_path = self.get_relative_path(file_path)

        # For Edit, we need the file content before the edit
        # Check if we already have it from a previous Read
        if rel_path in self.file_states:
            original_content = self.file_states[rel_path]['content']

            # Apply the edit
            try:
                if replace_all:
                    modified_content = original_content.replace(old_string, new_string)
                else:
                    # Replace only first occurrence
                    modified_content = original_content.replace(old_string, new_string, 1)

                print(f"  [{line_num:3d}] Edit:  {rel_path} (applied)")

                # Update with modified content
                self.file_states[rel_path] = {
                    'content': modified_content,
                    'line_num': line_num,
                    'source': 'Edit'
                }
            except Exception as e:
                print(f"    Warning: Failed to apply edit: {e}")

    def parse_cat_n_format(self, content: str) -> Optional[str]:
        """Parse cat -n formatted output to extract actual file content"""
        if not content or len(content) < 10:
            return None

        lines = content.split('\n')
        extracted_lines = []

        # Pattern to match cat -n format: optional spaces, number, tab/arrow, content
        # Example: "     1→import React from 'react';"
        # or: "     1\timport React from 'react';"
        pattern = re.compile(r'^\s*\d+[→\t](.*)$')

        for line in lines:
            match = pattern.match(line)
            if match:
                extracted_lines.append(match.group(1))
            elif extracted_lines:
                # If we've started extracting and hit a non-matching line,
                # it might be a continuation of the previous line
                # or the end of the file content
                # For safety, we'll include it if it doesn't look like a header
                if not line.strip().startswith('The file') and not line.strip().startswith('has been'):
                    extracted_lines.append(line)

        if not extracted_lines:
            return None

        return '\n'.join(extracted_lines)

    def is_project_file(self, file_path: str) -> bool:
        """Check if file path is within project and not a .py file"""
        if not file_path.startswith('/tmp/cc-agent/60989477/project/'):
            return False
        if file_path.endswith('.py') and 'restore' not in file_path.lower() and 'extract' not in file_path.lower():
            # Exclude .py files that are not our restore scripts
            return False
        return True

    def get_relative_path(self, file_path: str) -> str:
        """Convert absolute path to relative path"""
        prefix = '/tmp/cc-agent/60989477/project/'
        if file_path.startswith(prefix):
            return file_path[len(prefix):]
        return file_path

    def restore_files(self):
        """Write all extracted files to disk"""
        print(f"\nRestoring {len(self.file_states)} files...")

        created_dirs = set()
        created_files = 0
        skipped_files = []

        for rel_path, file_info in sorted(self.file_states.items()):
            # Skip our own restore scripts
            if 'restore' in rel_path.lower() or 'extract' in rel_path.lower():
                skipped_files.append(rel_path)
                continue

            full_path = os.path.join(self.project_root, rel_path)

            # Create directory if needed
            dir_path = os.path.dirname(full_path)
            if dir_path and dir_path not in created_dirs:
                os.makedirs(dir_path, exist_ok=True)
                created_dirs.add(dir_path)

            # Write file
            try:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(file_info['content'])
                created_files += 1
                print(f"  Created: {rel_path}")
            except Exception as e:
                print(f"  ERROR: Failed to write {rel_path}: {e}")

        print(f"\nRestoration complete!")
        print(f"  Created {len(created_dirs)} directories")
        print(f"  Created {created_files} files")
        if skipped_files:
            print(f"  Skipped {len(skipped_files)} restore scripts")

    def print_summary(self):
        """Print summary of extracted files"""
        print("\n" + "="*70)
        print("PROJECT FILE SUMMARY")
        print("="*70)

        # Group files by directory
        files_by_dir = defaultdict(list)
        for rel_path in sorted(self.file_states.keys()):
            # Skip restore scripts in summary
            if 'restore' in rel_path.lower() or 'extract' in rel_path.lower():
                continue
            dir_name = os.path.dirname(rel_path) or "root"
            files_by_dir[dir_name].append(rel_path)

        total_size = 0
        for dir_name in sorted(files_by_dir.keys()):
            print(f"\n{dir_name}/")
            for file_path in sorted(files_by_dir[dir_name]):
                file_name = os.path.basename(file_path)
                size = len(self.file_states[file_path]['content'])
                total_size += size
                source = self.file_states[file_path]['source']
                print(f"  - {file_name:40s} {size:>8,} bytes  ({source})")

        print(f"\n{'='*70}")
        print(f"Total: {len(files_by_dir)} directories, {sum(len(f) for f in files_by_dir.values())} files, {total_size:,} bytes")
        print(f"{'='*70}")

def main():
    jsonl_path = '/tmp/cc-agent/60989477/.claude/projects/-tmp-cc-agent-60989477-project/9deab743-7a47-4f7f-8ddd-4c4f31d3ed05.jsonl'
    project_root = '/tmp/cc-agent/60989477/project'

    print("="*70)
    print("CLAUDE CODE PROJECT RESTORATION v2")
    print("="*70)
    print(f"JSONL History: {jsonl_path}")
    print(f"Project Root:  {project_root}")
    print("="*70)
    print()

    if not os.path.exists(jsonl_path):
        print(f"ERROR: JSONL file not found: {jsonl_path}")
        sys.exit(1)

    restorer = ProjectRestorer(jsonl_path, project_root)

    # Parse the JSONL file
    restorer.parse_jsonl()

    # Print summary of what we found
    restorer.print_summary()

    # Restore all files (auto-confirm)
    print("\n" + "="*70)
    print("Proceeding with restoration...")
    print("="*70)

    restorer.restore_files()

    print("\n" + "="*70)
    print("RESTORATION COMPLETE!")
    print("="*70)

if __name__ == '__main__':
    main()
