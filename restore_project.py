#!/usr/bin/env python3
"""
Comprehensive JSONL Project Restore Script
Parses Claude Code history file and extracts all project files
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, Optional, List, Tuple

class ProjectRestorer:
    def __init__(self, jsonl_path: str, project_root: str):
        self.jsonl_path = jsonl_path
        self.project_root = project_root
        self.file_states: Dict[str, dict] = {}  # path -> {content, timestamp, line_num}
        self.edit_operations: List[Tuple[str, dict]] = []  # (path, edit_info)

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
                    print(f"Warning: Failed to parse line {line_num}: {e}")
                    continue
                except Exception as e:
                    print(f"Warning: Error processing line {line_num}: {e}")
                    continue

        print(f"Processed {line_num} lines from JSONL file")

    def process_entry(self, entry: dict, line_num: int):
        """Process a single JSONL entry"""
        # Check if this is an assistant message with tool use results
        message = entry.get('message', {})

        if message.get('role') == 'assistant':
            content = message.get('content', [])

            for item in content:
                # Handle Read tool results
                if item.get('type') == 'tool_result':
                    tool_use = item.get('tool_use', {})
                    tool_result = item.get('tool_result', {})

                    tool_name = tool_use.get('name', '')

                    if tool_name == 'Read':
                        self.process_read_result(tool_use, tool_result, line_num)
                    elif tool_name == 'Edit':
                        self.process_edit_result(tool_use, tool_result, line_num)
                    elif tool_name == 'Write':
                        self.process_write_result(tool_use, tool_result, line_num)

    def process_read_result(self, tool_use: dict, tool_result: dict, line_num: int):
        """Process Read tool results"""
        params = tool_use.get('params', {})
        file_path = params.get('file_path', '')

        if not self.is_project_file(file_path):
            return

        # Extract content from tool result
        content = tool_result.get('file', {}).get('content')

        if content is not None:
            rel_path = self.get_relative_path(file_path)
            print(f"  [{line_num}] Read: {rel_path}")

            # Store or update file state
            if rel_path not in self.file_states or self.file_states[rel_path]['line_num'] < line_num:
                self.file_states[rel_path] = {
                    'content': content,
                    'line_num': line_num,
                    'source': 'Read'
                }

    def process_edit_result(self, tool_use: dict, tool_result: dict, line_num: int):
        """Process Edit tool results"""
        params = tool_use.get('params', {})
        file_path = params.get('file_path', '')

        if not self.is_project_file(file_path):
            return

        rel_path = self.get_relative_path(file_path)

        # Get original file content from tool result
        original_file = tool_result.get('originalFile')
        old_string = params.get('old_string', '')
        new_string = params.get('new_string', '')
        replace_all = params.get('replace_all', False)

        if original_file is not None:
            print(f"  [{line_num}] Edit: {rel_path} (has original)")

            # Store the original file first (if we don't have it or this is more recent)
            if rel_path not in self.file_states or self.file_states[rel_path]['line_num'] < line_num:
                self.file_states[rel_path] = {
                    'content': original_file,
                    'line_num': line_num,
                    'source': 'Edit-original'
                }

            # Apply the edit
            if old_string and new_string is not None:
                try:
                    if replace_all:
                        modified_content = original_file.replace(old_string, new_string)
                    else:
                        # Replace only first occurrence
                        modified_content = original_file.replace(old_string, new_string, 1)

                    # Update with modified content
                    self.file_states[rel_path] = {
                        'content': modified_content,
                        'line_num': line_num,
                        'source': 'Edit-applied'
                    }
                    print(f"    Applied edit to {rel_path}")
                except Exception as e:
                    print(f"    Warning: Failed to apply edit: {e}")

    def process_write_result(self, tool_use: dict, tool_result: dict, line_num: int):
        """Process Write tool results"""
        params = tool_use.get('params', {})
        file_path = params.get('file_path', '')
        content = params.get('content', '')

        if not self.is_project_file(file_path):
            return

        rel_path = self.get_relative_path(file_path)
        print(f"  [{line_num}] Write: {rel_path}")

        # Store or update file state
        if rel_path not in self.file_states or self.file_states[rel_path]['line_num'] < line_num:
            self.file_states[rel_path] = {
                'content': content,
                'line_num': line_num,
                'source': 'Write'
            }

    def is_project_file(self, file_path: str) -> bool:
        """Check if file path is within project and not a .py file"""
        if not file_path.startswith('/tmp/cc-agent/60989477/project/'):
            return False
        if file_path.endswith('.py'):
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

        for rel_path, file_info in sorted(self.file_states.items()):
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
                print(f"  Created: {rel_path} (from {file_info['source']}, line {file_info['line_num']})")
            except Exception as e:
                print(f"  ERROR: Failed to write {rel_path}: {e}")

        print(f"\nRestoration complete!")
        print(f"  Created {len(created_dirs)} directories")
        print(f"  Created {created_files} files")

    def print_summary(self):
        """Print summary of extracted files"""
        print("\n" + "="*70)
        print("PROJECT FILE SUMMARY")
        print("="*70)

        # Group files by directory
        files_by_dir = defaultdict(list)
        for rel_path in sorted(self.file_states.keys()):
            dir_name = os.path.dirname(rel_path) or "root"
            files_by_dir[dir_name].append(rel_path)

        for dir_name in sorted(files_by_dir.keys()):
            print(f"\n{dir_name}/")
            for file_path in sorted(files_by_dir[dir_name]):
                file_name = os.path.basename(file_path)
                size = len(self.file_states[file_path]['content'])
                print(f"  - {file_name} ({size} bytes)")

        print(f"\nTotal files: {len(self.file_states)}")

def main():
    jsonl_path = '/tmp/cc-agent/60989477/.claude/projects/-tmp-cc-agent-60989477-project/9deab743-7a47-4f7f-8ddd-4c4f31d3ed05.jsonl'
    project_root = '/tmp/cc-agent/60989477/project'

    print("="*70)
    print("CLAUDE CODE PROJECT RESTORATION")
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

    # Ask for confirmation
    print("\n" + "="*70)
    response = input("Proceed with file restoration? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Restoration cancelled.")
        sys.exit(0)

    # Restore all files
    restorer.restore_files()

    print("\n" + "="*70)
    print("RESTORATION COMPLETE!")
    print("="*70)

if __name__ == '__main__':
    main()
