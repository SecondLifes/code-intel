# Python Performance — Reference

## Core Concepts

### Profiling Types

- **CPU Profiling**: Identify time-consuming functions
- **Memory Profiling**: Track memory allocation and leaks
- **Line Profiling**: Profile at line-by-line granularity
- **Call Graph**: Visualize function call relationships

### Performance Metrics

- **Execution Time**: How long operations take
- **Memory Usage**: Peak and average memory consumption
- **CPU Utilization**: Processor usage patterns
- **I/O Wait**: Time spent on I/O operations

### Optimization Strategies

- **Algorithmic**: Better algorithms and data structures
- **Implementation**: More efficient code patterns
- **Parallelization**: Multi-threading/processing
- **Caching**: Avoid redundant computation
- **Native Extensions**: C/Rust for critical paths

## Quick Start — Basic Timing

```python
import time

def measure_time():
    """Simple timing measurement."""
    start = time.time()
    result = sum(range(1000000))
    elapsed = time.time() - start
    print(f"Execution time: {elapsed:.4f} seconds")
    return result

# Better: use timeit for accurate measurements
import timeit

execution_time = timeit.timeit(
    "sum(range(1000000))",
    number=100
)
print(f"Average time: {execution_time/100:.6f} seconds")
```

## Profiling Tools

### Pattern 1: cProfile - CPU Profiling

```python
import cProfile
import pstats
from pstats import SortKey

def slow_function():
    total = 0
    for i in range(1000000):
        total += i
    return total

def another_function():
    return [i**2 for i in range(100000)]

def main():
    result1 = slow_function()
    result2 = another_function()
    return result1, result2

if __name__ == "__main__":
    profiler = cProfile.Profile()
    profiler.enable()
    main()
    profiler.disable()

    stats = pstats.Stats(profiler)
    stats.sort_stats(SortKey.CUMULATIVE)
    stats.print_stats(10)  # Top 10 functions
    stats.dump_stats("profile_output.prof")
```

**Command-line profiling:**

```bash
python -m cProfile -o output.prof script.py
python -m pstats output.prof
# In pstats:
# sort cumtime
# stats 10
```

### Pattern 2: line_profiler - Line-by-Line Profiling

```python
# Install: pip install line-profiler

@profile  # line_profiler provides this decorator
def process_data(data):
    result = []
    for item in data:
        processed = item * 2
        result.append(processed)
    return result

# Run with: kernprof -l -v script.py
```

**Manual line profiling:**

```python
from line_profiler import LineProfiler

def process_data(data):
    result = []
    for item in data:
        processed = item * 2
        result.append(processed)
    return result

if __name__ == "__main__":
    lp = LineProfiler()
    lp.add_function(process_data)
    data = list(range(100000))
    lp_wrapper = lp(process_data)
    lp_wrapper(data)
    lp.print_stats()
```

### Pattern 3: memory_profiler - Memory Usage

```python
# Install: pip install memory-profiler
from memory_profiler import profile

@profile
def memory_intensive():
    big_list = [i for i in range(1000000)]
    big_dict = {i: i**2 for i in range(100000)}
    result = sum(big_list)
    return result

if __name__ == "__main__":
    memory_intensive()

# Run with: python -m memory_profiler script.py
```

### Pattern 4: py-spy - Production Profiling

```bash
# Install: pip install py-spy
py-spy top --pid 12345
py-spy record -o profile.svg --pid 12345
py-spy record -o profile.svg -- python script.py
py-spy dump --pid 12345
```

## Optimization Patterns

### Pattern 5: List Comprehensions vs Loops

```python
import timeit

def slow_squares(n):
    result = []
    for i in range(n):
        result.append(i**2)
    return result

def fast_squares(n):
    return [i**2 for i in range(n)]

n = 100000
slow_time = timeit.timeit(lambda: slow_squares(n), number=100)
fast_time = timeit.timeit(lambda: fast_squares(n), number=100)
print(f"Loop: {slow_time:.4f}s")
print(f"Comprehension: {fast_time:.4f}s")
print(f"Speedup: {slow_time/fast_time:.2f}x")

# Even faster for simple operations: map
def faster_squares(n):
    return list(map(lambda x: x**2, range(n)))
```

