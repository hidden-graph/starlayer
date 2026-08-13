
# W3C Turtle Test Suite Download Script (manifest.ttl version)
# Downloads all .ttl and .nt files referenced in manifest.ttl from the official W3C RDF 1.2 Turtle test suite.
# Can be run from anywhere - writes into tests/w3c/data/ next to this script.
#
# Pulls both manifests W3C publishes for RDF 1.2 Turtle: eval/ (TestTurtleEval,
# parser output must match expected .nt) and syntax/ (TestTurtlePositiveSyntax/
# TestTurtleNegativeSyntax, parse success/failure only, no expected .nt). Both
# land in the same flat data/ directory and one combined manifest.csv - their
# filenames and test names don't collide (verified when this was added).

import os
import requests
import re

SOURCES = [
    "https://w3c.github.io/rdf-tests/rdf/rdf12/rdf-turtle/eval/",
    "https://w3c.github.io/rdf-tests/rdf/rdf12/rdf-turtle/syntax/",
]
DEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MANIFEST_FILE = os.path.join(DEST_DIR, "manifest.csv")

def download_file(url, dest):
    if os.path.exists(dest):
        return
    r = requests.get(url)
    if r.status_code == 200:
        with open(dest, "wb") as f:
            f.write(r.content)
        print(f"Downloaded {url}")
    else:
        print(f"Failed to download {url}")

def fetch_manifest_tests(base_url):
    """Fetch and parse one source's manifest.ttl into a list of
    (name, type, ttl, nt) tuples (nt is None for syntax-only tests)."""
    manifest_url = base_url + "manifest.ttl"
    print(f"Fetching manifest from {manifest_url} ...")
    r = requests.get(manifest_url)
    manifest = r.text
    # Parse manifest line by line (state machine)
    tests = []
    current = {}
    for line in manifest.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Start of a test entry (trs:... rdf:type ...)
        m = re.match(r'trs:([\w\-]+)\s+rdf:type\s+([^ ;]+)\s*;', line)
        if m:
            if current:
                tests.append((current.get('name'), current.get('type'), current.get('ttl'), current.get('nt')))
            current = {'name': m.group(1), 'type': m.group(2), 'ttl': None, 'nt': None}
            continue
        # mf:action (ttl file). No trailing-punctuation requirement: the
        # terminating ';' or '.' isn't always on this same line (e.g.
        # turtle12-surrogate-pair-bad-01/02 in the syntax manifest put the
        # '.' on its own following line, since mf:action is their entry's
        # last predicate) - only the IRI itself needs capturing here.
        m = re.match(r'mf:action\s+<([^>]+\.ttl)>', line)
        if m and current:
            current['ttl'] = m.group(1)
            continue
        # mf:result (nt file) - same tolerance
        m = re.match(r'mf:result\s+<([^>]+\.nt)>', line)
        if m and current:
            current['nt'] = m.group(1)
            continue
    # Add last test
    if current:
        tests.append((current.get('name'), current.get('type'), current.get('ttl'), current.get('nt')))
    tests = [t for t in tests if t[2] or t[3]]  # Only keep tests with files
    print(f"Discovered {len(tests)} tests in {manifest_url}.")
    return tests

def main():
    os.makedirs(DEST_DIR, exist_ok=True)

    # (base_url, (name, type, ttl, nt)) pairs across every source, so the
    # download step below knows which remote base each file comes from
    # even though they all land in the same local data/ directory.
    all_tests = []
    for base_url in SOURCES:
        for t in fetch_manifest_tests(base_url):
            all_tests.append((base_url, t))

    print(f"Total: {len(all_tests)} tests across {len(SOURCES)} manifests.")

    # Write combined manifest
    with open(MANIFEST_FILE, "w") as mf:
        mf.write("test_name,test_type,ttl_file,nt_file\n")
        for _base_url, (test_name, test_type, ttl_file, nt_file) in all_tests:
            mf.write(f"{test_name},{test_type},{ttl_file or ''},{nt_file or ''}\n")

    # Download files
    for base_url, (test_name, test_type, ttl_file, nt_file) in all_tests:
        print(f"Test: {test_name} | Type: {test_type} | TTL: {ttl_file} | NT: {nt_file}")
        if ttl_file:
            print(f"  Downloading TTL: {ttl_file}")
            download_file(base_url + ttl_file, os.path.join(DEST_DIR, ttl_file))
        if nt_file:
            print(f"  Downloading NT: {nt_file}")
            download_file(base_url + nt_file, os.path.join(DEST_DIR, nt_file))

if __name__ == "__main__":
    main()
