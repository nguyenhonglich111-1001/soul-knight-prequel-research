"""Run one function per bundle across worker processes, with a per-bundle result cache.

Every extractor here has the same shape: open each bundle on its own, pull something out,
then merge. The per-bundle part is independent, so it runs in a process pool; the merge
stays in the parent and walks the results **in the original bundle order**, so "first
bundle wins" rules give byte-identical output to the old sequential loops.

One bundle per UnityPy environment is still the rule -- each worker call loads exactly
one bundle (see `extract_soulknight.export_sprites` for why co-loading corrupts sprites).

Cache: a bundle's filename already carries its content hash, so `<name>` + file size
identifies its content. Results are pickled under `.cache/<tag>-<code hash>/`, where the
code hash covers the worker function's source file and the UnityPy version, so editing
the extractor invalidates its cache by itself. A new APK only re-reads the bundles whose
hash changed. `--no-cache` on the extractors (or deleting `.cache/`) forces a full read.
"""

import hashlib
import inspect
import os
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_ROOT = os.path.join(ROOT, '.cache')


CACHE_ENABLED = True
WORKERS = None  # None -> default_workers()


def add_arguments(ap):
    """`--workers` and `--no-cache`, shared by every extractor."""
    ap.add_argument('--workers', type=int, help='worker processes (default: CPUs - 1)')
    ap.add_argument('--no-cache', action='store_true', help='ignore and do not write .cache/')


def configure(args):
    global CACHE_ENABLED, WORKERS
    CACHE_ENABLED = not args.no_cache
    WORKERS = args.workers


def code_tag(tag, fn):
    """`tag` plus a hash of the code that produced the cached values."""
    import UnityPy

    target = getattr(fn, 'func', fn)  # unwrap functools.partial
    with open(inspect.getsourcefile(target), 'rb') as fh:
        source = fh.read()
    return cache_tag(tag, hashlib.sha1(source).hexdigest(), UnityPy.__version__)


def default_workers():
    return max(1, (os.cpu_count() or 2) - 1)


def _cache_file(cache, path):
    return os.path.join(cache, f'{os.path.basename(path)}.{os.path.getsize(path)}.pkl')


def _load(file):
    try:
        with open(file, 'rb') as fh:
            return True, pickle.load(fh)
    except (OSError, EOFError, pickle.UnpicklingError):
        return False, None


def _store(file, value):
    tmp = file + '.tmp'
    with open(tmp, 'wb') as fh:
        pickle.dump(value, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, file)


def map_bundles(fn, paths, *, workers=None, tag=None, progress=None, cacheable=None, consume=None):
    """`[fn(p) for p in paths]`, computed in parallel and cached per bundle.

    `fn` must be picklable (a top-level function or a `functools.partial` of one).
    `tag` names the cache folder (`None` disables caching); `cacheable(value)` can veto
    storing a result, so a bundle that failed to load is retried next run instead of
    being remembered as failed. `progress(done, total)` is called in the parent as
    results arrive. `workers=1` runs inline, which is what a debugger or a test wants.

    `consume(value)`, if given, is called in the parent **in bundle order** as soon as a
    result and every one before it are in; its return value is what gets kept in the
    returned list. That lets a caller write a bundle's bulky output (PNG bytes) and keep
    only a summary, instead of holding every bundle's result in memory at once."""
    paths = list(paths)
    results = [None] * len(paths)
    ready, next_i = {}, 0

    def emit(i, value):
        nonlocal next_i
        if consume is None:
            results[i] = value
            return
        ready[i] = value
        while next_i in ready:
            results[next_i] = consume(ready.pop(next_i))
            next_i += 1

    cache = os.path.join(CACHE_ROOT, code_tag(tag, fn)) if tag and CACHE_ENABLED else None
    if cache:
        os.makedirs(cache, exist_ok=True)

    todo = []
    for i, p in enumerate(paths):
        hit, value = _load(_cache_file(cache, p)) if cache else (False, None)
        if hit:
            emit(i, value)
        else:
            todo.append(i)

    done = len(paths) - len(todo)
    if progress and done:
        progress(done, len(paths))

    def finish(i, value):
        nonlocal done
        if cache and (cacheable is None or cacheable(value)):
            _store(_cache_file(cache, paths[i]), value)
        emit(i, value)
        done += 1
        if progress:
            progress(done, len(paths))

    workers = workers or WORKERS or default_workers()
    if workers == 1 or len(todo) <= 1:
        for i in todo:
            finish(i, fn(paths[i]))
    else:
        with ProcessPoolExecutor(max_workers=min(workers, len(todo))) as pool:
            futures = {pool.submit(fn, paths[i]): i for i in todo}
            for f in as_completed(futures):
                finish(futures[f], f.result())
    return results


def cache_tag(name, *inputs):
    """`name-<8 hex>`: a cache folder that changes whenever any of `inputs` does."""
    digest = hashlib.sha1('\n'.join(map(str, inputs)).encode()).hexdigest()[:8]
    return f'{name}-{digest}'


def every(step):
    """A `progress` callback that prints every `step` bundles and at the end."""

    def tick(done, total):
        if done % step == 0 or done == total:
            print(f'    {done}/{total} bundles', flush=True, file=sys.stdout)

    return tick
