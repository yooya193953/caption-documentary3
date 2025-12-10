#!/usr/bin/env python3
"""
Extract all project files from agent-38ccb57b.jsonl
"""

import json
import os
import sys

def extract_files():
    jsonl_file = '/tmp/cc-agent/60989477/project/agent-38ccb57b.jsonl'
    output_dir = '/tmp/cc-agent/60989477/project'
    
    files = {}
    
    print(f"Parsing {jsonl_file}...")
    
    line_num = 0
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            line_num += 1
            try:
                data = json.loads(line.strip())
                
                # Check toolUseResult field
                if 'toolUseResult' in data:
                    result = data['toolUseResult']
                    
                    # Write operation with content and filePath
                    if isinstance(result, dict):
                        if 'filePath' in result and 'content' in result:
                            file_path = result['filePath']
                            content = result['content']
                            if is_valid_project_file(file_path):
                                files[file_path] = {
                                    'content': content,
                                    'line': line_num,
                                    'source': 'toolUseResult'
                                }
                                print(f"  [{line_num}] Found: {get_rel_path(file_path)}")
                        
                        # Read operation with file object
                        if 'file' in result and isinstance(result['file'], dict):
                            if 'filePath' in result['file'] and 'content' in result['file']:
                                file_path = result['file']['filePath']
                                content = result['file']['content']
                                if is_valid_project_file(file_path):
                                    files[file_path] = {
                                        'content': content,
                                        'line': line_num,
                                        'source': 'Read'
                                    }
                                    print(f"  [{line_num}] Found: {get_rel_path(file_path)}")
                
                # Check message content for tool_use
                msg = data.get('message', {})
                content_list = msg.get('content', [])
                
                if isinstance(content_list, list):
                    for item in content_list:
                        if isinstance(item, dict) and item.get('type') == 'tool_use':
                            tool_name = item.get('name', '')
                            tool_input = item.get('input', {})
                            
                            # Write tool
                            if tool_name == 'Write':
                                file_path = tool_input.get('file_path', '')
                                content = tool_input.get('content', '')
                                if is_valid_project_file(file_path) and content:
                                    files[file_path] = {
                                        'content': content,
                                        'line': line_num,
                                        'source': 'Write'
                                    }
                                    print(f"  [{line_num}] Found: {get_rel_path(file_path)}")
                            
                            # Edit tool
                            elif tool_name == 'Edit':
                                file_path = tool_input.get('file_path', '')
                                if is_valid_project_file(file_path):
                                    print(f"  [{line_num}] Edit: {get_rel_path(file_path)}")
                
            except Exception as e:
                # Silently skip malformed lines
                pass
    
    print(f"\nProcessed {line_num} lines")
    print(f"Found {len(files)} files")
    
    # Write files
    print("\nWriting files...")
    created_dirs = set()
    
    for file_path, file_info in sorted(files.items()):
        # Create directory
        dir_path = os.path.dirname(file_path)
        if dir_path and dir_path not in created_dirs:
            os.makedirs(dir_path, exist_ok=True)
            created_dirs.add(dir_path)
        
        # Write file
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file_info['content'])
            
            rel_path = get_rel_path(file_path)
            size = len(file_info['content'])
            print(f"  Created: {rel_path} ({size} bytes)")
        except Exception as e:
            print(f"  ERROR: {file_path}: {e}")
    
    print(f"\nCreated {len(files)} files in {len(created_dirs)} directories")
    
    # Print summary
    print("\n" + "="*70)
    print("EXTRACTED FILES:")
    print("="*70)
    for file_path in sorted(files.keys()):
        rel_path = get_rel_path(file_path)
        size = len(files[file_path]['content'])
        print(f"  {rel_path} ({size} bytes)")

def is_valid_project_file(file_path):
    """Check if file is a valid project file"""
    if not file_path:
        return False
    if not file_path.startswith('/tmp/cc-agent/60989477/project/'):
        return False
    # Exclude extraction scripts and JSONL files
    if 'extract_' in file_path and file_path.endswith('.py'):
        return False
    if 'restore_' in file_path and file_path.endswith('.py'):
        return False
    if file_path.endswith('.jsonl'):
        return False
    return True

def get_rel_path(file_path):
    """Get relative path"""
    prefix = '/tmp/cc-agent/60989477/project/'
    if file_path.startswith(prefix):
        return file_path[len(prefix):]
    return file_path

if __name__ == '__main__':
    extract_files()
