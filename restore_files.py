#!/usr/bin/env python3
import json
import os
from pathlib import Path

files = {}

with open('/tmp/cc-agent/60989477/.claude/projects/-tmp-cc-agent-60989477-project/9deab743-7a47-4f7f-8ddd-4c4f31d3ed05.jsonl', 'r') as f:
    for line in f:
        try:
            data = json.loads(line)

            if 'toolUseResult' in data:
                result = data['toolUseResult']

                if 'file' in result and 'filePath' in result['file']:
                    file_path = result['file']['filePath']
                    content = result['file'].get('content', '')
                    if content:
                        files[file_path] = content

                if 'filePath' in result:
                    file_path = result['filePath']

                    if 'originalFile' in result:
                        files[file_path] = result['originalFile']

                    if 'newString' in result and 'oldString' in result:
                        if file_path in files:
                            files[file_path] = files[file_path].replace(
                                result['oldString'],
                                result['newString']
                            )
        except Exception as e:
            continue

for file_path, content in files.items():
    if file_path.startswith('/tmp/cc-agent/60989477/project/') and content and file_path != '/tmp/cc-agent/60989477/project/extract_files.py' and file_path != '/tmp/cc-agent/60989477/project/restore_files.py':
        dir_path = os.path.dirname(file_path)
        os.makedirs(dir_path, exist_ok=True)

        with open(file_path, 'w') as f:
            f.write(content)

        print(f"Restored: {file_path}")
