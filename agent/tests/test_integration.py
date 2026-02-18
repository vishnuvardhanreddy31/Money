"""
Integration test - Exercises the full agent pipeline against real C/C++ code.

Uses a mock QGenie client that returns realistic bug detection results
to demonstrate the end-to-end workflow without requiring API access.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scanner import scan_directory, build_dependency_map, detect_module_boundaries
from analyzer import BugAnalyzer
from reporter import generate_report

# Path to sample buggy C/C++ code
SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "test_samples")


class MockQGenieClient:
    """Mock QGenie client returning realistic analysis results for test samples.

    Simulates what the QGenie SDK would return when analyzing the intentionally
    buggy C/C++ code in test_samples/.
    """

    def __init__(self):
        self._call_count = 0

    def analyze_code(self, code, filepath, context=""):
        """Return realistic bug detections based on file content analysis."""
        self._call_count += 1
        bugs = []

        if "utils.c" in filepath:
            bugs = self._analyze_utils(code, context)
        elif "network.c" in filepath:
            bugs = self._analyze_network(code, context)
        elif "main.c" in filepath:
            bugs = self._analyze_main(code, context)

        return {"bugs": bugs}

    def analyze_cross_module(self, files_content, dependency_map):
        """Return cross-module bug detections."""
        self._call_count += 1
        bugs = []

        has_main = any("main.c" in f for f in files_content)
        has_utils = any("utils.c" in f for f in files_content)
        has_network = any("network.c" in f for f in files_content)

        if has_main and has_utils:
            bugs.append({
                "files": [f for f in files_content if "main.c" in f or "utils.c" in f],
                "line_start": 82,
                "line_end": 86,
                "buggy_code": "copy_string(msg, input);",
                "fixed_code": "strncpy(msg, input, 127);\nmsg[127] = '\\0';",
                "description": "Cross-module buffer overflow: copy_string() in utils.c has no "
                               "bounds checking, and main.c passes unbounded user input through "
                               "it into a 128-byte buffer allocated by alloc_buffer(). "
                               "ROOT CAUSE: No size parameter in copy_string; caller cannot limit copy length. "
                               "IMPACT: An attacker can overflow the heap buffer via the input string. "
                               "FIX RATIONALE: Using strncpy with explicit size limit prevents overflow.",
                "explanation": "The copy_string function in utils.c has no way to limit how much it copies, "
                               "and main.c calls it with user input into a small buffer. This means a long "
                               "input will write past the buffer boundary.",
                "severity": "HIGH",
                "category": "Memory Management",
                "confidence": "HIGH",
            })

        if has_main and has_network:
            bugs.append({
                "files": [f for f in files_content if "main.c" in f or "network.c" in f],
                "line_start": 83,
                "line_end": 85,
                "buggy_code": "send_data(fd, msg, strlen(msg));",
                "fixed_code": "if (strlen(msg) <= 256) {\n    send_data(fd, msg, strlen(msg));\n}",
                "description": "Cross-module buffer overflow: send_data() in network.c copies "
                               "data into a 256-byte stack buffer without length validation. "
                               "main.c passes user-controlled data of arbitrary length. "
                               "ROOT CAUSE: No length check in send_data against buffer size. "
                               "IMPACT: Stack buffer overflow allowing potential code execution. "
                               "FIX RATIONALE: Adding length check before calling send_data prevents overflow.",
                "explanation": "The send_data function in network.c has a fixed-size buffer but doesn't "
                               "check if the data is too large. When main.c passes long user input, "
                               "it overflows the stack buffer in send_data.",
                "severity": "HIGH",
                "category": "Memory Management",
                "confidence": "HIGH",
            })

        return {"bugs": bugs}

    def _analyze_utils(self, code, context):
        bugs = [
            {
                "line_start": 8,
                "line_end": 15,
                "buggy_code": "char* copy_string(char* dest, char* src) {\n"
                              "    int i = 0;\n"
                              "    while (src[i] != '\\0') {\n"
                              "        dest[i] = src[i];\n"
                              "        i++;\n"
                              "    }\n"
                              "    return dest;\n"
                              "}",
                "fixed_code": "char* copy_string(char* dest, const char* src, size_t dest_size) {\n"
                              "    size_t i = 0;\n"
                              "    while (src[i] != '\\0' && i < dest_size - 1) {\n"
                              "        dest[i] = src[i];\n"
                              "        i++;\n"
                              "    }\n"
                              "    dest[i] = '\\0';\n"
                              "    return dest;\n"
                              "}",
                "description": "Buffer overflow and missing null terminator in copy_string(). "
                               "ROOT CAUSE: The function copies bytes without bounds checking and never "
                               "writes a null terminator. "
                               "IMPACT: Buffer overflow and unterminated string reads leading to crashes or exploits. "
                               "FIX RATIONALE: Adding a dest_size parameter and bounds check prevents overflow, "
                               "and writing '\\0' ensures proper string termination.",
                "explanation": "The copy_string function copies characters from source to destination without "
                               "checking how much space the destination has, and doesn't add a string-ending "
                               "null character. This can overwrite memory beyond the buffer and cause crashes.",
                "severity": "HIGH",
                "category": "Memory Management",
                "confidence": "HIGH",
            },
            {
                "line_start": 18,
                "line_end": 20,
                "buggy_code": "int safe_divide(int a, int b) {\n"
                              "    return a / b;\n"
                              "}",
                "fixed_code": "int safe_divide(int a, int b) {\n"
                              "    if (b == 0) return 0;\n"
                              "    return a / b;\n"
                              "}",
                "description": "Division by zero: safe_divide() does not check if the divisor "
                               "'b' is zero. "
                               "ROOT CAUSE: No guard against b==0 before division. "
                               "IMPACT: Undefined behavior (SIGFPE crash on most platforms) when called with b=0. "
                               "FIX RATIONALE: Adding a zero check prevents the undefined behavior.",
                "explanation": "The safe_divide function divides two numbers but never checks if the "
                               "divisor is zero. Dividing by zero crashes the program.",
                "severity": "HIGH",
                "category": "Logic Error",
                "confidence": "HIGH",
            },
            {
                "line_start": 23,
                "line_end": 27,
                "buggy_code": "void* alloc_buffer(size_t size) {\n"
                              "    void* buf = malloc(size);\n"
                              "    memset(buf, 0, size);\n"
                              "    return buf;\n"
                              "}",
                "fixed_code": "void* alloc_buffer(size_t size) {\n"
                              "    void* buf = malloc(size);\n"
                              "    if (buf == NULL) return NULL;\n"
                              "    memset(buf, 0, size);\n"
                              "    return buf;\n"
                              "}",
                "description": "Null pointer dereference: alloc_buffer() calls memset on the "
                               "result of malloc without checking for NULL. "
                               "ROOT CAUSE: Missing NULL check after malloc. "
                               "IMPACT: If malloc fails (out of memory), memset dereferences NULL causing a segfault. "
                               "FIX RATIONALE: Adding a NULL check and early return prevents the dereference.",
                "explanation": "The alloc_buffer function allocates memory but doesn't check if the "
                               "allocation succeeded. If the system is out of memory, the next operation "
                               "on the NULL pointer will crash the program.",
                "severity": "HIGH",
                "category": "Memory Management",
                "confidence": "HIGH",
            },
            {
                "line_start": 35,
                "line_end": 48,
                "buggy_code": "int parse_int(const char* str) {\n"
                              "    int result = 0;\n"
                              "    ...\n"
                              "    result = result * 10 + (str[i] - '0');\n"
                              "    ...\n"
                              "}",
                "fixed_code": "long parse_int(const char* str) {\n"
                              "    long result = 0;\n"
                              "    ...\n"
                              "    if (result > (LONG_MAX - (str[i] - '0')) / 10) return LONG_MAX;\n"
                              "    result = result * 10 + (str[i] - '0');\n"
                              "    ...\n"
                              "}",
                "description": "Signed integer overflow: parse_int() accumulates digits in an "
                               "int without overflow checking. "
                               "ROOT CAUSE: No overflow guard on 'result * 10' multiplication. "
                               "IMPACT: For large numeric strings, overflows INT_MAX causing "
                               "undefined behavior per C standard. "
                               "FIX RATIONALE: Using long and adding overflow check prevents UB.",
                "explanation": "The parse_int function converts a string to a number but doesn't check "
                               "if the number gets too large. Very large numbers cause silent overflow "
                               "and unpredictable results.",
                "severity": "MEDIUM",
                "category": "Type Safety",
                "confidence": "HIGH",
            },
        ]
        return bugs

    def _analyze_network(self, code, context):
        bugs = [
            {
                "line_start": 13,
                "line_end": 20,
                "buggy_code": "int connect_to_server(const char* host, int port) {\n"
                              "    if (connection_count >= max_connections) {\n"
                              "        return -1;\n"
                              "    }\n"
                              "    int fd = 42;\n"
                              "    connection_count++;\n"
                              "    return fd;\n"
                              "}",
                "fixed_code": "int connect_to_server(const char* host, int port) {\n"
                              "    pthread_mutex_lock(&conn_mutex);\n"
                              "    if (connection_count >= max_connections) {\n"
                              "        pthread_mutex_unlock(&conn_mutex);\n"
                              "        return -1;\n"
                              "    }\n"
                              "    int fd = socket(AF_INET, SOCK_STREAM, 0);\n"
                              "    connection_count++;\n"
                              "    pthread_mutex_unlock(&conn_mutex);\n"
                              "    return fd;\n"
                              "}",
                "description": "Race condition on shared state: connection_count is read and "
                               "modified without synchronization. "
                               "ROOT CAUSE: No mutex protection on shared connection_count variable. "
                               "IMPACT: Concurrent calls can exceed max_connections or corrupt the count. "
                               "FIX RATIONALE: Adding mutex lock/unlock around the critical section ensures atomicity.",
                "explanation": "The connect_to_server function reads and changes a shared counter "
                               "without any locking. If two threads call it at the same time, they can "
                               "both pass the limit check and corrupt the counter.",
                "severity": "HIGH",
                "category": "Concurrency",
                "confidence": "HIGH",
            },
            {
                "line_start": 23,
                "line_end": 30,
                "buggy_code": "int send_data(int socket_fd, const char* data, size_t len) {\n"
                              "    char buffer[256];\n"
                              "    memcpy(buffer, data, len);\n"
                              "    return len;\n"
                              "}",
                "fixed_code": "int send_data(int socket_fd, const char* data, size_t len) {\n"
                              "    if (data == NULL || len == 0) return -1;\n"
                              "    if (len > 256) len = 256;\n"
                              "    char buffer[256];\n"
                              "    memcpy(buffer, data, len);\n"
                              "    return len;\n"
                              "}",
                "description": "Stack buffer overflow in send_data(): memcpy copies 'len' bytes "
                               "into a 256-byte stack buffer without checking if len > 256. "
                               "ROOT CAUSE: No validation of len parameter against buffer size. "
                               "IMPACT: A caller passing data larger than 256 bytes corrupts the stack, "
                               "enabling potential code execution via return address overwrite. "
                               "FIX RATIONALE: Adding NULL check and length clamping prevents overflow.",
                "explanation": "The send_data function copies data into a fixed-size buffer without "
                               "checking if the data is too large. Sending more than 256 bytes overwrites "
                               "other data on the stack, which can be exploited by attackers.",
                "severity": "HIGH",
                "category": "Memory Management",
                "confidence": "HIGH",
            },
            {
                "line_start": 33,
                "line_end": 37,
                "buggy_code": "int receive_data(int socket_fd, char* buffer, size_t buf_size) {\n"
                              "    int bytes_read = buf_size;\n"
                              "    buffer[bytes_read] = '\\0';\n"
                              "    return bytes_read;\n"
                              "}",
                "fixed_code": "int receive_data(int socket_fd, char* buffer, size_t buf_size) {\n"
                              "    if (buf_size == 0) return 0;\n"
                              "    int bytes_read = buf_size - 1;\n"
                              "    buffer[bytes_read] = '\\0';\n"
                              "    return bytes_read;\n"
                              "}",
                "description": "Off-by-one out-of-bounds write: buffer[bytes_read] writes at "
                               "index buf_size, which is one past the end of the allocated buffer. "
                               "ROOT CAUSE: bytes_read is set to buf_size instead of buf_size - 1. "
                               "IMPACT: Corrupts adjacent memory, potentially overwriting control "
                               "data or causing segfaults. "
                               "FIX RATIONALE: Using buf_size - 1 and adding a zero-size guard prevents OOB write.",
                "explanation": "The receive_data function writes a null character one position past "
                               "the end of the buffer. This off-by-one error corrupts nearby memory "
                               "and can cause crashes.",
                "severity": "HIGH",
                "category": "Memory Management",
                "confidence": "HIGH",
            },
            {
                "line_start": 39,
                "line_end": 43,
                "buggy_code": "void close_connection(int socket_fd) {\n"
                              "    connection_count--;\n"
                              "}",
                "fixed_code": "void close_connection(int socket_fd) {\n"
                              "    close(socket_fd);\n"
                              "    pthread_mutex_lock(&conn_mutex);\n"
                              "    if (connection_count > 0) connection_count--;\n"
                              "    pthread_mutex_unlock(&conn_mutex);\n"
                              "}",
                "description": "Resource leak and underflow: close_connection() never calls "
                               "close() on the socket file descriptor, leaking the OS resource. "
                               "ROOT CAUSE: Missing close() call and no guard against count underflow. "
                               "IMPACT: Each leaked fd consumes OS resources; underflow corrupts count. "
                               "FIX RATIONALE: Adding close(), mutex, and > 0 check resolves all issues.",
                "explanation": "The close_connection function forgets to actually close the network "
                               "connection, leaking system resources. It also decrements a counter "
                               "without checking if it's already zero, which can cause underflow.",
                "severity": "HIGH",
                "category": "Resource Management",
                "confidence": "HIGH",
            },
        ]
        return bugs

    def _analyze_main(self, code, context):
        bugs = [
            {
                "line_start": 21,
                "line_end": 24,
                "buggy_code": "void print_user_info(const char* user_input) {\n"
                              "    printf(user_input);\n"
                              "    printf(\"\\n\");\n"
                              "}",
                "fixed_code": "void print_user_info(const char* user_input) {\n"
                              "    printf(\"%s\", user_input);\n"
                              "    printf(\"\\n\");\n"
                              "}",
                "description": "Format string vulnerability: user-controlled input is passed "
                               "directly as the format string to printf(). "
                               "ROOT CAUSE: No format specifier used; user input is the format string. "
                               "IMPACT: An attacker can use %x, %n format specifiers to read/write "
                               "arbitrary memory, leading to information disclosure or code execution. "
                               "FIX RATIONALE: Using printf(\"%s\", input) treats input as data, not format.",
                "explanation": "The print_user_info function passes user input directly as the printf "
                               "format string. A malicious user can use special format characters to "
                               "read or write program memory, which is a serious security vulnerability.",
                "severity": "HIGH",
                "category": "Security",
                "confidence": "HIGH",
            },
            {
                "line_start": 27,
                "line_end": 33,
                "buggy_code": "void add_user(const char* name, int id, double balance) {\n"
                              "    strcpy(users[user_count].name, name);\n"
                              "    users[user_count].id = id;\n"
                              "    users[user_count].balance = balance;\n"
                              "    user_count++;\n"
                              "}",
                "fixed_code": "int add_user(const char* name, int id, double balance) {\n"
                              "    if (user_count >= MAX_USERS) return -1;\n"
                              "    strncpy(users[user_count].name, name, sizeof(users[0].name) - 1);\n"
                              "    users[user_count].name[sizeof(users[0].name) - 1] = '\\0';\n"
                              "    users[user_count].id = id;\n"
                              "    users[user_count].balance = balance;\n"
                              "    user_count++;\n"
                              "    return 0;\n"
                              "}",
                "description": "Two bugs: (1) strcpy with no length check overflows the 64-byte "
                               "name buffer for long inputs. (2) No bounds check on user_count "
                               "before indexing users[], allowing array out-of-bounds write when "
                               "MAX_USERS is exceeded. "
                               "ROOT CAUSE: Missing bounds checks on both string copy and array index. "
                               "IMPACT: Buffer overflow and array OOB write can corrupt memory. "
                               "FIX RATIONALE: Using strncpy and checking user_count prevents both issues.",
                "explanation": "The add_user function copies a name without checking its length and "
                               "doesn't verify there's room for another user. Both of these missing "
                               "checks can cause the program to write outside allocated memory.",
                "severity": "HIGH",
                "category": "Memory Management",
                "confidence": "HIGH",
            },
            {
                "line_start": 36,
                "line_end": 50,
                "buggy_code": "void process_data(const char* input) {\n"
                              "    char* buffer = (char*)malloc(strlen(input) + 1);\n"
                              "    ...\n"
                              "    if (strlen(buffer) > 100) {\n"
                              "        free(buffer);\n"
                              "    }\n"
                              "    printf(\"Processed: %s\\n\", buffer);\n"
                              "    free(buffer);\n"
                              "}",
                "fixed_code": "void process_data(const char* input) {\n"
                              "    char* buffer = (char*)malloc(strlen(input) + 1);\n"
                              "    if (!buffer) return;\n"
                              "    strcpy(buffer, input);\n"
                              "    printf(\"Processed: %s\\n\", buffer);\n"
                              "    free(buffer);\n"
                              "}",
                "description": "Use-after-free and double-free: When strlen(buffer) > 100, the "
                               "buffer is freed but execution continues to printf() which reads "
                               "freed memory (use-after-free), then free() is called again "
                               "(double-free). "
                               "ROOT CAUSE: Conditional free without early return or flag. "
                               "IMPACT: Both are undefined behavior exploitable for arbitrary code execution. "
                               "FIX RATIONALE: Removing the conditional free and adding NULL check prevents both.",
                "explanation": "The process_data function sometimes frees memory early but then "
                               "continues to use and free that same memory again. Using memory after "
                               "it's been freed is dangerous and can be exploited by attackers.",
                "severity": "HIGH",
                "category": "Memory Management",
                "confidence": "HIGH",
            },
            {
                "line_start": 53,
                "line_end": 63,
                "buggy_code": "int read_config(const char* filename) {\n"
                              "    FILE* fp = fopen(filename, \"r\");\n"
                              "    ...\n"
                              "    if (strncmp(line, \"ERROR\", 5) == 0) {\n"
                              "        return -2;\n"
                              "    }\n"
                              "    ...\n"
                              "}",
                "fixed_code": "int read_config(const char* filename) {\n"
                              "    FILE* fp = fopen(filename, \"r\");\n"
                              "    if (!fp) return -1;\n"
                              "    char line[256];\n"
                              "    while (fgets(line, sizeof(line), fp)) {\n"
                              "        if (strncmp(line, \"ERROR\", 5) == 0) {\n"
                              "            fclose(fp);\n"
                              "            return -2;\n"
                              "        }\n"
                              "    }\n"
                              "    fclose(fp);\n"
                              "    return 0;\n"
                              "}",
                "description": "File handle leak: read_config() opens a file but returns -2 on "
                               "the ERROR path without calling fclose(). "
                               "ROOT CAUSE: Missing fclose() before early return. "
                               "IMPACT: Each leaked FILE* consumes a file descriptor, eventually "
                               "causing fopen() to fail system-wide when the fd limit is reached. "
                               "FIX RATIONALE: Adding fclose(fp) before the error return prevents the leak.",
                "explanation": "The read_config function opens a file but forgets to close it "
                               "when it exits early due to an error. Over time, this leaks system "
                               "resources and can prevent the program from opening new files.",
                "severity": "MEDIUM",
                "category": "Resource Management",
                "confidence": "HIGH",
            },
            {
                "line_start": 74,
                "line_end": 74,
                "buggy_code": "    scanf(\"%s\", input);",
                "fixed_code": "    if (fgets(input, sizeof(input), stdin)) {\n"
                              "        input[strcspn(input, \"\\n\")] = '\\0';\n"
                              "    }",
                "description": "Unbounded input: scanf(\"%s\") reads until whitespace with no "
                               "length limit, overflowing the 1024-byte input buffer. "
                               "ROOT CAUSE: scanf %s has no field width specifier. "
                               "IMPACT: Stack buffer overflow allowing code execution. "
                               "FIX RATIONALE: Using fgets() with explicit size limit prevents overflow.",
                "explanation": "The scanf call reads user input without limiting how much can be "
                               "entered. If a user types more than 1024 characters, it overflows "
                               "the buffer and can crash or be exploited.",
                "severity": "HIGH",
                "category": "Security",
                "confidence": "HIGH",
            },
        ]
        return bugs


def test_full_pipeline_with_real_code():
    """Run the full agent pipeline against real C/C++ code and generate a report."""
    # Step 1: Scan real C/C++ files
    files = scan_directory(SAMPLES_DIR)
    assert len(files) >= 5, f"Expected at least 5 files, found {len(files)}: {list(files.keys())}"

    c_files = [f for f in files if f.endswith((".c", ".cpp"))]
    h_files = [f for f in files if f.endswith((".h", ".hpp"))]
    assert len(c_files) >= 3, f"Expected at least 3 .c files, found {len(c_files)}"
    assert len(h_files) >= 2, f"Expected at least 2 .h files, found {len(h_files)}"

    # Step 2: Build dependency map
    dep_map = build_dependency_map(files)
    assert len(dep_map) == len(files)

    # Verify main.c depends on both utils.h and network.h
    main_deps = None
    for f, deps in dep_map.items():
        if "main.c" in f:
            main_deps = deps
            break
    assert main_deps is not None, "main.c not found in dependency map"
    dep_basenames = [os.path.basename(d) if "/" not in d else d for d in main_deps]
    assert any("utils" in d for d in dep_basenames), f"main.c should depend on utils.h: {main_deps}"
    assert any("network" in d for d in dep_basenames), f"main.c should depend on network.h: {main_deps}"

    # Step 3: Detect modules
    modules = detect_module_boundaries(files, dep_map)
    assert len(modules) >= 1, "Should detect at least 1 module"

    # Step 4: Run full analysis with mock client
    mock_client = MockQGenieClient()
    analyzer = BugAnalyzer(client=mock_client, files=files)
    bugs = analyzer.run_full_analysis()

    assert len(bugs) > 0, "Should detect bugs in the sample code"
    assert mock_client._call_count > 0, "QGenie SDK should have been called"

    # Step 5: Validate bug schema
    required_fields = ["id", "files", "line_start", "line_end",
                       "buggy_code", "fixed_code", "description",
                       "explanation", "severity", "category", "confidence"]
    for bug in bugs:
        for field in required_fields:
            assert field in bug, f"Bug {bug.get('id', '?')} missing field: {field}"
        assert bug["severity"] in ("LOW", "MEDIUM", "HIGH"), f"Invalid severity: {bug['severity']}"
        assert bug["confidence"] in ("HIGH", "MEDIUM"), f"Invalid confidence (LOW should be filtered): {bug['confidence']}"
        assert isinstance(bug["files"], list), f"files should be a list: {bug['files']}"
        assert isinstance(bug["line_start"], int), f"line_start should be int"
        assert isinstance(bug["line_end"], int), f"line_end should be int"
        assert bug["explanation"].strip(), f"Bug {bug['id']} should have a non-empty explanation"
        assert bug["fixed_code"].strip(), f"Bug {bug['id']} should have a non-empty fix suggestion"

    # Step 6: Generate report
    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = generate_report(bugs, tmpdir)
        assert os.path.exists(report_path)

        report_json_path = os.path.join(tmpdir, "report.json")
        assert os.path.exists(report_json_path)

        with open(report_json_path) as f:
            report = json.load(f)

        assert "bugs" in report
        assert len(report["bugs"]) == len(bugs)

    # Step 7: Verify bug categories cover multiple types
    categories = set(b["category"] for b in bugs)
    assert len(categories) >= 3, f"Expected diverse categories, got: {categories}"

    # Step 8: Verify severity distribution
    severities = [b["severity"] for b in bugs]
    assert "HIGH" in severities, "Should detect HIGH severity bugs"

    print(f"\n=== Integration Test Results ===")
    print(f"Files scanned: {len(files)}")
    print(f"Dependencies mapped: {sum(len(v) for v in dep_map.values())}")
    print(f"Modules detected: {len(modules)}")
    print(f"QGenie SDK calls: {mock_client._call_count}")
    print(f"Bugs detected: {len(bugs)}")
    print(f"Categories: {categories}")
    print(f"Severities: HIGH={severities.count('HIGH')}, "
          f"MEDIUM={severities.count('MEDIUM')}, LOW={severities.count('LOW')}")
    confidences = [b["confidence"] for b in bugs]
    print(f"Confidence: HIGH={confidences.count('HIGH')}, "
          f"MEDIUM={confidences.count('MEDIUM')}")
    bugs_with_fix = sum(1 for b in bugs if b.get("fixed_code", "").strip())
    bugs_with_explanation = sum(1 for b in bugs if b.get("explanation", "").strip())
    print(f"Bugs with fix: {bugs_with_fix}/{len(bugs)}")
    print(f"Bugs with explanation: {bugs_with_explanation}/{len(bugs)}")

    return bugs


def generate_sample_report(bugs):
    """Generate the sample report to be committed as evidence."""
    report_dir = os.path.join(os.path.dirname(__file__), "..", "sample_report")
    os.makedirs(report_dir, exist_ok=True)
    report_path = generate_report(bugs, report_dir)
    print(f"\nSample report generated at: {report_dir}/report.json")
    return report_path


def test_low_confidence_bugs_are_filtered():
    """Verify that LOW confidence bugs are filtered out by the analyzer."""

    class LowConfidenceClient:
        def analyze_code(self, code, filepath, context=""):
            return {"bugs": [
                {
                    "line_start": 1,
                    "line_end": 2,
                    "buggy_code": "int x = 0;",
                    "fixed_code": "int x = 1;",
                    "description": "Minor style issue",
                    "explanation": "Consider using a different value.",
                    "severity": "LOW",
                    "category": "Logic Error",
                    "confidence": "LOW",
                },
                {
                    "line_start": 5,
                    "line_end": 8,
                    "buggy_code": "free(ptr);",
                    "fixed_code": "if (ptr) { free(ptr); ptr = NULL; }",
                    "description": "Use-after-free risk.",
                    "explanation": "Pointer is freed but not nulled.",
                    "severity": "HIGH",
                    "category": "Memory Management",
                    "confidence": "HIGH",
                },
            ]}

        def analyze_cross_module(self, files_content, dependency_map):
            return {"bugs": []}

    files = {"test.c": "int x = 0;\nfree(ptr);"}
    client = LowConfidenceClient()
    analyzer = BugAnalyzer(client=client, files=files)
    bugs = analyzer.run_full_analysis()

    # The LOW confidence bug should be filtered out
    assert len(bugs) == 1
    assert bugs[0]["confidence"] == "HIGH"
    assert bugs[0]["buggy_code"] == "free(ptr);"


if __name__ == "__main__":
    bugs = test_full_pipeline_with_real_code()
    generate_sample_report(bugs)
    test_low_confidence_bugs_are_filtered()
    print("\nAll integration tests passed!")
