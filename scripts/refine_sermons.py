import re
import os
from pathlib import Path

def extract_korean_sermon(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    korean_lines = []
    capture = False
    current_speaker = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if line.startswith('Attendees 1'):
            current_speaker = 'korean'
            text = line.replace('Attendees 1', '').strip()
            if text:
                korean_lines.append(text)
            continue
        elif line.startswith('Attendees 2'):
            current_speaker = 'english'
            continue
        
        if current_speaker == 'korean':
            korean_lines.append(line)
    
    full_text = '\n'.join(korean_lines)
    full_text = re.sub(r'\d{4}\.\d{2}\.\d{2}.*?\n', '', full_text)
    full_text = re.sub(r'^rt$', '', full_text, flags=re.MULTILINE)
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)
    
    return full_text.strip()

def process_all_sermons(source_dir, output_dir):
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    txt_files = list(Path(source_dir).glob('*.txt'))
    print(f'총 {len(txt_files)}개의 파일 발견')
    
    for txt_file in txt_files:
        try:
            korean_text = extract_korean_sermon(str(txt_file))
            
            if len(korean_text) < 100:
                print(f'  건너뜀 (내용 너무 짧음): {txt_file.name}')
                continue
            
            output_path = Path(output_dir) / f'정제_{txt_file.name}'
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(korean_text)
            
            print(f'  완료: {txt_file.name} ({len(korean_text)}자)')
        except Exception as e:
            print(f'  오류: {txt_file.name} - {e}')

if __name__ == '__main__':
    source_dir = r'c:\Desktop\korean-gospel-ai\data\documents'
    output_dir = r'c:\Desktop\korean-gospel-ai\data\documents_refined'
    
    process_all_sermons(source_dir, output_dir)
    print('\n정제 완료!')
