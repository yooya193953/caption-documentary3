#!/usr/bin/env python3
"""
Extract all project files from agent-38ccb57b.jsonl
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict

class FileExtractor:
    def __init__(self, jsonl_path, output_dir):
        self.jsonl_path = jsonl_path
        self.output_dir = output_dir
        self.files = {}  # path -> {content, line_num, source}

    def parse_jsonl(self):
        """Parse JSONL and extract all file contents"""
        print(f"Parsing {self.jsonl_path}...")

        line_num = 0
        with open(self.jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line_num += 1
                try:
                    entry = json.loads(line.strip())
                    self.process_entry(entry, line_num)
                except Exception as e:
                    print(f"Warning: Line {line_num}: {e}")

        print(f"Processed {line_num} lines")

    def process_entry(self, entry, line_num):
        """Process a single JSONL entry"""
        # Check for toolUseResult field (direct result)
        if 'toolUseResult' in entry:
            result = entry['toolUseResult']
            if isinstance(result, dict):
                self.extract_from_result(result, line_num)

        # Check message content for tool results
        message = entry.get('message', {})
        content = message.get('content', [])

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    # Tool use with input parameters (Write operations)
                    if item.get('type') == 'tool_use':
                        tool_name = item.get('name', '')
                        tool_input = item.get('input', {})

                        if tool_name == 'Write':
                            self.extract_write_operation(tool_input, line_num)
                        elif tool_name == 'Edit':
                            self.extract_edit_operation(tool_input, line_num)

                    # Tool result with content
                    elif item.get('type') == 'tool_result':
                        content_text = item.get('content', '')
                        if isinstance(content_text, str):
                            self.extract_from_content_text(content_text, line_num)

    def extract_from_result(self, result, line_num):
        """Extract file from direct tool result"""
        # Write operation result
        if result.get('type') == 'create' or 'filePath' in result:
            file_path = result.get('filePath', '')
            content = result.get('content', '')
            if self.is_valid_file(file_path) and content:
                rel_path = self.get_rel_path(file_path)
                print(f"  [{line_num}] Found Write: {rel_path}")
                self.store_file(rel_path, content, line_num, 'Write')

        # Edit operation result
        if 'originalFile' in result:
            # For edits, we'd need to track the path separately
            pass

    def extract_write_operation(self, tool_input, line_num):
        """Extract Write tool parameters"""
        file_path = tool_input.get('file_path', '')
        content = tool_input.get('content', '')

        if self.is_valid_file(file_path) and content:
            rel_path = self.get_rel_path(file_path)
            print(f"  [{line_num}] Found Write operation: {rel_path}")
            self.store_file(rel_path, content, line_num, 'Write')

    def extract_edit_operation(self, tool_input, line_num):
        """Extract Edit tool parameters"""
        file_path = tool_input.get('file_path', '')
        if self.is_valid_file(file_path):
            rel_path = self.get_rel_path(file_path)
            print(f"  [{line_num}] Found Edit operation: {rel_path}")
            # We'll track edits but may not have full content

    def extract_from_content_text(self, content_text, line_num):
        """Extract file content from tool_result content text"""
        # Look for file content in formatted output
        if content_text.startswith('File created successfully'):
            # Extract path if available
            pass

    def is_valid_file(self, file_path):
        """Check if file path is valid project file"""
        if not file_path:
            return False
        if not file_path.startswith('/tmp/cc-agent/60989477/project/'):
            return False
        # Exclude Python extraction scripts
        if file_path.endswith('extract_files.py') or file_path.endswith('restore_project.py'):
            return False
        if file_path.endswith('agent-38ccb57b.jsonl'):
            return False
        return True

    def get_rel_path(self, file_path):
        """Get relative path from absolute"""
        prefix = '/tmp/cc-agent/60989477/project/'
        if file_path.startswith(prefix):
            return file_path[len(prefix):]
        return file_path

    def store_file(self, rel_path, content, line_num, source):
        """Store file content (keep latest version)"""
        if rel_path not in self.files or self.files[rel_path]['line_num'] < line_num:
            self.files[rel_path] = {
                'content': content,
                'line_num': line_num,
                'source': source
            }

    def write_files(self):
        """Write all extracted files to disk"""
        print(f"\nWriting {len(self.files)} files...")

        created_dirs = set()
        created_files = 0

        for rel_path, file_info in sorted(self.files.items()):
            full_path = os.path.join(self.output_dir, rel_path)

            # Create directory
            dir_path = os.path.dirname(full_path)
            if dir_path and dir_path not in created_dirs:
                os.makedirs(dir_path, exist_ok=True)
                created_dirs.add(dir_path)

            # Write file
            try:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(file_info['content'])
                created_files += 1
                size = len(file_info['content'])
                print(f"  Created: {rel_path} ({size} bytes, line {file_info['line_num']})")
            except Exception as e:
                print(f"  ERROR writing {rel_path}: {e}")

        print(f"\nCreated {created_files} files in {len(created_dirs)} directories")

    def print_summary(self):
        """Print summary of extracted files"""
        print("\n" + "="*70)
        print("EXTRACTED FILES SUMMARY")
        print("="*70)

        # Group by directory
        by_dir = defaultdict(list)
        for rel_path in sorted(self.files.keys()):
            dir_name = os.path.dirname(rel_path) or "root"
            by_dir[dir_name].append(rel_path)

        for dir_name in sorted(by_dir.keys()):
            print(f"\n{dir_name}/")
            for file_path in sorted(by_dir[dir_name]):
                file_name = os.path.basename(file_path)
                size = len(self.files[file_path]['content'])
                print(f"  - {file_name} ({size} bytes)")

        print(f"\nTotal: {len(self.files)} files")

def main():
    jsonl_path = '/tmp/cc-agent/60989477/project/agent-38ccb57b.jsonl'
    output_dir = '/tmp/cc-agent/60989477/project'

    print("="*70)
    print("EXTRACTING FILES FROM agent-38ccb57b.jsonl")
    print("="*70)
    print()

    extractor = FileExtractor(jsonl_path, output_dir)
    extractor.parse_jsonl()
    extractor.print_summary()

    print("\n" + "="*70)
    print("Writing files to disk...")
    print("="*70)

    extractor.write_files()

    print("\n" + "="*70)
    print("EXTRACTION COMPLETE!")
    print("="*70)

if __name__ == '__main__':
    main()
