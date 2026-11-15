# compress.py behavior test: installed and not-installed paths.
import os, sys
os.environ['PYTHONIOENCODING'] = 'utf-8'

from kernel.compress import available, compress_code, compress_snippets, maybe_log, _tok

BIG = ("\n".join(
    f"def filler_function_{i}(param_one, param_two) -> int:"
    f"\n    '''Utility routine {i} that does some arithmetic.'''"
    f"\n    accumulator = param_one + param_two"
    f"\n    for step in range(20):"
    f"\n        accumulator += step * {i}"
    f"\n    if accumulator > 100:"
    f"\n        accumulator = accumulator - 50"
    f"\n    return accumulator"
    for i in range(30)
)) + "\n"

print('available():', available())
out, meta = compress_code(BIG)
print('meta:', meta)
maybe_log(meta, label='big excerpt')
if 'orig_tokens' in meta:
    assert meta['ratio'] < 1.0
    print('compressed ratio OK:', meta['ratio'])

# guardrail: short text unchanged
out2, meta2 = compress_code("x = 1\n")
print('short skip:', meta2)

# preserve list
out3, meta3 = compress_code(BIG, preserve=[BIG])
print('preserve skip:', meta3)

# batch
outs, ameta = compress_snippets([BIG, BIG])
maybe_log(ameta, label='snippets')
print('batch len preserved:', len(outs))

# without llmlingua simulated: verify skipped dict shape
from kernel import compress as C
saved = C.available
C.__dict__['_model_failed'] = True
out4, meta4 = compress_code(BIG)
print('simulated-missing:', meta4)
assert out4 == BIG and 'skipped' in meta4
print('ALL OK')