### Pattern 6: Generator Expressions for Memory

```python
import sys

def list_approach():
    data = [i**2 for i in range(1000000)]
    return sum(data)

def generator_approach():
    data = (i**2 for i in range(1000000))
    return sum(data)

list_data = [i for i in range(1000000)]
gen_data = (i for i in range(1000000))
print(f"List size: {sys.getsizeof(list_data)} bytes")
print(f"Generator size: {sys.getsizeof(gen_data)} bytes")
# Generators use constant memory regardless of size
```

### Pattern 7: String Concatenation

```python
import timeit

def slow_concat(items):
    result = ""
    for item in items:
        result += str(item)
    return result

def fast_concat(items):
    return "".join(str(item) for item in items)

def faster_concat(items):
    parts = [str(item) for item in items]
    return "".join(parts)

items = list(range(10000))
slow = timeit.timeit(lambda: slow_concat(items), number=100)
fast = timeit.timeit(lambda: fast_concat(items), number=100)
faster = timeit.timeit(lambda: faster_concat(items), number=100)
print(f"Concatenation (+): {slow:.4f}s")
print(f"Join (generator): {fast:.4f}s")
print(f"Join (list): {faster:.4f}s")
```

### Pattern 8: Dictionary Lookups vs List Searches

```python
import timeit

size = 10000
items = list(range(size))
lookup_dict = {i: i for i in range(size)}

def list_search(items, target):
    return target in items

def dict_search(lookup_dict, target):
    return target in lookup_dict

target = size - 1  # Worst case for list
list_time = timeit.timeit(lambda: list_search(items, target), number=1000)
dict_time = timeit.timeit(lambda: dict_search(lookup_dict, target), number=1000)
print(f"List search: {list_time:.6f}s")
print(f"Dict search: {dict_time:.6f}s")
print(f"Speedup: {list_time/dict_time:.0f}x")
```

### Pattern 9: Local Variable Access

```python
import timeit

GLOBAL_VALUE = 100

def use_global():
    total = 0
    for i in range(10000):
        total += GLOBAL_VALUE
    return total

def use_local():
    local_value = 100
    total = 0
    for i in range(10000):
        total += local_value
    return total

global_time = timeit.timeit(use_global, number=1000)
local_time = timeit.timeit(use_local, number=1000)
print(f"Global access: {global_time:.4f}s")
print(f"Local access: {local_time:.4f}s")
print(f"Speedup: {global_time/local_time:.2f}x")
```

### Pattern 10: Function Call Overhead

```python
import timeit

def calculate_inline():
    total = 0
    for i in range(10000):
        total += i * 2 + 1
    return total

def helper_function(x):
    return x * 2 + 1

def calculate_with_function():
    total = 0
    for i in range(10000):
        total += helper_function(i)
    return total

inline_time = timeit.timeit(calculate_inline, number=1000)
function_time = timeit.timeit(calculate_with_function, number=1000)
print(f"Inline: {inline_time:.4f}s")
print(f"Function calls: {function_time:.4f}s")
```

## Advanced Optimization

### Pattern 11: NumPy for Numerical Operations

```python
import timeit
import numpy as np

def python_sum(n):
    return sum(range(n))

def numpy_sum(n):
    return np.arange(n).sum()

n = 1000000
python_time = timeit.timeit(lambda: python_sum(n), number=100)
numpy_time = timeit.timeit(lambda: numpy_sum(n), number=100)
print(f"Python: {python_time:.4f}s")
print(f"NumPy: {numpy_time:.4f}s")
print(f"Speedup: {python_time/numpy_time:.2f}x")

def python_multiply():
    a = list(range(100000))
    b = list(range(100000))
    return [x * y for x, y in zip(a, b)]

def numpy_multiply():
    a = np.arange(100000)
    b = np.arange(100000)
    return a * b

py_time = timeit.timeit(python_multiply, number=100)
np_time = timeit.timeit(numpy_multiply, number=100)
print(f"\nPython multiply: {py_time:.4f}s")
print(f"NumPy multiply: {np_time:.4f}s")
print(f"Speedup: {py_time/np_time:.2f}x")
```

