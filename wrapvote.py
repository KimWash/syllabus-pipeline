# Ask an LLM provider whether each wrap point "<end of line>|<start of next line>" swallowed a space.
import re, sys, time, concurrent.futures as cf
from llm import LLMError

PROMPT = ("PDF에서 추출한 한국어/영어 문장이 칸 너비 때문에 자동 줄바꿈되었습니다. 줄바꿈 지점은 '|'로 표시했습니다. "
          "줄바꿈 때문에 원래 있던 공백이 사라졌을 수도 있고, 단어 중간에서 잘렸을 수도 있습니다. "
          "각 번호마다 올바른 한국어 띄어쓰기(또는 영어 단어 경계) 기준으로 '|' 자리에 공백이 있어야 하면 S, 붙여야 하면 J로 답하세요. "
          "다른 설명 없이 한 줄에 하나씩 '번호:S' 또는 '번호:J' 형식으로만 답하세요.\n\n")

def ask(provider, keys, attempts=4):
    """One batch -> {key: 'S'|'J'}; empty dict if the provider never gave a complete answer."""
    prompt = PROMPT + "\n".join(f"{i+1}) {k}" for i, k in enumerate(keys))
    for attempt in range(attempts):
        try:
            res = {}
            for m in re.finditer(r'(\d+)\s*[:：]\s*([SJ])', provider.complete(prompt)):
                i = int(m.group(1)) - 1
                if 0 <= i < len(keys):
                    res[keys[i]] = m.group(2)
            if len(res) == len(keys):
                return res
            print(f"  {provider.label}: incomplete answer ({len(res)}/{len(keys)})", file=sys.stderr)
        except LLMError as e:
            print(f"  {provider.label}: {str(e)[:150]}", file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    return {}

def vote(provider, keys, batch=50, rounds=3):
    """Vote on all keys in batches with the provider's concurrency; failed batches are retried next round."""
    out = {}
    batches = [keys[i:i + batch] for i in range(0, len(keys), batch)]
    for rnd in range(rounds):
        todo = [[k for k in b if k not in out] for b in batches]
        todo = [b for b in todo if b]
        if not todo:
            break
        with cf.ThreadPoolExecutor(provider.concurrency) as ex:
            for res in ex.map(lambda b: ask(provider, b), todo):
                out.update(res)
        print(f"  {provider.label}: {len(out)}/{len(keys)} after round {rnd+1}", file=sys.stderr)
    return out
