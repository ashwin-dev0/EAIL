import re
PATTERNS=[
 r'ignore\s+(?:all\s+)?(?:previous|prior|system)\s+instructions',
 r'(?:reveal|print|show)\s+(?:the\s+)?system\s+prompt',
 r'(?:override|bypass)\s+(?:security|access|guardrails|permissions)',
 r'<\|(?:system|assistant|im_start)\|>',
 r'you\s+are\s+now\s+(?:an?\s+)?(?:unrestricted|different)',
]
def injection(text): return any(re.search(p,text,re.I) for p in PATTERNS)
def validate_question(question):
    if not isinstance(question,str) or not 3<=len(question.strip())<=2000: raise ValueError('Question must be 3..2000 characters')
    if any(ord(c)<32 and c not in '\n\t' for c in question): raise ValueError('Control characters rejected')
    if injection(question): raise ValueError('Instruction override detected')
    return question.strip()
def exact_fast_path(answer, evidence):
    # Copy-only extractive path: exact complete sentence, never overlap-based acceptance.
    if len(answer.split())>35 or injection(answer): return False
    return any(answer.strip()==sentence.strip() for text in evidence for sentence in re.split(r'(?<=[.!?])\s+|\n',text) if sentence.strip())
def numeric_support(answer,evidence):
    from decimal import Decimal, InvalidOperation
    # Compare complete numeric tokens. 900 must not pass because 9000 appears.
    pattern=r'(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?%?(?![\w.])'
    def tokens(text):
        result=set()
        for value in re.findall(pattern,text):
            try:
                percent=value.endswith('%')
                number=Decimal(value.rstrip('%').replace(',','')).normalize()
                result.add((number,percent))
            except InvalidOperation: pass
        return result
    return tokens(answer)<=tokens(' '.join(evidence))