### Pattern 12: Caching with functools.lru_cache

```python
from functools import lru_cache
import timeit

def fibonacci_slow(n):
    if n < 2:
        return n
    return fibonacci_slow(n-1) + fibonacci_slow(n-2)

@lru_cache(maxsize=None)
def fibonacci_fast(n):
    if n < 2:
        return n
    return fibonacci_fast(n-1) + fibonacci_fast(n-2)

n = 30
slow_time = timeit.timeit(lambda: fibonacci_slow(n), number=1)
fast_time = timeit.timeit(lambda: fibonacci_fast(n), number=1000)
print(f"Without cache (1 run): {slow_time:.4f}s")
print(f"With cache (1000 runs): {fast_time:.4f}s")
print(f"Cache info: {fibonacci_fast.cache_info()}")
```

### Pattern 13: Using __slots__ for Memory

```python
import sys

class RegularClass:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

class SlottedClass:
    __slots__ = ['x', 'y', 'z']
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

regular = RegularClass(1, 2, 3)
slotted = SlottedClass(1, 2, 3)
print(f"Regular class size: {sys.getsizeof(regular)} bytes")
print(f"Slotted class size: {sys.getsizeof(slotted)} bytes")
# Significant savings with many instances
```

### Pattern 14: Multiprocessing for CPU-Bound Tasks

```python
import multiprocessing as mp
import time

def cpu_intensive_task(n):
    return sum(i**2 for i in range(n))

def sequential_processing():
    start = time.time()
    results = [cpu_intensive_task(1000000) for _ in range(4)]
    return time.time() - start, results

def parallel_processing():
    start = time.time()
    with mp.Pool(processes=4) as pool:
        results = pool.map(cpu_intensive_task, [1000000] * 4)
    return time.time() - start, results

if __name__ == "__main__":
    seq_time, seq_results = sequential_processing()
    par_time, par_results = parallel_processing()
    print(f"Sequential: {seq_time:.2f}s")
    print(f"Parallel: {par_time:.2f}s")
    print(f"Speedup: {seq_time/par_time:.2f}x")
```

### Pattern 15: Async I/O for I/O-Bound Tasks

```python
import asyncio
import aiohttp
import time
import requests

urls = ["https://httpbin.org/delay/1"] * 4

def synchronous_requests():
    start = time.time()
    results = [requests.get(url).status_code for url in urls]
    return time.time() - start, results

async def async_fetch(session, url):
    async with session.get(url) as response:
        return response.status

async def asynchronous_requests():
    start = time.time()
    async with aiohttp.ClientSession() as session:
        tasks = [async_fetch(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
    return time.time() - start, results

sync_time, sync_results = synchronous_requests()
async_time, async_results = asyncio.run(asynchronous_requests())
print(f"Synchronous: {sync_time:.2f}s")
print(f"Asynchronous: {async_time:.2f}s")
print(f"Speedup: {sync_time/async_time:.2f}x")
```

## Database Optimization

### Pattern 16: Batch Database Operations

```python
import sqlite3
import time

def create_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    return conn

def slow_inserts(conn, count):
    start = time.time()
    cursor = conn.cursor()
    for i in range(count):
        cursor.execute("INSERT INTO users (name) VALUES (?)", (f"User {i}",))
        conn.commit()  # Commit each insert
    return time.time() - start

def fast_inserts(conn, count):
    start = time.time()
    cursor = conn.cursor()
    data = [(f"User {i}",) for i in range(count)]
    cursor.executemany("INSERT INTO users (name) VALUES (?)", data)
    conn.commit()  # Single commit
    return time.time() - start

conn1 = create_db()
slow_time = slow_inserts(conn1, 1000)
conn2 = create_db()
fast_time = fast_inserts(conn2, 1000)
print(f"Individual inserts: {slow_time:.4f}s")
print(f"Batch insert: {fast_time:.4f}s")
print(f"Speedup: {slow_time/fast_time:.2f}x")
```

