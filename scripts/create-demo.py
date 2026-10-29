"""Create an explicit self-authored local reading fixture, never a YouTube result.

Developer/demo use only. Refuses an existing destination and does not translate,
download, synthesize, or export to the Desktop. No private source content used.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio.subtitles import Cue, render_subtitles


def create_demo(root):
    root=Path(root);identity='d'*32;folder=root/'results'/identity
    if folder.exists():raise ValueError('The self-authored demo already exists; no files were changed.')
    pairs=[
        ('A good learning routine starts with a question.','好的学习习惯从一个问题开始。'),
        ('The response was bifurcated, with two groups taking different views.','反应出现两极分化，两个群体持不同看法。'),
        ('A natural governor can keep a system from expanding too quickly.','自发约束机制可以防止系统扩张过快。'),
        ('Think of unused potential as a coiled spring.','可以把尚未释放的潜力想象成压紧的弹簧。'),
        ('A small setback does not always mean capitulation in the stock market.','小幅挫折并不总意味着股市出现恐慌性抛售。'),
        ('Listen again, then explain the idea in your own words.','再听一遍，然后用自己的话解释这个观点。'),
    ]
    cues=[Cue(index*5,index*5+4,english) for index,(english,_) in enumerate(pairs)]
    folder.mkdir(parents=True)
    files={extension:'self-authored-demo.'+extension for extension in ('srt','vtt','txt')}
    for extension,name in files.items():(folder/name).write_text(render_subtitles(cues,extension),encoding='utf-8')
    records=[{'start':cue.start,'end':cue.end,'text':cue.text} for cue in cues]
    (folder/'study-cues.json').write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
    blocks=[{'start':cue.start,'end':cue.end,'english':english,'chinese':chinese} for cue,(english,chinese) in zip(cues,pairs)]
    note='自编中英示例；不是第三方视频字幕，也没有视频原音。'
    (folder/'bilingual.json').write_text(json.dumps({'blocks':blocks,'chinese_source':note},ensure_ascii=False),encoding='utf-8')
    metadata={'id':identity,'title':'Self-authored learning demo · 自编学习示例','source':'uploaded_caption','url':None,'language':'en','duration':30,
              'model':None,'created_at':datetime.now(timezone.utc).isoformat(),'count':len(cues),'files':files,'output_dir':str(folder.resolve()),
              'preview':records,'bilingual_count':len(blocks),'bilingual_preview':blocks,'chinese_source':note,'warning':note}
    (folder/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf-8')
    return identity


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: python scripts/create-demo.py <explicit-test-data-directory>')
    print(create_demo(sys.argv[1]))