### Pattern 17: Query Optimization

```sql
-- Slow: No index
SELECT * FROM users WHERE email = 'user@example.com';

-- Fast: With index
CREATE INDEX idx_users_email ON users(email);
SELECT * FROM users WHERE email = 'user@example.com';
```

```python
# Analyze query performance
import sqlite3
conn = sqlite3.connect("example.db")
cursor = conn.cursor()
cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM users WHERE email = ?", ("test@example.com",))
print(cursor.fetchall())

# Use SELECT only needed columns instead of SELECT *
```

## Memory Optimization

### Pattern 18: Detecting Memory Leaks

```python
import tracemalloc
import gc

def memory_leak_example():
    leaked_objects = []
    for i in range(100000):
        leaked_objects.append([i] * 100)

def track_memory_usage():
    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()
    memory_leak_example()
    snapshot2 = tracemalloc.take_snapshot()
    top_stats = snapshot2.compare_to(snapshot1, 'lineno')
    print("Top 10 memory allocations:")
    for stat in top_stats[:10]:
        print(stat)
    tracemalloc.stop()

track_memory_usage()
gc.collect()
```

### Pattern 19: Iterators vs Lists

```python
def process_file_list(filename):
    """Loads entire file into memory."""
    with open(filename) as f:
        lines = f.readlines()
        return sum(1 for line in lines if line.strip())

def process_file_iterator(filename):
    """Processes file line by line — constant memory."""
    with open(filename) as f:
        return sum(1 for line in f if line.strip())
```

### Pattern 20: Weakref for Caches

```python
import weakref

class CachedResource:
    def __init__(self, data):
        self.data = data

# Regular cache prevents garbage collection
regular_cache = {}

def get_resource_regular(key):
    if key not in regular_cache:
        regular_cache[key] = CachedResource(f"Data for {key}")
    return regular_cache[key]

# Weak reference cache allows garbage collection
weak_cache = weakref.WeakValueDictionary()

def get_resource_weak(key):
    resource = weak_cache.get(key)
    if resource is None:
        resource = CachedResource(f"Data for {key}")
        weak_cache[key] = resource
    return resource
```

## Benchmarking Tools

### Custom Benchmark Decorator

```python
import time
from functools import wraps

def benchmark(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.6f} seconds")
        return result
    return wrapper

@benchmark
def slow_function():
    time.sleep(0.5)
    return sum(range(1000000))
```

### Performance Testing with pytest-benchmark

```python
# Install: pip install pytest-benchmark

def test_list_comprehension(benchmark):
    result = benchmark(lambda: [i**2 for i in range(10000)])
    assert len(result) == 10000

def test_map_function(benchmark):
    result = benchmark(lambda: list(map(lambda x: x**2, range(10000))))
    assert len(result) == 10000

# Run with: pytest test_performance.py --benchmark-compare
```

## Best Practices

1. **Profile before optimizing** — Measure to find real bottlenecks
2. **Focus on hot paths** — Optimize code that runs most frequently
3. **Use appropriate data structures** — Dict for lookups, set for membership
4. **Avoid premature optimization** — Clarity first, then optimize
5. **Use built-in functions** — They're implemented in C
6. **Cache expensive computations** — Use lru_cache
7. **Batch I/O operations** — Reduce system calls
8. **Use generators** for large datasets
9. **Consider NumPy** for numerical operations
10. **Profile production code** — Use py-spy for live systems

## Common Pitfalls

- Optimizing without profiling
- Using global variables unnecessarily
- Not using appropriate data structures
- Creating unnecessary copies of data
- Not using connection pooling for databases
- Ignoring algorithmic complexity
- Over-optimizing rare code paths
- Not considering memory usage
